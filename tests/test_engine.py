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

    # Read consumes the whole buffer and reports the layer has ended in the
    # same call (no zombie "one more read returning False" state).
    out1 = np.zeros((64, 2), dtype=np.float32)
    assert layer.read(out1, 64) is False
    np.testing.assert_allclose(out1, data, atol=1e-6)


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


# Use a synthetic sample rate where 1 frame = 1 ms; this makes loop-region
# tests robust to ms<->frame rounding (irrelevant to correctness of the mixer).
_SR_1MS = 1000


def test_loop_region_wraps_at_loop_end_not_file_end():
    """With loop_start_ms/loop_end_ms set, playback loops between those
    positions instead of wrapping at end-of-file."""
    n = 1000
    x = np.arange(n, dtype=np.float32) / n  # unique per frame -> wrap is obvious
    data = np.column_stack([x, x])
    spec = LayerSpec(
        id="t", data=data, loop=True, volume=1.0, fade_in_ms=0, fade_out_ms=0,
        loop_start_ms=200, loop_end_ms=600,  # frames [200, 600) at SR=1000
    )
    layer = Layer.start(spec, _SR_1MS)

    # intro (200) + full loop (400) + 250 of second loop = 850 frames
    out = np.zeros((850, 2), dtype=np.float32)
    assert layer.read(out, 850) is True
    np.testing.assert_allclose(out[:600], data[:600], atol=1e-6)
    np.testing.assert_allclose(out[600:850], data[200:450], atol=1e-6)


def test_exit_loop_lets_tail_play_to_eof():
    """After request_exit_loop(), the cursor keeps advancing past loop_end
    (no wrap) until EOF, then the layer ends. Exit takes effect at the
    current cursor position — no need to wait for the loop to complete."""
    n = 500
    x = np.arange(n, dtype=np.float32) / n
    data = np.column_stack([x, x])
    spec = LayerSpec(
        id="t", data=data, loop=True, volume=1.0, fade_in_ms=0, fade_out_ms=0,
        loop_start_ms=100, loop_end_ms=300,
    )
    layer = Layer.start(spec, _SR_1MS)

    # Read 250 frames: intro (0..100) + partial loop (100..250). After this
    # the cursor sits at frame 250, still inside the loop region.
    out1 = np.zeros((250, 2), dtype=np.float32)
    layer.read(out1, 250)
    assert layer.cursor == 250

    layer.request_exit_loop()
    # Now request 300 more: should read frames 250..500 (finishes remainder
    # of loop region plus tail), then EOF.
    out2 = np.zeros((300, 2), dtype=np.float32)
    alive = layer.read(out2, 300)
    assert alive is False
    assert layer.state == LayerState.ENDED
    np.testing.assert_allclose(out2[:250], data[250:500], atol=1e-6)
    np.testing.assert_allclose(out2[250:], np.zeros_like(out2[250:]), atol=1e-6)


def test_on_ended_callback_fires_on_natural_end():
    """The on_ended callback should fire when a non-loop layer reaches EOF."""
    data = np.ones((100, 2), dtype=np.float32)
    spec = LayerSpec(id="t", data=data, loop=False, volume=1.0, fade_in_ms=0, fade_out_ms=0)
    calls: list[str] = []
    layer = Layer.start(spec, SR, on_ended=lambda lid: calls.append(lid))

    out = np.zeros((100, 2), dtype=np.float32)
    alive = layer.read(out, 100)
    assert alive is False
    assert calls == ["t"]

    # Subsequent reads must not fire the callback again (idempotent).
    layer.read(np.zeros((10, 2), dtype=np.float32), 10)
    assert calls == ["t"]


def test_volume_scales_output():
    data = np.ones((100, 2), dtype=np.float32)
    spec = LayerSpec(id="t", data=data, loop=True, volume=0.3, fade_in_ms=0, fade_out_ms=0)
    layer = Layer.start(spec, SR)
    out = np.zeros((50, 2), dtype=np.float32)
    layer.read(out, 50)
    np.testing.assert_allclose(out, 0.3 * np.ones_like(out), atol=1e-6)
