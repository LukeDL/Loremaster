"""ScenePlayer: coordinates the layers of one scene, handles transitions and on_end.

`on_end` policies:
- return_previous: crossfade back to the previously-playing scene
- goto:<scene_id>: crossfade to a specific scene (resolved via injected resolver)
- stop: fade everything out

FIM DA CENA with loop region (M14)
----------------------------------
When a scene has layers with `loop_start_ms`/`loop_end_ms` set, `end_scene()`
tells the engine to *jump* each of those layers directly to their tail
(`loop_end` -> EOF) via a short crossfade — no matter where the loop cursor
currently is. Immediately after, it applies the `on_end` policy, so the tail
and the next scene's fade-in play concurrently.

This replaces the pre-M14 behavior that waited (with the player lock held)
for tails to reach EOF — see issue #4.
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

# Duration of the loop -> tail crossfade. Short and predictable, per the
# design conversation for M14. Not user-configurable (yet).
_TAIL_CROSSFADE_MS = 300


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
    layer_groups: dict[str, str] = field(default_factory=dict)
    layer_volumes: dict[str, float] = field(default_factory=dict)
    group_volumes: dict[str, float] = field(default_factory=dict)
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
        """Start a scene. If another scene is playing, crossfade into this one."""
        async with self._lock:
            await self._play_locked(scene)

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def end_scene(
        self,
        scene_resolver: Callable[[str], Awaitable["SceneSpec | None"]],
    ) -> None:
        """Apply the current scene's on_end policy.

        For layers with a loop region: enqueue a jump-to-tail (short crossfade
        from the current loop position to a fresh Layer starting at loop_end).
        For layers without: they'll be crossfaded out by the transition below.

        The tail plays concurrently with the next scene's fade-in — we don't
        wait for it. The whole method holds the lock for a short, bounded
        window (just command enqueue + resolver hydration + play/stop), which
        is the fix for issue #4."""
        if self._current is None:
            return
        async with self._lock:
            for spec in self._current.layers:
                if spec.loop_start_ms is None or spec.loop_end_ms is None:
                    continue
                scoped_id = _scoped(self._current.id, spec.id)
                tail_id = _tail_id(self._current.id, spec.id)
                self.engine.jump_to_tail(
                    scoped_id, tail_id, tail_fade_ms=_TAIL_CROSSFADE_MS,
                )
            policy = self._current.on_end
            current_id = self._current.id
            previous = self._previous
            # Apply the policy inline while still holding the lock. Any
            # subsequent play/stop from the user queues up behind us and runs
            # after — the intended sequential behavior.
            if policy.type == "stop":
                log.info("end_scene: stop")
                self._finish_current_locked()
                return
            if policy.type == "return_previous":
                target = previous
                if target is None or target.id == current_id:
                    log.info("end_scene: return_previous with no valid previous, stopping")
                    self._finish_current_locked()
                    return
            else:  # goto
                if policy.goto_scene_id is None:
                    log.warning("end_scene: goto policy without scene_id, stopping")
                    self._finish_current_locked()
                    return
                target = await scene_resolver(policy.goto_scene_id)
                if target is None:
                    log.warning("end_scene: goto target %s not found, stopping", policy.goto_scene_id)
                    self._finish_current_locked()
                    return
            await self._play_locked(target)

    # ---- internals ----------------------------------------------------------

    async def _play_locked(self, scene: SceneSpec) -> None:
        """Play under the assumption that the caller holds ``self._lock``."""
        log.info("scene play: %s (was %s)", scene.id, self._current.id if self._current else None)
        await self._fade_out_and_forget_current()
        for layer_spec in scene.layers:
            scoped_id = _scoped(scene.id, layer_spec.id)
            self.engine.play_layer(scoped_id, layer_spec)
        if self._current is not None and self._current.id != scene.id:
            self._previous = self._current
        self._current = scene

    async def _stop_locked(self) -> None:
        log.info("scene stop")
        # Fade EVERY active layer, including tail sublayers spawned by an
        # earlier end_scene. When the user hits ■ they want silence.
        self.engine.stop_all()
        self._current = None

    def _finish_current_locked(self) -> None:
        """End by policy while preserving tail sublayers spawned above."""
        if self._current is None:
            return
        for layer_spec in self._current.layers:
            if layer_spec.loop_start_ms is None or layer_spec.loop_end_ms is None:
                self.engine.fade_out_layer(_scoped(self._current.id, layer_spec.id))
        self._current = None

    async def _fade_out_and_forget_current(self) -> None:
        if self._current is None:
            return
        for layer_spec in self._current.layers:
            scoped_id = _scoped(self._current.id, layer_spec.id)
            self.engine.fade_out_layer(scoped_id)
        # Tail sublayers (spawned by jump_to_tail) are intentionally left
        # alone here — they play to EOF and get removed by the engine.


def _scoped(scene_id: str, layer_id: str) -> str:
    return f"{scene_id}::{layer_id}"


def _tail_id(scene_id: str, layer_id: str) -> str:
    # Distinct id so the engine treats the tail as a new independent layer
    # instead of crossfading it against the original.
    return f"{scene_id}::{layer_id}::__tail"
