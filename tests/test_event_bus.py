"""Event bus: fan-out, wildcard, error isolation."""

from __future__ import annotations

import asyncio

import pytest

from loremaster.events.bus import EventBus
from loremaster.events.types import SceneEnded, ScenePlaybackStopped, VolumeChanged
from uuid import uuid4


@pytest.mark.asyncio
async def test_publish_to_typed_subscribers():
    bus = EventBus()
    received: list[VolumeChanged] = []

    async def handle(event: VolumeChanged) -> None:
        received.append(event)

    bus.subscribe(VolumeChanged, handle)
    bus.publish(VolumeChanged(target="master", volume=0.7))
    bus.publish(ScenePlaybackStopped())  # different type — should be ignored

    await asyncio.sleep(0.05)
    assert len(received) == 1
    assert received[0].volume == 0.7


@pytest.mark.asyncio
async def test_wildcard_subscriber_gets_everything():
    bus = EventBus()
    seen: list[type] = []

    async def handle_all(event) -> None:
        seen.append(type(event))

    bus.subscribe_all(handle_all)
    bus.publish(VolumeChanged(target="master", volume=1.0))
    bus.publish(SceneEnded(scene_id=uuid4()))

    await asyncio.sleep(0.05)
    assert VolumeChanged in seen
    assert SceneEnded in seen


@pytest.mark.asyncio
async def test_broken_handler_does_not_break_others():
    bus = EventBus()
    reached: list[int] = []

    async def broken(event) -> None:
        raise RuntimeError("boom")

    async def working(event) -> None:
        reached.append(1)

    bus.subscribe(VolumeChanged, broken)
    bus.subscribe(VolumeChanged, working)
    bus.publish(VolumeChanged(target="master", volume=0.5))

    await asyncio.sleep(0.05)
    assert reached == [1]
