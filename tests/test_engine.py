"""Mixer correctness tests — no PortAudio, we drive the callback directly."""

from __future__ import annotations

import numpy as np
import pytest

from loremaster.audio.crossfade import equal_power_in, equal_power_out
from loremaster.audio.layer import Layer, LayerSpec, LayerState


SR = 48_000


def _stereo_ramp(n: int) -> np.ndarray:
    """A distinct, non-repeating ramp so we can prove the loop wrap emits the
    right samples in the right order (not silent, not garbage)."""
    x = np.linspace(0.1, 0.9, n, dtype=np.float32)
    return np.column_stack([x, x])


def test_loop_wrap_is_gapless():
    """When cursor hits end-of-buffer, the next samples must be the head of
    the buffer — no silence, no repeat, no reorder."""
    data = _stereo_ramp(100)
    spec = LayerSpec(id="t", data=data, loop=True, volume=1.0, fade_in_ms=0, fade_out_ms=0)
    layer = Layer.start(spec, SR)

    # Ask for 250 frames from a 100-frame buffer -> should read all, wrap, all, wrap, half
    out = np.zeros((250, 2), dtype=np.float32)
    alive = layer.read(out, 250)
    assert alive

    expected = np.concatenate([data, data, data[:50]], axis=0)
    np.testing.assert_allclose(out, expected, atol=1e-6)


def test_non_loop_ends_after_buffer():
    data = _stereo_ramp(64)
    spec = LayerSpec(id="t", data=data, loop=False, volume=1.0, fade_in_ms=0, fade_out_ms=0)
    layer = Layer.start(spec, SR)

    out1 = np.zeros((64, 2), dtype=np.float32)
    assert layer.read(out1, 64) is True
    np.testing.assert_allclose(out1, data, atol=1e-6)

    out2 = np.zeros((10, 2), dtype=np.float32)
    assert layer.read(out2, 10) is False
    # Nothing was written to out2 after end-of-file
    np.testing.assert_array_equal(out2, np.zeros_like(out2))


def test_equal_power_envelope_sums_to_unity():
    """The critical property: cos^2 + sin^2 == 1 at every sample.
    Guarantees a crossfade between uncorrelated signals has no perceived
    dip in the middle."""
    n = 1024
    fade_in = equal_power_in(n)
    fade_out = equal_power_out(n)
    np.testing.assert_allclose(fade_in**2 + fade_out**2, np.ones(n), atol=1e-6)


def test_fade_in_reaches_full_volume():
    n_frames = int(0.5 * SR)  # 500 ms
    data = np.ones((n_frames + SR, 2), dtype=np.float32)  # DC ones so gain = output
    spec = LayerSpec(id="t", data=data, loop=False, volume=1.0, fade_in_ms=500, fade_out_ms=0)
    layer = Layer.start(spec, SR)

    out = np.zeros((n_frames + 100, 2), dtype=np.float32)
    layer.read(out, n_frames + 100)

    # First sample should be near 0 (sin(0) = 0), last of fade near 1 (sin(pi/2))
    assert out[0, 0] < 0.05
    assert out[n_frames - 1, 0] == pytest.approx(1.0, abs=1e-3)
    # After the fade the layer is at full base volume
    assert out[n_frames + 50, 0] == pytest.approx(1.0, abs=1e-6)
    assert layer.state == LayerState.PLAYING


def test_fade_out_ends_layer():
    n_frames = int(0.5 * SR)
    data = np.ones((n_frames + SR, 2), dtype=np.float32)
    spec = LayerSpec(id="t", data=data, loop=False, volume=1.0, fade_in_ms=0, fade_out_ms=500)
    layer = Layer.start(spec, SR)
    assert layer.state == LayerState.PLAYING

    layer.begin_fade_out(SR)
    assert layer.state == LayerState.FADING_OUT

    out = np.zeros((n_frames + 100, 2), dtype=np.float32)
    alive = layer.read(out, n_frames + 100)

    assert alive is False
    assert layer.state == LayerState.ENDED
    # Fade started at full, ends near zero
    assert out[0, 0] == pytest.approx(1.0, abs=1e-3)
    assert out[n_frames - 1, 0] < 0.05
    # After fade completes, nothing further is written
    np.testing.assert_allclose(out[n_frames:], np.zeros_like(out[n_frames:]), atol=1e-6)


def test_volume_scales_output():
    data = np.ones((100, 2), dtype=np.float32)
    spec = LayerSpec(id="t", data=data, loop=True, volume=0.3, fade_in_ms=0, fade_out_ms=0)
    layer = Layer.start(spec, SR)
    out = np.zeros((50, 2), dtype=np.float32)
    layer.read(out, 50)
    np.testing.assert_allclose(out, 0.3 * np.ones_like(out), atol=1e-6)
