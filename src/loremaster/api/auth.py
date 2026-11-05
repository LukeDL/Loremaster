"""Login, logout and current-session endpoints."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from loremaster.api.deps import AuthContext, db_session, require_authenticated, require_csrf
from loremaster.config import settings
from loremaster.models.auth import LoginRequest, LoginResponse
from loremaster.models.auth_repository import (
    create_session,
    get_user_by_username,
    public_user,
    revoke_session,
)
from loremaster.security import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    parsed = urlsplit(origin)
    if parsed.netloc != request.url.netloc or parsed.scheme != request.url.scheme:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid origin")


def _set_auth_cookies(
    response: Response,
    *,
    session_token: str,
    csrf_token: str,
) -> None:
    max_age = settings.session_lifetime_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    sess: AsyncSession = Depends(db_session),
) -> LoginResponse:
    _require_same_origin(request)
    user = await get_user_by_username(sess, payload.username)
    valid = await asyncio.to_thread(
        verify_password,
        payload.password,
        user.password_hash if user is not None else None,
    )
    if not valid or user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")
    session_token, csrf_token, _ = await create_session(
        sess,
        user_id=user.id,
        lifetime_hours=settings.session_lifetime_hours,
    )
    _set_auth_cookies(
        response,
        session_token=session_token,
        csrf_token=csrf_token,
    )
    return LoginResponse(user=public_user(user))


@router.get("/me", response_model=LoginResponse)
async def me(context: AuthContext = Depends(require_authenticated)) -> LoginResponse:
    return LoginResponse(user=public_user(context.user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    _: None = Depends(require_csrf),
    sess: AsyncSession = Depends(db_session),
) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await revoke_session(sess, token)
    _clear_auth_cookies(response)
