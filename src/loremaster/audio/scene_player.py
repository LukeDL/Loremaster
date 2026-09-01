"""ScenePlayer: coordinates the layers of one scene, handles transitions and on_end.

`on_end` policies:
- return_previous: crossfade back to the previously-playing scene
- goto:<scene_id>: crossfade to a specific scene (resolved by caller providing the SceneSpec)
- stop: fade everything out
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from loremaster.audio.engine import AudioEngine
from loremaster.audio.layer import LayerSpec

log = logging.getLogger(__name__)


OnEndType = Literal["return_previous", "goto", "stop"]


@dataclass
class OnEnd:
    type: OnEndType = "return_previous"
    goto_scene_id: str | None = None


@dataclass
class SceneSpec:
    """User-facing scene: id, name, and the layers it contains."""

    id: str
    name: str
    layers: list[LayerSpec] = field(default_factory=list)
    on_end: OnEnd = field(default_factory=OnEnd)


class ScenePlayer:
    def __init__(self, engine: AudioEngine) -> None:
        self.engine = engine
        self._current: SceneSpec | None = None
        self._previous: SceneSpec | None = None
        self._lock = asyncio.Lock()

    @property
    def current_scene(self) -> SceneSpec | None:
        return self._current

    @property
    def previous_scene(self) -> SceneSpec | None:
        return self._previous

    async def play(self, scene: SceneSpec) -> None:
        """Start a scene. If another scene is playing, crossfade into this one.

        Layer-level fade_in_ms/fade_out_ms provide the crossfade curves; the
        engine handles both fades simultaneously so there's no gap.
        """
        async with self._lock:
            log.info("scene play: %s (was %s)", scene.id, self._current.id if self._current else None)
            self._fade_out_current_layers()
            for layer_spec in scene.layers:
                # Namespace layer ids by scene id so a re-triggered scene
                # doesn't collide with the same layer name from another scene.
                self.engine.play_layer(_scoped(scene.id, layer_spec.id), layer_spec)
            if self._current is not None and self._current.id != scene.id:
                self._previous = self._current
            self._current = scene

    async def stop(self) -> None:
        async with self._lock:
            log.info("scene stop")
            self._fade_out_current_layers()
            self._current = None

    async def end_combat(
        self,
        scene_resolver: Callable[[str], Awaitable["SceneSpec | None"]],
    ) -> None:
        """Apply the current scene's on_end policy.

        The resolver looks up a scene by id — injected so the player doesn't
        need to know about persistence.
        """
        if self._current is None:
            return
        policy = self._current.on_end
        if policy.type == "return_previous":
            target = self._previous
            if target is None:
                log.info("end_combat: return_previous but no previous scene, stopping")
                await self.stop()
                return
            await self.play(target)
        elif policy.type == "goto":
            if policy.goto_scene_id is None:
                log.warning("end_combat: goto policy without scene_id, stopping")
                await self.stop()
                return
            target = await scene_resolver(policy.goto_scene_id)
            if target is None:
                log.warning("end_combat: goto target %s not found, stopping", policy.goto_scene_id)
                await self.stop()
                return
            await self.play(target)
        else:  # stop
            await self.stop()

    def _fade_out_current_layers(self) -> None:
        if self._current is None:
            return
        for layer_spec in self._current.layers:
            self.engine.fade_out_layer(_scoped(self._current.id, layer_spec.id))


def _scoped(scene_id: str, layer_id: str) -> str:
    return f"{scene_id}::{layer_id}"
