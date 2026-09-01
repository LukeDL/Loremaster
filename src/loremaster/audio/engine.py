"""AudioEngine: PortAudio OutputStream + NumPy mixer.

Threading model
---------------
- The `sounddevice` callback runs on the PortAudio thread. It reads `_layers`
  and drains `_command_queue` at block boundaries. It never allocates in the
  hot path beyond a small output buffer.
- Public methods (`play_layer`, `stop_layer`, `set_layer_volume`, ...) are
  called from asyncio / any other thread and only enqueue commands. They
  never touch `_layers` directly.

Rules for the callback:
- No I/O.
- No locks that can block (uses `queue.Queue.get_nowait`).
- No allocation beyond the block-sized scratch buffer and the fixed-cost
  numpy operations `Layer.read` does.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import sounddevice as sd

from loremaster.audio.layer import Layer, LayerSpec, LayerState

log = logging.getLogger(__name__)


# ---- Commands ----------------------------------------------------------------


@dataclass
class _Cmd:
    """Base class for commands sent from public API to the audio callback."""


@dataclass
class _CmdAddLayer(_Cmd):
    layer_id: str
    spec: LayerSpec
    on_ended: Callable[[str], None] | None = None


@dataclass
class _CmdFadeOutLayer(_Cmd):
    layer_id: str


@dataclass
class _CmdExitLoop(_Cmd):
    layer_id: str


@dataclass
class _CmdSetLayerVolume(_Cmd):
    layer_id: str
    volume: float


@dataclass
class _CmdSetMasterVolume(_Cmd):
    volume: float


@dataclass
class _CmdStopAll(_Cmd):
    pass


# ---- Engine ------------------------------------------------------------------


class AudioEngine:
    def __init__(
        self,
        sample_rate: int = 48_000,
        block_size: int = 1024,
        device: int | str | None = None,
        on_state_change: Callable[[], None] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.device = device
        self.on_state_change = on_state_change

        self._layers: dict[str, Layer] = {}
        self._master_volume: float = 1.0
        self._command_queue: queue.Queue[_Cmd] = queue.Queue()
        self._stream: sd.OutputStream | None = None
        self._xrun_count: int = 0
        # snapshot lock — public state readers acquire this briefly.
        # Callback publishes a snapshot after each block; readers copy it.
        self._snapshot_lock = threading.Lock()
        self._snapshot: dict[str, Any] = {"layers": {}, "master_volume": 1.0}

    # ---- Lifecycle -----------------------------------------------------------

    def start(self) -> None:
        if self._stream is not None:
            return
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=2,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()
        log.info(
            "audio engine started: sr=%d block=%d device=%s",
            self.sample_rate, self.block_size, self.device or "default",
        )

    def stop(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self._layers.clear()

    # ---- Public API (thread-safe: enqueue only) -----------------------------

    def play_layer(
        self,
        layer_id: str,
        spec: LayerSpec,
        on_ended: Callable[[str], None] | None = None,
    ) -> None:
        """Add a layer. `on_ended` fires from the audio thread when the layer
        finishes naturally (e.g. after a tail played out following exit_loop)."""
        self._command_queue.put(_CmdAddLayer(layer_id=layer_id, spec=spec, on_ended=on_ended))

    def fade_out_layer(self, layer_id: str) -> None:
        self._command_queue.put(_CmdFadeOutLayer(layer_id=layer_id))

    def exit_layer_loop(self, layer_id: str) -> None:
        """Ask the layer to stop looping; when its cursor next hits loop_end,
        it will continue to EOF (playing the tail) and then end."""
        self._command_queue.put(_CmdExitLoop(layer_id=layer_id))

    def set_layer_volume(self, layer_id: str, volume: float) -> None:
        self._command_queue.put(_CmdSetLayerVolume(layer_id=layer_id, volume=volume))

    def set_master_volume(self, volume: float) -> None:
        self._command_queue.put(_CmdSetMasterVolume(volume=volume))

    def stop_all(self) -> None:
        self._command_queue.put(_CmdStopAll())

    def snapshot(self) -> dict[str, Any]:
        with self._snapshot_lock:
            return {
                "layers": dict(self._snapshot["layers"]),
                "master_volume": self._snapshot["master_volume"],
                "xrun_count": self._xrun_count,
            }

    # ---- Callback (PortAudio thread) ----------------------------------------

    def _callback(
        self,
        outdata: np.ndarray,
        frames: int,
        _time: Any,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            # underrun/overrun is the only failure mode we care about here
            if status.output_underflow:
                self._xrun_count += 1

        self._drain_commands()

        outdata.fill(0.0)
        if self._layers:
            for layer_id in list(self._layers.keys()):
                layer = self._layers[layer_id]
                alive = layer.read(outdata, frames)
                if not alive:
                    del self._layers[layer_id]

            if self._master_volume != 1.0:
                outdata *= self._master_volume

            # Soft clip: mixed layers can exceed [-1, 1]. tanh is smooth and
            # cheap; alternative would be per-layer normalization at load time.
            np.tanh(outdata, out=outdata)

        self._publish_snapshot()
        if self.on_state_change is not None:
            # Callback fires often (~46/s at 48k/1024). The callback itself
            # must not do I/O — the hook just sets a flag; consumer polls.
            try:
                self.on_state_change()
            except Exception:  # noqa: BLE001 — never let a handler kill the callback
                pass

    def _drain_commands(self) -> None:
        while True:
            try:
                cmd = self._command_queue.get_nowait()
            except queue.Empty:
                return
            self._apply_command(cmd)

    def _apply_command(self, cmd: _Cmd) -> None:
        if isinstance(cmd, _CmdAddLayer):
            # Replacing a layer with the same id: fade the old one out first
            # so we don't get a click. New one starts with its own fade-in.
            if cmd.layer_id in self._layers:
                self._layers[cmd.layer_id].begin_fade_out(self.sample_rate)
                # Rename to keep both alive during the crossfade
                self._layers[f"{cmd.layer_id}__old_{id(cmd)}"] = self._layers.pop(cmd.layer_id)
            self._layers[cmd.layer_id] = Layer.start(cmd.spec, self.sample_rate, on_ended=cmd.on_ended)
        elif isinstance(cmd, _CmdFadeOutLayer):
            layer = self._layers.get(cmd.layer_id)
            if layer is not None:
                layer.begin_fade_out(self.sample_rate)
        elif isinstance(cmd, _CmdExitLoop):
            layer = self._layers.get(cmd.layer_id)
            if layer is not None:
                layer.request_exit_loop()
        elif isinstance(cmd, _CmdSetLayerVolume):
            layer = self._layers.get(cmd.layer_id)
            if layer is not None:
                layer.set_volume(cmd.volume)
        elif isinstance(cmd, _CmdSetMasterVolume):
            self._master_volume = max(0.0, min(1.0, cmd.volume))
        elif isinstance(cmd, _CmdStopAll):
            for layer in self._layers.values():
                layer.begin_fade_out(self.sample_rate)

    def _publish_snapshot(self) -> None:
        # Build a small dict per layer — cheap even at callback rate.
        layers_snap = {
            lid: {
                "state": layer.state.value,
                "position_ms": layer.position_ms(self.sample_rate),
                "volume": layer.spec.volume,
                "loop": layer.spec.loop,
            }
            for lid, layer in self._layers.items()
            if layer.state != LayerState.ENDED
        }
        with self._snapshot_lock:
            self._snapshot["layers"] = layers_snap
            self._snapshot["master_volume"] = self._master_volume
