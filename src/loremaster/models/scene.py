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
    """One layer within a scene — references an AudioFile by id."""

    id: UUID = Field(default_factory=uuid4)
    audio_file_id: UUID
    loop: bool = True
    volume: float = Field(default=1.0, ge=0.0, le=1.0)
    fade_in_ms: int = Field(default=500, ge=0, le=60_000)
    fade_out_ms: int = Field(default=500, ge=0, le=60_000)


class Scene(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    layers: list[LayerConfig] = Field(default_factory=list)
    on_end: OnEndPolicy = Field(default_factory=OnEndReturnPrevious)
    is_on_map: bool = False
    graph_x: float | None = None
    graph_y: float | None = None
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
