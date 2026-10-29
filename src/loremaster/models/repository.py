"""Data-access helpers: convert Pydantic <-> SQLAlchemy rows, run queries."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from loremaster.models.db import AudioFileRow, LayerRow, SceneRow
from loremaster.models.scene import (
    AudioFile,
    GroupVolumes,
    LayerConfig,
    OnEndGoto,
    OnEndPolicy,
    OnEndReturnPrevious,
    OnEndStop,
    Scene,
    SceneCreate,
    SceneUpdate,
)


class InvalidReferenceError(ValueError):
    """A scene payload points to audio or another scene that does not exist."""


# ---- OnEnd (de)serialization -------------------------------------------------


def _on_end_to_json(policy: OnEndPolicy) -> str:
    return policy.model_dump_json()


def _on_end_from_json(raw: str) -> OnEndPolicy:
    obj = json.loads(raw)
    t = obj.get("type")
    if t == "return_previous":
        return OnEndReturnPrevious()
    if t == "goto":
        return OnEndGoto(scene_id=UUID(obj["scene_id"]))
    if t == "stop":
        return OnEndStop()
    raise ValueError(f"unknown on_end type: {t}")


# ---- AudioFile ---------------------------------------------------------------


async def create_audio_file(
    session: AsyncSession,
    *,
    original_name: str,
    path: str,
    duration_ms: int,
    sample_rate: int,
    channels: int,
    size_bytes: int,
) -> AudioFile:
    row = AudioFileRow(
        id=str(uuid4()),
        original_name=original_name,
        path=path,
        duration_ms=duration_ms,
        sample_rate=sample_rate,
        channels=channels,
        size_bytes=size_bytes,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    return _audio_file_to_pydantic(row)


async def list_audio_files(session: AsyncSession) -> list[AudioFile]:
    result = await session.execute(select(AudioFileRow).order_by(AudioFileRow.created_at.desc()))
    return [_audio_file_to_pydantic(r) for r in result.scalars()]


async def get_audio_file(session: AsyncSession, file_id: UUID) -> AudioFile | None:
    row = await session.get(AudioFileRow, str(file_id))
    return _audio_file_to_pydantic(row) if row else None


async def delete_audio_file(session: AsyncSession, file_id: UUID) -> bool:
    """Return False if any scene still references this file."""
    ref = await session.execute(
        select(LayerRow.id).where(LayerRow.audio_file_id == str(file_id)).limit(1)
    )
    if ref.first() is not None:
        return False
    row = await session.get(AudioFileRow, str(file_id))
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True


def _audio_file_to_pydantic(row: AudioFileRow) -> AudioFile:
    return AudioFile(
        id=UUID(row.id),
        original_name=row.original_name,
        path=row.path,
        duration_ms=row.duration_ms,
        sample_rate=row.sample_rate,
        channels=row.channels,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
    )


# ---- Scene -------------------------------------------------------------------


async def create_scene(session: AsyncSession, payload: SceneCreate) -> Scene:
    await _validate_scene_references(session, payload.layers, payload.on_end)
    now = datetime.now(UTC)
    scene_id = uuid4()
    row = SceneRow(
        id=str(scene_id),
        name=payload.name,
        description=payload.description,
        on_end_json=_on_end_to_json(payload.on_end),
        group_volumes_json=payload.group_volumes.model_dump_json(),
        created_at=now,
        updated_at=now,
    )
    row.layers = [_layer_config_to_row(layer, scene_id, i) for i, layer in enumerate(payload.layers)]
    session.add(row)
    await session.commit()
    return await _hydrate_scene(session, scene_id)


async def list_scenes(session: AsyncSession) -> list[Scene]:
    result = await session.execute(
        select(SceneRow).options(selectinload(SceneRow.layers)).order_by(SceneRow.name)
    )
    return [_scene_row_to_pydantic(r) for r in result.scalars()]


async def get_scene(session: AsyncSession, scene_id: UUID) -> Scene | None:
    result = await session.execute(
        select(SceneRow).options(selectinload(SceneRow.layers)).where(SceneRow.id == str(scene_id))
    )
    row = result.scalar_one_or_none()
    return _scene_row_to_pydantic(row) if row else None


async def update_scene(session: AsyncSession, scene_id: UUID, payload: SceneUpdate) -> Scene | None:
    result = await session.execute(
        select(SceneRow).options(selectinload(SceneRow.layers)).where(SceneRow.id == str(scene_id))
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    await _validate_scene_references(session, payload.layers, payload.on_end)
    if payload.name is not None:
        row.name = payload.name
    if payload.description is not None:
        row.description = payload.description
    if payload.on_end is not None:
        row.on_end_json = _on_end_to_json(payload.on_end)
    if payload.group_volumes is not None:
        row.group_volumes_json = payload.group_volumes.model_dump_json()
    if payload.layers is not None:
        row.layers = [_layer_config_to_row(layer, scene_id, i) for i, layer in enumerate(payload.layers)]
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return await _hydrate_scene(session, scene_id)


async def delete_scene(session: AsyncSession, scene_id: UUID) -> bool:
    row = await session.get(SceneRow, str(scene_id))
    if row is None:
        return False
    result = await session.execute(select(SceneRow.id, SceneRow.on_end_json))
    for source_id, raw_policy in result:
        if source_id == str(scene_id):
            continue
        policy = json.loads(raw_policy)
        if policy.get("type") == "goto" and policy.get("scene_id") == str(scene_id):
            raise InvalidReferenceError(f"scene is referenced by transition from {source_id}")
    await session.delete(row)
    await session.commit()
    return True


async def _hydrate_scene(session: AsyncSession, scene_id: UUID) -> Scene:
    scene = await get_scene(session, scene_id)
    assert scene is not None, "just-written scene should exist"
    return scene


def _layer_config_to_row(layer: LayerConfig, scene_id: UUID, position: int) -> LayerRow:
    return LayerRow(
        id=str(layer.id),
        scene_id=str(scene_id),
        audio_file_id=str(layer.audio_file_id),
        position=position,
        loop=layer.loop,
        volume=layer.volume,
        group_name=layer.group,
        pan_lr=layer.pan_lr,
        fade_in_ms=layer.fade_in_ms,
        fade_out_ms=layer.fade_out_ms,
        loop_start_ms=layer.loop_start_ms,
        loop_end_ms=layer.loop_end_ms,
    )


async def _validate_scene_references(
    session: AsyncSession,
    layers: list[LayerConfig] | None,
    on_end: OnEndPolicy | None,
) -> None:
    if layers is not None:
        requested = {str(layer.audio_file_id) for layer in layers}
        if requested:
            result = await session.execute(
                select(AudioFileRow.id).where(AudioFileRow.id.in_(requested))
            )
            existing = set(result.scalars())
            missing = sorted(requested - existing)
            if missing:
                raise InvalidReferenceError(f"audio files not found: {', '.join(missing)}")
    if isinstance(on_end, OnEndGoto):
        target = await session.get(SceneRow, str(on_end.scene_id))
        if target is None:
            raise InvalidReferenceError(f"transition target scene not found: {on_end.scene_id}")


def _scene_row_to_pydantic(row: SceneRow) -> Scene:
    return Scene(
        id=UUID(row.id),
        name=row.name,
        description=row.description,
        on_end=_on_end_from_json(row.on_end_json),
        group_volumes=GroupVolumes.model_validate_json(row.group_volumes_json),
        is_on_map=row.is_on_map,
        graph_x=row.graph_x,
        graph_y=row.graph_y,
        is_entry=row.is_entry,
        layers=[
            LayerConfig(
                id=UUID(layer.id),
                audio_file_id=UUID(layer.audio_file_id),
                group=layer.group_name,
                loop=layer.loop,
                volume=layer.volume,
                pan_lr=layer.pan_lr,
                fade_in_ms=layer.fade_in_ms,
                fade_out_ms=layer.fade_out_ms,
                loop_start_ms=layer.loop_start_ms,
                loop_end_ms=layer.loop_end_ms,
            )
            for layer in row.layers
        ],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def update_scene_position(
    session: AsyncSession, scene_id: UUID, x: float, y: float
) -> bool:
    row = await session.get(SceneRow, str(scene_id))
    if row is None:
        return False
    row.graph_x = x
    row.graph_y = y
    await session.commit()
    return True


async def set_entry_scene(session: AsyncSession, scene_id: UUID | None) -> bool:
    """Set the singleton campaign entry scene. Passing None clears it.
    Returns False if scene_id was given but doesn't exist."""
    if scene_id is not None:
        exists = await session.get(SceneRow, str(scene_id))
        if exists is None:
            return False
    # Clear all, then set the target — in a single commit so we never observe
    # two entry scenes simultaneously.
    await session.execute(update(SceneRow).values(is_entry=False))
    if scene_id is not None:
        await session.execute(
            update(SceneRow).where(SceneRow.id == str(scene_id)).values(is_entry=True)
        )
    await session.commit()
    return True


async def set_scene_on_map(
    session: AsyncSession,
    scene_id: UUID,
    on_map: bool,
    position: tuple[float, float] | None = None,
) -> bool:
    row = await session.get(SceneRow, str(scene_id))
    if row is None:
        return False
    row.is_on_map = on_map
    if position is not None:
        row.graph_x, row.graph_y = position
    if not on_map:
        # Taking a scene off the map: reset placement, its outgoing edge, AND
        # release the entry singleton if this was the entry scene. Re-adding
        # it later starts clean instead of resurrecting a stale start-edge.
        # (Incoming edges from other scenes are left alone — we don't silently
        # rewrite unrelated scenes.)
        row.graph_x = None
        row.graph_y = None
        row.on_end_json = _on_end_to_json(OnEndReturnPrevious())
        row.is_entry = False
    await session.commit()
    return True
