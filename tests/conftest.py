"""Reusable headless test harness for API and static UI tests."""

from __future__ import annotations

from contextlib import asynccontextmanager

import numpy as np
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from loremaster.audio.scene_player import ScenePlayer
from loremaster.config import settings
from loremaster.events import EventBus
from loremaster.main import create_app
from loremaster.models.db import Database
from loremaster.scene_service import SceneService


class FakeEngine:
    def __init__(self, sample_rate: int = 48_000) -> None:
        self.sample_rate = sample_rate
        self.block_size = 1024
        self.played: list[str] = []
        self.faded_out: list[str] = []
        self.jumped_to_tail: list[tuple[str, str, int]] = []
        self.layer_volumes: list[tuple[str, float]] = []
        self.layer_pans: list[tuple[str, float]] = []
        self._master_volume = 1.0

    def start(self) -> None: ...
    def stop(self) -> None: ...

    def play_layer(self, layer_id, spec, on_ended=None) -> None:
        self.played.append(layer_id)

    def fade_out_layer(self, layer_id) -> None:
        self.faded_out.append(layer_id)

    def exit_layer_loop(self, layer_id) -> None: ...

    def jump_to_tail(self, layer_id, tail_layer_id, tail_fade_ms=300) -> None:
        self.jumped_to_tail.append((layer_id, tail_layer_id, tail_fade_ms))

    def set_layer_volume(self, layer_id, volume) -> None:
        self.layer_volumes.append((layer_id, volume))

    def set_layer_pan(self, layer_id, pan_lr) -> None:
        self.layer_pans.append((layer_id, pan_lr))

    def set_master_volume(self, volume) -> None:
        self._master_volume = volume

    def stop_all(self) -> None: ...

    def snapshot(self):
        return {"layers": {}, "master_volume": self._master_volume, "xrun_count": 0}


class FakeLoader:
    def __init__(self, sample_rate: int = 48_000) -> None:
        self.target_sample_rate = sample_rate

    def load(self, path):
        from loremaster.audio.loader import LoadedAudio

        return LoadedAudio(
            data=np.zeros((self.target_sample_rate, 2), dtype=np.float32),
            sample_rate=self.target_sample_rate,
            source_path=path,
        )


@pytest_asyncio.fixture
async def app(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    (tmp_path / "audio").mkdir()

    @asynccontextmanager
    async def fake_lifespan(app):
        db = Database(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
        await db.create_all()
        bus = EventBus()
        engine = FakeEngine()
        loader = FakeLoader()
        player = ScenePlayer(engine)  # type: ignore[arg-type]
        service = SceneService(
            engine=engine,  # type: ignore[arg-type]
            loader=loader,  # type: ignore[arg-type]
            player=player,
            db=db,
            bus=bus,
            audio_dir=tmp_path / "audio",
        )
        from loremaster.api.ws import WsBroadcaster

        app.state.db = db
        app.state.bus = bus
        app.state.engine = engine
        app.state.scene_service = service
        app.state.ws_broadcaster = WsBroadcaster(bus, service)
        try:
            yield
        finally:
            await db.close()

    yield create_app(lifespan_context=fake_lifespan)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client
