"""A single audio layer: one buffer, one cursor, one volume envelope.

Owned exclusively by the audio callback thread. Public state changes go
through the engine's command queue and are applied at block boundaries.
"""

from __future__ import annotations

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


@dataclass
class Layer:
    """Runtime state of a playing layer. Do not access from outside the callback."""

    spec: LayerSpec
    cursor: int = 0
    state: LayerState = LayerState.FADING_IN
    _fade_env: np.ndarray | None = None
    _fade_pos: int = 0
    _base_volume: float = field(init=False)

    def __post_init__(self) -> None:
        self._base_volume = self.spec.volume

    @classmethod
    def start(cls, spec: LayerSpec, sample_rate: int) -> "Layer":
        layer = cls(spec=spec)
        if spec.fade_in_ms > 0:
            n = int(round(spec.fade_in_ms * sample_rate / 1000.0))
            layer._fade_env = equal_power_in(n)
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
            self.state = LayerState.ENDED
            return
        self._fade_env = equal_power_out(n)
        self._fade_pos = 0
        self.state = LayerState.FADING_OUT

    def read(self, out: np.ndarray, frames: int) -> bool:
        """Mix `frames` samples of this layer into `out` (shape (frames, 2)).

        Returns True while the layer is still active; False when it has ended
        and can be removed by the engine.
        """
        if self.state == LayerState.ENDED:
            return False

        buf = self._read_from_buffer(frames)
        if buf is None:
            self.state = LayerState.ENDED
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
                    # zero out the tail so nothing leaks after fade completes
                    if take < frames:
                        gain[take:] = 0.0
                    out += buf * gain[:, None]
                    self.state = LayerState.ENDED
                    return False

        out += buf * gain[:, None]
        return True

    def _read_from_buffer(self, frames: int) -> np.ndarray | None:
        """Return `frames` frames from the source buffer, wrapping if loop=True.

        Returns None if we hit end-of-file on a non-loop layer.
        """
        data = self.spec.data
        n = data.shape[0]
        if n == 0:
            return None
        if not self.spec.loop and self.cursor >= n:
            return None

        end = self.cursor + frames
        if end <= n:
            block = data[self.cursor : end]
            self.cursor = end if end < n else (0 if self.spec.loop else n)
            if end == n and not self.spec.loop:
                # emit final block, next call will return None
                pass
            return block

        if not self.spec.loop:
            block = np.zeros((frames, 2), dtype=np.float32)
            take = n - self.cursor
            block[:take] = data[self.cursor : n]
            self.cursor = n
            return block

        # loop wrap: concatenate tail + head with as many full wraps as needed
        block = np.empty((frames, 2), dtype=np.float32)
        written = 0
        while written < frames:
            available = n - self.cursor
            take = min(available, frames - written)
            block[written : written + take] = data[self.cursor : self.cursor + take]
            written += take
            self.cursor += take
            if self.cursor >= n:
                self.cursor = 0
        return block

    def set_volume(self, volume: float) -> None:
        """Immediate volume change. Called at block boundary via engine command."""
        self._base_volume = max(0.0, min(1.0, volume))
        self.spec.volume = self._base_volume

    def position_ms(self, sample_rate: int) -> int:
        return int(self.cursor * 1000 / sample_rate)
