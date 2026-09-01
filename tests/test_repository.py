"""CRUD + OnEnd JSON round-trip tests, using an in-memory SQLite database."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio

from loremaster.models.db import Database
from loremaster.models.repository import (
    create_audio_file,
    create_scene,
    delete_audio_file,
    delete_scene,
    get_scene,
    list_audio_files,
    list_scenes,
    update_scene,
)
from loremaster.models.scene import (
    LayerConfig,
    OnEndGoto,
    OnEndReturnPrevious,
    OnEndStop,
    SceneCreate,
    SceneUpdate,
)


@pytest_asyncio.fixture
async def db():
    d = Database("sqlite+aiosqlite:///:memory:")
    await d.create_all()
    try:
        yield d
    finally:
        await d.close()


@pytest_asyncio.fixture
async def audio_file(db):
    async with db.session() as sess:
        af = await create_audio_file(
            sess,
            original_name="battle.ogg",
            path="abc.ogg",
            duration_ms=120_000,
            sample_rate=48_000,
            channels=2,
            size_bytes=1_234_567,
        )
    return af


@pytest.mark.asyncio
async def test_audio_file_crud(db, audio_file):
    async with db.session() as sess:
        rows = await list_audio_files(sess)
        assert len(rows) == 1
        assert rows[0].original_name == "battle.ogg"
        assert rows[0].duration_ms == 120_000

        deleted = await delete_audio_file(sess, audio_file.id)
        assert deleted is True
        assert await list_audio_files(sess) == []


@pytest.mark.asyncio
async def test_scene_create_and_retrieve(db, audio_file):
    async with db.session() as sess:
        payload = SceneCreate(
            name="Forest exploration",
            description="Calm forest ambience",
            layers=[
                LayerConfig(audio_file_id=audio_file.id, loop=True, volume=0.7, fade_in_ms=800),
                LayerConfig(audio_file_id=audio_file.id, loop=True, volume=0.4),
            ],
            on_end=OnEndReturnPrevious(),
        )
        created = await create_scene(sess, payload)
        assert created.name == "Forest exploration"
        assert len(created.layers) == 2
        assert created.layers[0].volume == 0.7
        assert created.on_end.type == "return_previous"

        fetched = await get_scene(sess, created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert len(fetched.layers) == 2


@pytest.mark.asyncio
async def test_on_end_policies_roundtrip(db, audio_file):
    target_id = uuid4()

    async with db.session() as sess:
        s1 = await create_scene(sess, SceneCreate(name="a", on_end=OnEndReturnPrevious()))
        s2 = await create_scene(sess, SceneCreate(name="b", on_end=OnEndStop()))
        s3 = await create_scene(sess, SceneCreate(name="c", on_end=OnEndGoto(scene_id=target_id)))

        r1 = await get_scene(sess, s1.id)
        r2 = await get_scene(sess, s2.id)
        r3 = await get_scene(sess, s3.id)

        assert r1.on_end.type == "return_previous"
        assert r2.on_end.type == "stop"
        assert r3.on_end.type == "goto"
        assert r3.on_end.scene_id == target_id


@pytest.mark.asyncio
async def test_scene_update_replaces_layers(db, audio_file):
    async with db.session() as sess:
        created = await create_scene(
            sess,
            SceneCreate(
                name="original",
                layers=[LayerConfig(audio_file_id=audio_file.id)],
            ),
        )
        assert len(created.layers) == 1

        updated = await update_scene(
            sess,
            created.id,
            SceneUpdate(
                name="updated",
                layers=[
                    LayerConfig(audio_file_id=audio_file.id, volume=0.1),
                    LayerConfig(audio_file_id=audio_file.id, volume=0.9),
                    LayerConfig(audio_file_id=audio_file.id, volume=0.5),
                ],
            ),
        )
        assert updated.name == "updated"
        assert len(updated.layers) == 3
        assert [layer.volume for layer in updated.layers] == [0.1, 0.9, 0.5]


@pytest.mark.asyncio
async def test_delete_audio_file_blocked_if_used_by_scene(db, audio_file):
    async with db.session() as sess:
        await create_scene(
            sess,
            SceneCreate(name="uses_it", layers=[LayerConfig(audio_file_id=audio_file.id)]),
        )
        deleted = await delete_audio_file(sess, audio_file.id)
        assert deleted is False


@pytest.mark.asyncio
async def test_delete_scene_cascades_layers(db, audio_file):
    async with db.session() as sess:
        created = await create_scene(
            sess,
            SceneCreate(
                name="doomed",
                layers=[LayerConfig(audio_file_id=audio_file.id) for _ in range(3)],
            ),
        )
        assert await delete_scene(sess, created.id) is True
        assert await get_scene(sess, created.id) is None
        # AudioFile is now unreferenced -> deletable
        assert await delete_audio_file(sess, audio_file.id) is True
