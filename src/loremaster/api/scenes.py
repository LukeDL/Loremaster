"""Scene CRUD endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from pydantic import BaseModel

from loremaster.api.deps import db_session
from loremaster.models.repository import (
    InvalidReferenceError,
    create_scene,
    delete_scene,
    get_scene,
    list_scenes,
    set_entry_scene,
    set_scene_on_map,
    update_scene,
    update_scene_position,
)
from loremaster.models.scene import OnEndPolicy, Scene, SceneCreate, SceneUpdate

router = APIRouter(prefix="/api/scenes", tags=["scenes"])
# Separate router for the singleton entry-scene resource: it doesn't hang off
# a specific /scenes/{id}, so it gets its own prefix.
singletons_router = APIRouter(prefix="/api", tags=["scenes"])


class PositionPayload(BaseModel):
    x: float
    y: float


class OnEndPayload(BaseModel):
    on_end: OnEndPolicy


class OnMapPayload(BaseModel):
    is_on_map: bool
    x: float | None = None
    y: float | None = None


@router.get("", response_model=list[Scene])
async def list_all(sess: AsyncSession = Depends(db_session)) -> list[Scene]:
    return await list_scenes(sess)


@router.post("", response_model=Scene, status_code=status.HTTP_201_CREATED)
async def create(payload: SceneCreate, sess: AsyncSession = Depends(db_session)) -> Scene:
    try:
        return await create_scene(sess, payload)
    except InvalidReferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/{scene_id}", response_model=Scene)
async def retrieve(scene_id: UUID, sess: AsyncSession = Depends(db_session)) -> Scene:
    scene = await get_scene(sess, scene_id)
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
    return scene


@router.put("/{scene_id}", response_model=Scene)
async def update(
    scene_id: UUID,
    payload: SceneUpdate,
    sess: AsyncSession = Depends(db_session),
) -> Scene:
    try:
        scene = await update_scene(sess, scene_id, payload)
    except InvalidReferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
    return scene


@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(scene_id: UUID, sess: AsyncSession = Depends(db_session)) -> None:
    try:
        deleted = await delete_scene(sess, scene_id)
    except InvalidReferenceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")


@router.patch("/{scene_id}/position", status_code=status.HTTP_204_NO_CONTENT)
async def set_position(
    scene_id: UUID,
    payload: PositionPayload,
    sess: AsyncSession = Depends(db_session),
) -> None:
    """Lightweight endpoint called on every node drag — avoids re-sending the
    whole scene payload."""
    updated = await update_scene_position(sess, scene_id, payload.x, payload.y)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")


@router.patch("/{scene_id}/map", status_code=status.HTTP_204_NO_CONTENT)
async def set_on_map(
    scene_id: UUID,
    payload: OnMapPayload,
    sess: AsyncSession = Depends(db_session),
) -> None:
    """Add/remove a scene from the campaign graph. Optionally sets the initial
    drop position (used when dragging from the palette to the canvas)."""
    position = (payload.x, payload.y) if payload.x is not None and payload.y is not None else None
    updated = await set_scene_on_map(sess, scene_id, payload.is_on_map, position)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")


@router.patch("/{scene_id}/on_end", response_model=Scene)
async def set_on_end(
    scene_id: UUID,
    payload: OnEndPayload,
    sess: AsyncSession = Depends(db_session),
) -> Scene:
    """Change only the on_end policy — used when the user draws/removes an
    edge on the campaign graph."""
    try:
        scene = await update_scene(sess, scene_id, SceneUpdate(on_end=payload.on_end))
    except InvalidReferenceError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
    return scene


class EntrySceneBody(BaseModel):
    scene_id: UUID | None = None


@singletons_router.put("/entry_scene", status_code=status.HTTP_204_NO_CONTENT)
async def set_entry(
    payload: EntrySceneBody,
    sess: AsyncSession = Depends(db_session),
) -> None:
    """Set the singleton campaign entry scene. Body {"scene_id": UUID | null}.
    Passing null clears the current entry. Called when the mestre connects the
    start node to a scene on the map (or removes that connection)."""
    ok = await set_entry_scene(sess, payload.scene_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
