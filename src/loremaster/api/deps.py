"""FastAPI dependency shims — the app populates these at startup."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from loremaster.config import settings
from loremaster.models.auth import Role
from loremaster.models.auth_repository import get_session_user
from loremaster.models.db import SessionRow, UserRow
from loremaster.security import tokens_match

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


@dataclass(frozen=True)
class AuthContext:
    session: SessionRow
    user: UserRow


async def auth_context_from_token(request: Request, token: str | None) -> AuthContext | None:
    if not token:
        return None
    db = get_db(request)
    async with db.session() as sess:
        found = await get_session_user(sess, token)
    if found is None:
        return None
    session, user = found
    return AuthContext(session=session, user=user)


async def get_auth_context(request: Request) -> AuthContext | None:
    return await auth_context_from_token(
        request,
        request.cookies.get(settings.session_cookie_name),
    )


async def require_authenticated(
    context: AuthContext | None = Depends(get_auth_context),
) -> AuthContext:
    if context is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    return context


async def require_gm(
    context: AuthContext = Depends(require_authenticated),
) -> AuthContext:
    if context.user.role != Role.GM.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "gm access required")
    return context


async def require_csrf(
    request: Request,
    context: AuthContext = Depends(require_authenticated),
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get("X-CSRF-Token")
    if (
        not cookie_token
        or not header_token
        or cookie_token != header_token
        or not tokens_match(header_token, context.session.csrf_hash)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid csrf token")
