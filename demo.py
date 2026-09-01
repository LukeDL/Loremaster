"""Standalone demo of the M1 audio engine.

Generates synthetic tones so it needs no audio files. Sequence:

  1. Play "exploration" scene (soft pad + slow ambient) with fade-in.
  2. Press ENTER: transition to "combat" scene (busy pulse + drone).
  3. Press ENTER: end combat -> on_end=return_previous -> back to exploration.
  4. Press ENTER: stop.

Listen for:
  * loop wrap without clicks or gaps in either scene
  * smooth crossfade between scenes (no "hole" in the middle)
  * responsive commands (transition starts immediately)

Run: `uv run python demo.py`
"""

from __future__ import annotations

import asyncio
import logging

import numpy as np

from loremaster.audio.engine import AudioEngine
from loremaster.audio.layer import LayerSpec
from loremaster.audio.scene_player import OnEnd, SceneSpec

SAMPLE_RATE = 48_000


def sine(freq: float, seconds: float, amp: float = 0.2) -> np.ndarray:
    """Generate a loopable stereo sine tone.

    Length is chosen so that both channels complete an integer number of cycles,
    guaranteeing no discontinuity at the loop boundary — this is the gapless
    loop test the mixer must pass.
    """
    period = SAMPLE_RATE / freq
    n_periods = max(1, int(seconds * freq))
    n = int(round(n_periods * period))
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    wave = amp * np.sin(2.0 * np.pi * freq * t).astype(np.float32)
    return np.column_stack([wave, wave])


def build_scenes() -> tuple[SceneSpec, SceneSpec]:
    exploration = SceneSpec(
        id="exploration",
        name="Exploration",
        layers=[
            LayerSpec(
                id="pad",
                data=sine(220.0, seconds=4.0, amp=0.15),
                loop=True,
                volume=0.8,
                fade_in_ms=1500,
                fade_out_ms=1500,
            ),
            LayerSpec(
                id="ambient",
                data=sine(330.0, seconds=3.0, amp=0.08),
                loop=True,
                volume=0.6,
                fade_in_ms=1500,
                fade_out_ms=1500,
            ),
        ],
        on_end=OnEnd(type="return_previous"),
    )
    combat = SceneSpec(
        id="combat",
        name="Combat",
        layers=[
            LayerSpec(
                id="drums",
                data=sine(110.0, seconds=2.0, amp=0.25),
                loop=True,
                volume=0.9,
                fade_in_ms=800,
                fade_out_ms=1200,
            ),
            LayerSpec(
                id="brass",
                data=sine(440.0, seconds=2.5, amp=0.12),
                loop=True,
                volume=0.7,
                fade_in_ms=800,
                fade_out_ms=1200,
            ),
        ],
        on_end=OnEnd(type="return_previous"),
    )
    return exploration, combat


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    exploration, combat = build_scenes()

    engine = AudioEngine(sample_rate=SAMPLE_RATE, block_size=1024)
    engine.start()

    from loremaster.audio.scene_player import ScenePlayer
    player = ScenePlayer(engine)

    async def resolver(scene_id: str) -> SceneSpec | None:
        return {"exploration": exploration, "combat": combat}.get(scene_id)

    print("\n>> playing EXPLORATION (fade in)")
    await player.play(exploration)

    await asyncio.get_event_loop().run_in_executor(None, input, "\n[ENTER] transition to COMBAT ")
    print(">> playing COMBAT (crossfade)")
    await player.play(combat)

    await asyncio.get_event_loop().run_in_executor(None, input, "\n[ENTER] end combat (return to exploration) ")
    print(">> end_combat -> return_previous (crossfade)")
    await player.end_combat(resolver)

    await asyncio.get_event_loop().run_in_executor(None, input, "\n[ENTER] stop and quit ")
    print(">> stopping")
    await player.stop()

    # Let the fade-out finish before killing the stream
    await asyncio.sleep(2.0)
    engine.stop()
    print(f"\nxrun count: {engine.snapshot()['xrun_count']}")


if __name__ == "__main__":
    asyncio.run(main())
