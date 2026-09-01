"""In-process asyncio event bus. ~40 lines by design.

Handlers are wrapped so one broken subscriber can't take down the publisher.
Future integrations (OBS, HA, MQTT) subscribe here without touching core code.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import TypeVar

from loremaster.events.types import Event

log = logging.getLogger(__name__)

E = TypeVar("E", bound=Event)
Handler = Callable[[E], Awaitable[None]]

_HANDLER_TIMEOUT_S = 5.0


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Handler]] = defaultdict(list)
        self._wildcard: list[Handler] = []

    def subscribe(self, event_type: type[E], handler: Handler[E]) -> None:
        self._handlers[event_type].append(handler)

    def subscribe_all(self, handler: Handler[Event]) -> None:
        """Subscribe to every event type — used by the WS broadcaster."""
        self._wildcard.append(handler)

    def publish(self, event: Event) -> None:
        """Fire-and-forget. Handlers run as separate tasks so a slow one
        doesn't block the publisher."""
        for handler in self._handlers.get(type(event), ()):
            asyncio.create_task(self._run(handler, event))
        for handler in self._wildcard:
            asyncio.create_task(self._run(handler, event))

    async def _run(self, handler: Handler, event: Event) -> None:
        try:
            await asyncio.wait_for(handler(event), timeout=_HANDLER_TIMEOUT_S)
        except TimeoutError:
            log.warning("event handler timed out: %s on %s", handler, type(event).__name__)
        except Exception:  # noqa: BLE001
            log.exception("event handler failed: %s on %s", handler, type(event).__name__)
