"""Scene hydration, reference validation, and M14 tail regressions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from loremaster.audio.layer import LayerSpec
from loremaster.audio.loader import LoadedAudio
from loremaster.audio.scene_player import OnEnd, ScenePlayer, SceneSpec
from loremaster.events import EventBus
from loremaster.models.db import Database
from loremaster.models.repository import create_audio_file, create_scene
from loremaster.models.scene import LayerConfig, Scene, SceneCreate
from loremaster.scene_service import SceneService


class RecordingEngine:
    def __init__(self) -> None:
        self.played: list[str] = []
        self.faded: list[str] = []
        self.jumped: list[tuple[str, str, int]] = []
        self.stop_all_calls = 0

    def play_layer(self, layer_id, spec, on_ended=None) -> None:
        self.played.append(layer_id)

    def fade_out_layer(self, layer_id) -> None:
        self.faded.append(layer_id)

    def jump_to_tail(self, layer_id, tail_layer_id, tail_fade_ms=300) -> None:
        self.jumped.append((layer_id, tail_layer_id, tail_fade_ms))

    def stop_all(self) -> None:
        self.stop_all_calls += 1


class RecordingLoader:
    target_sample_rate = 48_000

    def __init__(self) -> None:
        self.loaded: list[Path] = []

    def load(self, path: Path) -> LoadedAudio:
        self.loaded.append(path)
        return LoadedAudio(
            data=np.zeros((48_000, 2), dtype=np.float32),
            sample_rate=48_000,
            source_path=path,
        )


async def _service(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'service.db'}")
    await db.create_all()
    engine = RecordingEngine()
    loader = RecordingLoader()
    player = ScenePlayer(engine)  # type: ignore[arg-type]
    service = SceneService(
        engine=engine,  # type: ignore[arg-type]
        loader=loader,  # type: ignore[arg-type]
        player=player,
        db=db,
        bus=EventBus(),
        audio_dir=tmp_path / "audio",
    )
    service.audio_dir.mkdir()
    return db, service, loader


@pytest.mark.asyncio
async def test_hydrate_preserves_loop_markers_and_pan(tmp_path):
    db, service, loader = await _service(tmp_path)
    try:
        async with db.session() as session:
            audio = await create_audio_file(
                session,
                original_name="rain.wav",
                path="rain.wav",
                duration_ms=10_000,
                sample_rate=48_000,
                channels=2,
                size_bytes=100,
            )
        layer = LayerConfig(
            audio_file_id=audio.id,
            pan_lr=-0.35,
            loop_start_ms=1200,
            loop_end_ms=8700,
        )
        scene = Scene(
            id=uuid4(),
            name="Rain",
            layers=[layer],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        spec = await service._hydrate(scene)

        assert loader.loaded == [service.audio_dir / "rain.wav"]
        assert len(spec.layers) == 1
        assert spec.layers[0].pan_lr == pytest.approx(-0.35)
        assert spec.layers[0].loop_start_ms == 1200
        assert spec.layers[0].loop_end_ms == 8700
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_reference_validation_reports_missing_physical_audio(tmp_path):
    db, service, _ = await _service(tmp_path)
    try:
        async with db.session() as session:
            audio = await create_audio_file(
                session,
                original_name="missing.wav",
                path="missing.wav",
                duration_ms=1000,
                sample_rate=48_000,
                channels=2,
                size_bytes=100,
            )
            await create_scene(
                session,
                SceneCreate(name="Broken", layers=[LayerConfig(audio_file_id=audio.id)]),
            )

        with pytest.raises(RuntimeError, match="missing audio file missing.wav"):
            await service.validate_references()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_end_scene_jumps_to_tail_without_manual_stop_semantics():
    engine = RecordingEngine()
    player = ScenePlayer(engine)  # type: ignore[arg-type]
    scene = SceneSpec(
        id="scene",
        name="Scene",
        layers=[
            LayerSpec(
                id="rain",
                data=np.zeros((48_000, 2), dtype=np.float32),
                loop=True,
                loop_start_ms=1000,
                loop_end_ms=5000,
            ),
            LayerSpec(id="sting", data=np.zeros((1000, 2), dtype=np.float32), loop=False),
        ],
        on_end=OnEnd(type="stop"),
    )
    await player.play(scene)

    async def resolver(_scene_id: str):
        raise AssertionError("stop policy must not resolve another scene")

    await player.end_scene(resolver)

    assert engine.jumped == [("scene::rain", "scene::rain::__tail", 300)]
    assert "scene::sting" in engine.faded
    assert engine.stop_all_calls == 0
    assert player.current_scene is None

    await player.play(scene)
    await player.stop()
    assert engine.stop_all_calls == 1
