"""FastAPI dependency shims — the app populates these at startup."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from loremaster.events import EventBus
    from loremaster.models.db import Database
    from loremaster.scene_service import SceneService


def get_db(request: Request) -> "Database":
    return request.app.state.db


def get_bus(request: Request) -> "EventBus":
    return request.app.state.bus


def get_scene_service(request: Request) -> "SceneService":
    return request.app.state.scene_service


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    db = get_db(request)
    async with db.session() as sess:
        yield sess
