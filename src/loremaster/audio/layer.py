"""A single audio layer: one buffer, one cursor, one volume envelope.

Owned exclusively by the audio callback thread. Public state changes go
through the engine's command queue and are applied at block boundaries.

Loop region
-----------
If ``LayerSpec.loop_start_ms`` and ``loop_end_ms`` are set, playback works
Skyrim/Wwise-style:

- Frames ``[0, loop_start)`` play once (intro).
- Frames ``[loop_start, loop_end)`` loop.
- When ``request_exit_loop()`` is called, the cursor stops wrapping at
  loop_end and continues to EOF (tail), then the layer ends naturally.

If the markers are missing, the layer either loops the whole buffer
(``loop=True``) or plays once and ends (``loop=False``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from loremaster.audio.crossfade import equal_power_in, equal_power_out


class LayerState(Enum):
    FADING_IN = "fading_in"
    PLAYING = "playing"
    FADING_OUT = "fading_out"
    ENDED = "ended"


@dataclass
class LayerSpec:
    """User-facing config for a layer within a scene."""

    id: str
    data: np.ndarray  # shape (n, 2), float32, engine sample rate
    loop: bool = True
    volume: float = 1.0
    fade_in_ms: int = 500
    fade_out_ms: int = 500
    loop_start_ms: int | None = None
    loop_end_ms: int | None = None


@dataclass
class Layer:
    """Runtime state of a playing layer. Do not access from outside the callback."""

    spec: LayerSpec
    cursor: int = 0
    state: LayerState = LayerState.FADING_IN
    _fade_env: np.ndarray | None = None
    _fade_pos: int = 0
    _base_volume: float = field(init=False)
    _loop_start_frame: int | None = None  # inclusive
    _loop_end_frame: int | None = None    # exclusive
    _exit_loop_requested: bool = False
    _on_ended: Callable[[str], None] | None = None

    def __post_init__(self) -> None:
        self._base_volume = self.spec.volume

    @classmethod
    def start(
        cls,
        spec: LayerSpec,
        sample_rate: int,
        on_ended: Callable[[str], None] | None = None,
    ) -> "Layer":
        layer = cls(spec=spec, _on_ended=on_ended)
        if spec.loop_start_ms is not None and spec.loop_end_ms is not None:
            n = spec.data.shape[0]
            start = int(round(spec.loop_start_ms * sample_rate / 1000.0))
            end = int(round(spec.loop_end_ms * sample_rate / 1000.0))
            # Clamp and sanity check; ignore markers if invalid.
            start = max(0, min(start, n))
            end = max(0, min(end, n))
            if end > start:
                layer._loop_start_frame = start
                layer._loop_end_frame = end
        if spec.fade_in_ms > 0:
            fade_n = int(round(spec.fade_in_ms * sample_rate / 1000.0))
            layer._fade_env = equal_power_in(fade_n)
            layer._fade_pos = 0
            layer.state = LayerState.FADING_IN
        else:
            layer.state = LayerState.PLAYING
        return layer

    def begin_fade_out(self, sample_rate: int) -> None:
        if self.state == LayerState.ENDED:
            return
        n = int(round(self.spec.fade_out_ms * sample_rate / 1000.0))
        if n <= 0:
            self._mark_ended()
            return
        self._fade_env = equal_power_out(n)
        self._fade_pos = 0
        self.state = LayerState.FADING_OUT

    def request_exit_loop(self) -> None:
        """Stop looping; when the cursor reaches loop_end, let it continue to
        EOF instead of wrapping. Called from the engine command queue."""
        self._exit_loop_requested = True

    def has_loop_region(self) -> bool:
        return self._loop_start_frame is not None and self._loop_end_frame is not None

    def read(self, out: np.ndarray, frames: int) -> bool:
        """Mix `frames` samples of this layer into `out` (shape (frames, 2)).

        Returns True while the layer is still active; False when it has ended
        and can be removed by the engine.
        """
        if self.state == LayerState.ENDED:
            return False

        buf = self._read_from_buffer(frames)
        if buf is None:
            self._mark_ended()
            return False

        gain = np.full(frames, self._base_volume, dtype=np.float32)

        if self._fade_env is not None:
            remaining = len(self._fade_env) - self._fade_pos
            take = min(remaining, frames)
            gain[:take] *= self._fade_env[self._fade_pos : self._fade_pos + take]
            self._fade_pos += take
            if self._fade_pos >= len(self._fade_env):
                if self.state == LayerState.FADING_IN:
                    self.state = LayerState.PLAYING
                    self._fade_env = None
                    self._fade_pos = 0
                elif self.state == LayerState.FADING_OUT:
                    if take < frames:
                        gain[take:] = 0.0
                    out += buf * gain[:, None]
                    self._mark_ended()
                    return False

        out += buf * gain[:, None]

        # If this read consumed the last available frames (EOF and no more
        # wrapping possible), end the layer now instead of waiting for the
        # next call to notice.
        n = self.spec.data.shape[0]
        if self.cursor >= n and (not self.spec.loop or self._exit_loop_requested):
            self._mark_ended()
            return False
        return True

    def _read_from_buffer(self, frames: int) -> np.ndarray | None:
        """Return `frames` frames from the source buffer, handling loops and
        loop regions. Returns None on EOF (non-looping layer, or looping layer
        that has exited its loop and reached the end of the file)."""
        data = self.spec.data
        n = data.shape[0]
        if n == 0:
            return None
        if self.cursor >= n:
            # Non-loop layer already fully played; also the exit-loop tail
            # falls here once it reaches EOF.
            if not self.spec.loop or self._exit_loop_requested:
                return None
            self.cursor = 0  # plain loop wraps at file boundary

        block = np.empty((frames, 2), dtype=np.float32)
        written = 0
        while written < frames:
            wrap_at = self._next_wrap_point(n)
            available = wrap_at - self.cursor
            if available <= 0:
                # Reached EOF on a tail (or non-loop layer past end).
                if written == 0:
                    return None
                # Partial block filled — zero the rest so the mixer stays clean.
                block[written:] = 0.0
                self.cursor = n
                return block
            take = min(available, frames - written)
            block[written : written + take] = data[self.cursor : self.cursor + take]
            written += take
            self.cursor += take
            if self.cursor >= wrap_at:
                if self._should_wrap(n):
                    # Wrap to loop_start (region) or 0 (whole-file loop)
                    self.cursor = self._loop_start_frame if self.has_loop_region() else 0
                # else: we hit EOF or the tail path; next iteration handles it.
        return block

    def _next_wrap_point(self, n: int) -> int:
        """The next cursor value at which we need to decide what to do:
        wrap back to loop_start, or stop at EOF. Reading may proceed linearly
        up to (but not including) this frame index in a single slice."""
        if self.has_loop_region() and not self._exit_loop_requested:
            assert self._loop_end_frame is not None
            # If cursor is already past loop_end (unusual, e.g. loop markers
            # changed mid-play), treat file end as the wrap point.
            return self._loop_end_frame if self.cursor < self._loop_end_frame else n
        return n

    def _should_wrap(self, n: int) -> bool:
        """After hitting a wrap point, do we loop back or continue to EOF?"""
        if self.has_loop_region() and not self._exit_loop_requested:
            # Wrapped at loop_end; go back to loop_start.
            return True
        # Whole-file loop with no region and no exit request.
        return self.spec.loop and not self._exit_loop_requested and self.cursor >= n

    def _mark_ended(self) -> None:
        if self.state != LayerState.ENDED:
            self.state = LayerState.ENDED
            if self._on_ended is not None:
                # Callback runs on the audio thread — must be threadsafe on
                # the receiver's side (Scene Player wraps with call_soon_threadsafe).
                try:
                    self._on_ended(self.spec.id)
                except Exception:  # noqa: BLE001
                    pass

    def set_volume(self, volume: float) -> None:
        """Immediate volume change. Called at block boundary via engine command."""
        self._base_volume = max(0.0, min(1.0, volume))
        self.spec.volume = self._base_volume

    def position_ms(self, sample_rate: int) -> int:
        return int(self.cursor * 1000 / sample_rate)
