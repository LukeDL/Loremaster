"""ScenePlayer: coordinates the layers of one scene, handles transitions and on_end.

`on_end` policies:
- return_previous: crossfade back to the previously-playing scene
- goto:<scene_id>: crossfade to a specific scene (resolved via injected resolver)
- stop: fade everything out

End-of-combat with loop region
------------------------------
When a scene has layers with loop_start_ms/loop_end_ms set, `end_combat()`
first tells each such layer to exit its loop (playing the tail after
loop_end), then waits for those tails to finish naturally, then applies the
on_end policy. This is the Skyrim/Wwise "post-exit playback" pattern: you
hear the musical closure before ambient returns.
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

# Safety cap: no tail should keep the transition waiting forever.
_TAIL_TIMEOUT_S = 60.0


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
        # Layer id -> asyncio.Event that fires when the layer ends naturally.
        # Populated on play(), consumed by end_combat() to wait for the tail.
        self._ended_events: dict[str, asyncio.Event] = {}

    @property
    def current_scene(self) -> SceneSpec | None:
        return self._current

    @property
    def previous_scene(self) -> SceneSpec | None:
        return self._previous

    async def play(self, scene: SceneSpec) -> None:
        """Start a scene. If another scene is playing, crossfade into this one."""
        async with self._lock:
            log.info("scene play: %s (was %s)", scene.id, self._current.id if self._current else None)
            await self._fade_out_and_forget_current()
            loop = asyncio.get_running_loop()
            for layer_spec in scene.layers:
                scoped_id = _scoped(scene.id, layer_spec.id)
                event = asyncio.Event()
                self._ended_events[scoped_id] = event
                self.engine.play_layer(
                    scoped_id,
                    layer_spec,
                    on_ended=self._make_on_ended(loop, event),
                )
            if self._current is not None and self._current.id != scene.id:
                self._previous = self._current
            self._current = scene

    async def stop(self) -> None:
        async with self._lock:
            log.info("scene stop")
            await self._fade_out_and_forget_current()
            self._current = None

    async def end_combat(
        self,
        scene_resolver: Callable[[str], Awaitable["SceneSpec | None"]],
    ) -> None:
        """Apply the current scene's on_end policy.

        If the current scene has any layers with a loop region, first ask
        those layers to exit their loop and wait for the tail to finish
        before transitioning.
        """
        if self._current is None:
            return
        async with self._lock:
            await self._await_tails()
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

    # ---- internals ----------------------------------------------------------

    async def _await_tails(self) -> None:
        """Trigger exit-loop on layers that have a loop region and wait for
        their tails to reach EOF. Layers without a loop region are ignored
        here (they'll be crossfaded out normally when the next scene plays)."""
        if self._current is None:
            return
        tail_events: list[asyncio.Event] = []
        for spec in self._current.layers:
            if spec.loop_start_ms is None or spec.loop_end_ms is None:
                continue
            scoped_id = _scoped(self._current.id, spec.id)
            self.engine.exit_layer_loop(scoped_id)
            event = self._ended_events.get(scoped_id)
            if event is not None:
                tail_events.append(event)
        if not tail_events:
            return
        log.info("end_combat: waiting for %d tail(s) to finish", len(tail_events))
        try:
            await asyncio.wait_for(
                asyncio.gather(*(e.wait() for e in tail_events)),
                timeout=_TAIL_TIMEOUT_S,
            )
        except TimeoutError:
            log.warning("end_combat: tail timeout after %.1fs, transitioning anyway", _TAIL_TIMEOUT_S)

    async def _fade_out_and_forget_current(self) -> None:
        if self._current is None:
            return
        for layer_spec in self._current.layers:
            scoped_id = _scoped(self._current.id, layer_spec.id)
            self.engine.fade_out_layer(scoped_id)
            # Drop the ended-event for the old layer — a fade_out doesn't fire
            # our on_ended callback in a semantically useful way, and if the
            # layer ended earlier (e.g. tail already played) we don't need it.
            self._ended_events.pop(scoped_id, None)

    @staticmethod
    def _make_on_ended(loop: asyncio.AbstractEventLoop, event: asyncio.Event) -> Callable[[str], None]:
        """Wrap an asyncio.Event.set() so it can be called from the audio
        callback thread. asyncio primitives aren't thread-safe by themselves."""
        def _notify(_layer_id: str) -> None:
            loop.call_soon_threadsafe(event.set)
        return _notify


def _scoped(scene_id: str, layer_id: str) -> str:
    return f"{scene_id}::{layer_id}"
