"""WebSocket endpoint: broadcasts every bus event + periodic state snapshots."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from loremaster.events import Event, EventBus, PlaybackStateSnapshot
from loremaster.scene_service import SceneService

log = logging.getLogger(__name__)

router = APIRouter()

# Broadcast state every 500 ms so tablet UIs can show live layer positions
STATE_INTERVAL_S = 0.5


class WsBroadcaster:
    """Fan-out queue: subscribe once to the bus, deliver to N websocket clients."""

    def __init__(self, bus: EventBus, service: SceneService) -> None:
        self.bus = bus
        self.service = service
        self._clients: set[WebSocket] = set()
        self._state_task: asyncio.Task | None = None
        bus.subscribe_all(self._on_event)

    def start(self) -> None:
        if self._state_task is None:
            self._state_task = asyncio.create_task(self._state_loop())

    async def stop(self) -> None:
        if self._state_task is not None:
            self._state_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._state_task
            self._state_task = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)
        # Send current state immediately so the new client isn't blank
        await self._send(ws, self._state_message())

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def _on_event(self, event: Event) -> None:
        message = event.model_dump(mode="json")
        await self._broadcast(message)

    async def _state_loop(self) -> None:
        while True:
            await asyncio.sleep(STATE_INTERVAL_S)
            await self._broadcast(self._state_message())

    def _state_message(self) -> dict[str, Any]:
        snap = self.service.snapshot()
        return PlaybackStateSnapshot(
            current_scene_id=snap["current_scene_id"],
            previous_scene_id=snap["previous_scene_id"],
            master_volume=snap["master_volume"],
            layers=snap["layers"],
            xrun_count=snap["xrun_count"],
        ).model_dump(mode="json")

    async def _broadcast(self, message: dict[str, Any]) -> None:
        if not self._clients:
            return
        dead: list[WebSocket] = []
        for ws in self._clients:
            try:
                await self._send(ws, message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)

    @staticmethod
    async def _send(ws: WebSocket, message: dict[str, Any]) -> None:
        await ws.send_text(json.dumps(message, default=str))


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    broadcaster: WsBroadcaster = ws.app.state.ws_broadcaster
    await broadcaster.connect(ws)
    try:
        # No client-to-server protocol beyond keepalive; drain and ignore.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.disconnect(ws)
