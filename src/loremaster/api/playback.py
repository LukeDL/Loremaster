"""Playback control endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from loremaster.api.deps import get_scene_service
from loremaster.scene_service import SceneService

router = APIRouter(prefix="/api/playback", tags=["playback"])


class PlayRequest(BaseModel):
    scene_id: UUID


class VolumeRequest(BaseModel):
    target: str = Field(description='"master" or a layer id')
    volume: float = Field(ge=0.0, le=1.0)


class LayerPatchRequest(BaseModel):
    """Fields left as None are not modified. Bare `id` (unscoped) — the service
    scopes it to the current scene."""

    volume: float | None = Field(default=None, ge=0.0, le=1.0)
    pan_lr: float | None = Field(default=None, ge=-1.0, le=1.0)


@router.post("/play", status_code=status.HTTP_202_ACCEPTED)
async def play(
    payload: PlayRequest,
    service: SceneService = Depends(get_scene_service),
) -> dict[str, str]:
    scene = await service.play_scene(payload.scene_id)
    if scene is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "scene not found")
    return {"scene_id": str(scene.id), "name": scene.name}


@router.post("/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop(service: SceneService = Depends(get_scene_service)) -> dict[str, str]:
    await service.stop_playback()
    return {"status": "stopping"}


@router.post("/end_scene", status_code=status.HTTP_202_ACCEPTED)
async def end_scene(service: SceneService = Depends(get_scene_service)) -> dict[str, str]:
    await service.end_scene()
    return {"status": "on_end_triggered"}


@router.post("/volume", status_code=status.HTTP_202_ACCEPTED)
async def volume(
    payload: VolumeRequest,
    service: SceneService = Depends(get_scene_service),
) -> dict[str, str]:
    if payload.target == "master":
        service.set_master_volume(payload.volume)
    else:
        service.set_layer_volume(payload.target, payload.volume)
    return {"status": "ok"}


@router.patch("/layers/{layer_id}", status_code=status.HTTP_202_ACCEPTED)
async def patch_layer(
    layer_id: str,
    payload: LayerPatchRequest,
    service: SceneService = Depends(get_scene_service),
) -> dict[str, str]:
    if payload.volume is not None:
        service.set_layer_volume(layer_id, payload.volume)
    if payload.pan_lr is not None:
        service.set_layer_pan(layer_id, payload.pan_lr)
    return {"status": "ok"}


@router.get("/state")
def state(service: SceneService = Depends(get_scene_service)) -> dict[str, Any]:
    return service.snapshot()
