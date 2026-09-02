"""Event payloads published on the in-process bus.

New event types are the extension point for future modules (OBS sync,
Hue/Home Assistant, MQTT bridge). Add a new class here, publish it from
the code that generates it, subscribe from the module that reacts to it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class _EventBase(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScenePlaybackStarted(_EventBase):
    type: Literal["scene_playback_started"] = "scene_playback_started"
    scene_id: UUID
    scene_name: str
    previous_scene_id: UUID | None = None


class ScenePlaybackStopped(_EventBase):
    type: Literal["scene_playback_stopped"] = "scene_playback_stopped"
    scene_id: UUID | None = None


class TransitionStarted(_EventBase):
    """Fired when a crossfade between scenes begins."""

    type: Literal["transition_started"] = "transition_started"
    from_scene_id: UUID | None
    to_scene_id: UUID


class SceneEnded(_EventBase):
    """Fired when the user triggers the "FIM DA CENA" button on a scene.
    Applies the scene's on_end policy (return_previous / goto / stop),
    playing the tail concurrently for layers with a loop region."""

    type: Literal["scene_ended"] = "scene_ended"
    scene_id: UUID


class VolumeChanged(_EventBase):
    type: Literal["volume_changed"] = "volume_changed"
    target: str  # "master" or layer id
    volume: float


class PlaybackStateSnapshot(_EventBase):
    """Periodic broadcast of engine state — used by the WS to keep clients in sync."""

    type: Literal["state"] = "state"
    current_scene_id: UUID | None
    previous_scene_id: UUID | None
    master_volume: float
    layers: dict[str, dict[str, Any]]
    xrun_count: int


Event = (
    ScenePlaybackStarted
    | ScenePlaybackStopped
    | TransitionStarted
    | SceneEnded
    | VolumeChanged
    | PlaybackStateSnapshot
)
