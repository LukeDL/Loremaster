"""Pydantic models — the API contract for scenes and audio files."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class OnEndReturnPrevious(BaseModel):
    type: Literal["return_previous"] = "return_previous"


class OnEndGoto(BaseModel):
    type: Literal["goto"] = "goto"
    scene_id: UUID


class OnEndStop(BaseModel):
    type: Literal["stop"] = "stop"


OnEndPolicy = Annotated[
    OnEndReturnPrevious | OnEndGoto | OnEndStop,
    Field(discriminator="type"),
]


class AudioFile(BaseModel):
    id: UUID
    original_name: str
    path: str  # relative to settings.audio_dir
    duration_ms: int
    sample_rate: int
    channels: int
    size_bytes: int
    created_at: datetime


class LayerConfig(BaseModel):
    """One layer within a scene — references an AudioFile by id.

    Loop region (Skyrim/Wwise style, optional): when both loop_start_ms and
    loop_end_ms are set, playback loops between them; everything before
    loop_start_ms is an intro (plays once), everything after loop_end_ms is
    a tail that plays when the scene's on_end fires.
    """

    id: UUID = Field(default_factory=uuid4)
    audio_file_id: UUID
    loop: bool = True
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    fade_in_ms: int = Field(default=500, ge=0, le=60_000)
    fade_out_ms: int = Field(default=500, ge=0, le=60_000)
    loop_start_ms: int | None = Field(default=None, ge=0)
    loop_end_ms: int | None = Field(default=None, ge=0)


class Scene(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    layers: list[LayerConfig] = Field(default_factory=list)
    on_end: OnEndPolicy = Field(default_factory=OnEndReturnPrevious)
    is_on_map: bool = False
    graph_x: float | None = None
    graph_y: float | None = None
    # Singleton flag: at most one scene has is_entry=True at a time.
    # Managed exclusively via PUT /api/entry_scene, not via SceneUpdate.
    is_entry: bool = False
    created_at: datetime
    updated_at: datetime


class SceneCreate(BaseModel):
    """Payload for POST /api/scenes — no server-managed fields."""

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    layers: list[LayerConfig] = Field(default_factory=list)
    on_end: OnEndPolicy = Field(default_factory=OnEndReturnPrevious)


class SceneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    layers: list[LayerConfig] | None = None
    on_end: OnEndPolicy | None = None
