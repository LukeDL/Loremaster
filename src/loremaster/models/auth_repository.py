"""Persistence operations for users and opaque database-backed sessions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from loremaster.models.auth import Role, UserPublic
from loremaster.models.db import SessionRow, UserRow
from loremaster.security import generate_token, hash_password, normalize_username, token_hash


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def public_user(row: UserRow) -> UserPublic:
    return UserPublic(
        id=row.id,
        username=row.username,
        role=Role(row.role),
        is_active=row.is_active,
        created_at=row.created_at,
    )


async def create_user(
    sess: AsyncSession,
    *,
    username: str,
    password: str,
    role: Role,
) -> UserRow:
    now = utcnow()
    row = UserRow(
        id=str(uuid4()),
        username=username.strip(),
        username_key=normalize_username(username),
        password_hash=await asyncio.to_thread(hash_password, password),
        role=role.value,
        is_active=True,
        created_at=now,
        updated_at=now,
        password_changed_at=now,
    )
    sess.add(row)
    await sess.commit()
    await sess.refresh(row)
    return row


async def get_user_by_username(sess: AsyncSession, username: str) -> UserRow | None:
    result = await sess.execute(
        select(UserRow).where(UserRow.username_key == normalize_username(username))
    )
    return result.scalar_one_or_none()


async def get_user(sess: AsyncSession, user_id: str) -> UserRow | None:
    return await sess.get(UserRow, user_id)


async def list_users(sess: AsyncSession) -> list[UserRow]:
    result = await sess.execute(select(UserRow).order_by(UserRow.username_key))
    return list(result.scalars())


async def active_gm_count(sess: AsyncSession) -> int:
    result = await sess.execute(
        select(func.count()).select_from(UserRow).where(
            UserRow.role == Role.GM.value,
            UserRow.is_active.is_(True),
        )
    )
    return int(result.scalar_one())


async def set_user_active(sess: AsyncSession, row: UserRow, active: bool) -> None:
    row.is_active = active
    row.updated_at = utcnow()
    if not active:
        await sess.execute(delete(SessionRow).where(SessionRow.user_id == row.id))
    await sess.commit()


async def reset_password(sess: AsyncSession, row: UserRow, password: str) -> None:
    now = utcnow()
    row.password_hash = await asyncio.to_thread(hash_password, password)
    row.password_changed_at = now
    row.updated_at = now
    await sess.execute(delete(SessionRow).where(SessionRow.user_id == row.id))
    await sess.commit()


async def create_session(
    sess: AsyncSession,
    *,
    user_id: str,
    lifetime_hours: int,
) -> tuple[str, str, datetime]:
    session_token = generate_token()
    csrf_token = generate_token()
    now = utcnow()
    expires_at = now + timedelta(hours=lifetime_hours)
    sess.add(
        SessionRow(
            token_hash=token_hash(session_token),
            user_id=user_id,
            csrf_hash=token_hash(csrf_token),
            created_at=now,
            expires_at=expires_at,
            last_seen_at=now,
        )
    )
    await sess.commit()
    return session_token, csrf_token, expires_at


async def get_session_user(
    sess: AsyncSession,
    session_token: str,
) -> tuple[SessionRow, UserRow] | None:
    result = await sess.execute(
        select(SessionRow)
        .options(selectinload(SessionRow.user))
        .where(SessionRow.token_hash == token_hash(session_token))
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    if session.expires_at <= utcnow() or not session.user.is_active:
        await sess.delete(session)
        await sess.commit()
        return None
    return session, session.user


async def revoke_session(sess: AsyncSession, session_token: str) -> None:
    await sess.execute(
        delete(SessionRow).where(SessionRow.token_hash == token_hash(session_token))
    )
    await sess.commit()
