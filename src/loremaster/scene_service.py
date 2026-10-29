"""Bridges the persistence layer (DB) and the audio engine.

This is where a Scene row becomes a SceneSpec with decoded audio buffers.
API endpoints call into this service; the service owns the ScenePlayer and
emits events on the bus.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from loremaster.audio.engine import AudioEngine
from loremaster.audio.layer import LayerSpec
from loremaster.audio.loader import AudioLoader
from loremaster.audio.scene_player import OnEnd, ScenePlayer, SceneSpec
from loremaster.events import (
    EventBus,
    SceneEnded,
    ScenePlaybackStarted,
    ScenePlaybackStopped,
    TransitionStarted,
    VolumeChanged,
)
from loremaster.models.db import Database
from loremaster.models.repository import get_audio_file, get_scene, list_scenes, update_scene
from loremaster.models.scene import AudioGroup, GroupVolumes, OnEndGoto, Scene, SceneUpdate

log = logging.getLogger(__name__)


class SceneService:
    def __init__(
        self,
        engine: AudioEngine,
        loader: AudioLoader,
        player: ScenePlayer,
        db: Database,
        bus: EventBus,
        audio_dir: Path,
    ) -> None:
        self.engine = engine
        self.loader = loader
        self.player = player
        self.db = db
        self.bus = bus
        self.audio_dir = audio_dir

    async def validate_references(self) -> None:
        """Reject legacy scene graphs that point to missing scenes or files."""
        errors: list[str] = []
        async with self.db.session() as sess:
            scenes = await list_scenes(sess)
            scene_ids = {scene.id for scene in scenes}
            for scene in scenes:
                if isinstance(scene.on_end, OnEndGoto) and scene.on_end.scene_id not in scene_ids:
                    errors.append(
                        f"scene {scene.id} points to missing scene {scene.on_end.scene_id}"
                    )
                for layer in scene.layers:
                    audio = await get_audio_file(sess, layer.audio_file_id)
                    if audio is None:
                        errors.append(
                            f"scene {scene.id} points to missing audio row {layer.audio_file_id}"
                        )
                    elif not (self.audio_dir / audio.path).is_file():
                        errors.append(
                            f"scene {scene.id} points to missing audio file {audio.path}"
                        )
        if errors:
            raise RuntimeError("invalid scene references: " + "; ".join(errors))

    async def _hydrate(self, scene: Scene) -> SceneSpec:
        """Load audio files referenced by a Scene into an engine-ready SceneSpec."""
        layer_specs: list[LayerSpec] = []
        group_volumes = scene.group_volumes.model_dump()
        async with self.db.session() as sess:
            for layer in scene.layers:
                audio = await get_audio_file(sess, layer.audio_file_id)
                if audio is None:
                    raise RuntimeError(
                        f"scene {scene.id} references missing audio {layer.audio_file_id}"
                    )
                loaded = self.loader.load(self.audio_dir / audio.path)
                layer_specs.append(
                    LayerSpec(
                        id=str(layer.id),
                        data=loaded.data,
                        loop=layer.loop,
                        volume=layer.volume * group_volumes[layer.group],
                        pan_lr=layer.pan_lr,
                        fade_in_ms=layer.fade_in_ms,
                        fade_out_ms=layer.fade_out_ms,
                        loop_start_ms=layer.loop_start_ms,
                        loop_end_ms=layer.loop_end_ms,
                    )
                )
        on_end = OnEnd(
            type=scene.on_end.type,
            goto_scene_id=str(scene.on_end.scene_id) if isinstance(scene.on_end, OnEndGoto) else None,
        )
        return SceneSpec(
            id=str(scene.id),
            name=scene.name,
            layers=layer_specs,
            layer_groups={str(layer.id): layer.group for layer in scene.layers},
            layer_volumes={str(layer.id): layer.volume for layer in scene.layers},
            group_volumes=group_volumes,
            on_end=on_end,
        )

    async def _resolve_by_str_id(self, scene_id_str: str) -> SceneSpec | None:
        try:
            scene_id = UUID(scene_id_str)
        except ValueError:
            return None
        async with self.db.session() as sess:
            scene = await get_scene(sess, scene_id)
        if scene is None:
            return None
        return await self._hydrate(scene)

    # ---- Playback commands ---------------------------------------------------

    async def play_scene(self, scene_id: UUID) -> Scene | None:
        async with self.db.session() as sess:
            scene = await get_scene(sess, scene_id)
        if scene is None:
            return None

        previous = self.player.current_scene
        previous_id = UUID(previous.id) if previous else None

        spec = await self._hydrate(scene)
        if previous is not None and previous.id != spec.id:
            self.bus.publish(TransitionStarted(from_scene_id=previous_id, to_scene_id=scene_id))
        await self.player.play(spec)
        self.bus.publish(
            ScenePlaybackStarted(
                scene_id=scene_id,
                scene_name=scene.name,
                previous_scene_id=previous_id,
            )
        )
        return scene

    async def stop_playback(self) -> None:
        current = self.player.current_scene
        current_id = UUID(current.id) if current else None
        await self.player.stop()
        self.bus.publish(ScenePlaybackStopped(scene_id=current_id))

    async def end_scene(self) -> None:
        current = self.player.current_scene
        if current is None:
            return
        current_id = UUID(current.id)
        self.bus.publish(SceneEnded(scene_id=current_id))
        await self.player.end_scene(self._resolve_by_str_id)

    def set_master_volume(self, volume: float) -> None:
        self.engine.set_master_volume(volume)
        self.bus.publish(VolumeChanged(target="master", volume=volume))

    def set_layer_volume(self, layer_id: str, volume: float) -> bool:
        current = self.player.current_scene
        if current is None or layer_id not in current.layer_volumes:
            return False
        current.layer_volumes[layer_id] = volume
        group = current.layer_groups[layer_id]
        effective_volume = volume * current.group_volumes[group]
        # Layer ids are scoped by scene in the engine
        self.engine.set_layer_volume(f"{current.id}::{layer_id}", effective_volume)
        self.bus.publish(VolumeChanged(target=layer_id, volume=volume))
        return True

    def set_layer_pan(self, layer_id: str, pan_lr: float) -> bool:
        current = self.player.current_scene
        if current is None or layer_id not in current.layer_volumes:
            return False
        # No dedicated bus event — pan changes propagate via the periodic
        # PlaybackStateSnapshot (layers[layer_id].pan_lr).
        self.engine.set_layer_pan(f"{current.id}::{layer_id}", pan_lr)
        return True

    async def set_group_volume(self, group: AudioGroup, volume: float) -> bool:
        current = self.player.current_scene
        if current is None:
            return False
        current.group_volumes[group] = volume
        for layer_id, layer_group in current.layer_groups.items():
            if layer_group != group:
                continue
            effective_volume = current.layer_volumes[layer_id] * volume
            self.engine.set_layer_volume(f"{current.id}::{layer_id}", effective_volume)
        async with self.db.session() as sess:
            await update_scene(
                sess,
                UUID(current.id),
                SceneUpdate(group_volumes=GroupVolumes(**current.group_volumes)),
            )
        return True

    # ---- State snapshot ------------------------------------------------------

    def snapshot(self) -> dict:
        current = self.player.current_scene
        previous = self.player.previous_scene
        engine_snap = self.engine.snapshot()
        return {
            "current_scene_id": current.id if current else None,
            "previous_scene_id": previous.id if previous else None,
            "master_volume": engine_snap["master_volume"],
            "group_volumes": dict(current.group_volumes) if current else GroupVolumes().model_dump(),
            "layers": engine_snap["layers"],
            "xrun_count": engine_snap["xrun_count"],
        }
