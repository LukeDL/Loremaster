"""GM-only player account administration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from loremaster.api.deps import require_csrf, require_gm, db_session
from loremaster.models.auth import (
    CreateUserRequest,
    ResetPasswordRequest,
    Role,
    UpdateUserRequest,
    UserPublic,
)
from loremaster.models.auth_repository import (
    active_gm_count,
    create_user,
    get_user,
    list_users,
    public_user,
    reset_password,
    set_user_active,
)

router = APIRouter(
    prefix="/api/admin/users",
    tags=["users"],
    dependencies=[Depends(require_gm), Depends(require_csrf)],
)


@router.get("", response_model=list[UserPublic])
async def all_users(sess: AsyncSession = Depends(db_session)) -> list[UserPublic]:
    return [public_user(row) for row in await list_users(sess)]


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def add_player(
    payload: CreateUserRequest,
    sess: AsyncSession = Depends(db_session),
) -> UserPublic:
    if payload.role != Role.PLAYER:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "only player accounts can be created here")
    try:
        user = await create_user(
            sess,
            username=payload.username,
            password=payload.password,
            role=Role.PLAYER,
        )
    except IntegrityError as exc:
        await sess.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists") from exc
    return public_user(user)


@router.patch("/{user_id}", response_model=UserPublic)
async def update_player(
    user_id: str,
    payload: UpdateUserRequest,
    sess: AsyncSession = Depends(db_session),
) -> UserPublic:
    user = await get_user(sess, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if not payload.is_active and user.role == Role.GM.value and await active_gm_count(sess) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot disable the last active gm")
    await set_user_active(sess, user, payload.is_active)
    return public_user(user)


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    user_id: str,
    payload: ResetPasswordRequest,
    sess: AsyncSession = Depends(db_session),
) -> None:
    user = await get_user(sess, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    await reset_password(sess, user, payload.password)
