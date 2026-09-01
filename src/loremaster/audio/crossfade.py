"""Envelope shapes for fades and crossfades."""

from __future__ import annotations

import numpy as np


def equal_power_out(n: int) -> np.ndarray:
    """Fade-out envelope: cos ramp from 1 to 0 over n samples.

    Paired with equal_power_in, the sum of squared gains is constant, so a
    crossfade between uncorrelated signals keeps perceived loudness flat
    (avoids the "dip in the middle" of a linear crossfade).
    """
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.linspace(0.0, np.pi / 2.0, n, dtype=np.float32)
    return np.cos(t).astype(np.float32)


def equal_power_in(n: int) -> np.ndarray:
    """Fade-in envelope: sin ramp from 0 to 1 over n samples."""
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.linspace(0.0, np.pi / 2.0, n, dtype=np.float32)
    return np.sin(t).astype(np.float32)


def linear_ramp(start: float, end: float, n: int) -> np.ndarray:
    """Linear volume ramp — used for manual volume adjustments (not fades)."""
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    return np.linspace(start, end, n, dtype=np.float32)


def ms_to_samples(ms: float, sample_rate: int) -> int:
    return max(0, int(round(ms * sample_rate / 1000.0)))
