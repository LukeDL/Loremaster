"""Load audio files into stereo float32 NumPy arrays, resampled to the engine sample rate."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class LoadedAudio:
    """Decoded audio ready for the mixer: shape (n_frames, 2), float32, target sample rate."""

    data: np.ndarray
    sample_rate: int
    source_path: Path


class AudioLoader:
    """Caches decoded arrays so re-triggering a scene doesn't re-decode from disk."""

    def __init__(self, target_sample_rate: int = 48_000) -> None:
        self.target_sample_rate = target_sample_rate
        self._cache: dict[Path, LoadedAudio] = {}

    def load(self, path: str | Path) -> LoadedAudio:
        key = Path(path).resolve()
        if key in self._cache:
            return self._cache[key]

        data, sample_rate = sf.read(str(key), dtype="float32", always_2d=True)
        # always_2d gives shape (n, channels); normalize to stereo
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]

        if sample_rate != self.target_sample_rate:
            data = _resample_linear(data, sample_rate, self.target_sample_rate)

        data = np.ascontiguousarray(data, dtype=np.float32)
        loaded = LoadedAudio(data=data, sample_rate=self.target_sample_rate, source_path=key)
        self._cache[key] = loaded
        return loaded

    def clear(self) -> None:
        self._cache.clear()


def _resample_linear(data: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    """Linear resampler — good enough for MVP. Swap for soxr later if quality matters."""
    if src_sr == dst_sr:
        return data
    src_n = data.shape[0]
    dst_n = int(round(src_n * dst_sr / src_sr))
    if dst_n <= 0:
        return np.zeros((0, data.shape[1]), dtype=np.float32)
    src_idx = np.linspace(0.0, src_n - 1, dst_n, dtype=np.float64)
    left = np.floor(src_idx).astype(np.int64)
    right = np.minimum(left + 1, src_n - 1)
    frac = (src_idx - left).astype(np.float32)[:, None]
    return (data[left] * (1.0 - frac) + data[right] * frac).astype(np.float32)
