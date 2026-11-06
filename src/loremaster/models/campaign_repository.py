"""Persistence operations for campaigns, memberships and rule-pack metadata."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from loremaster.models.auth import Role
from loremaster.models.auth_repository import utcnow
from loremaster.models.campaign import (
    CampaignLifecycle,
    CampaignMemberPublic,
    CampaignPublic,
    RulePackPublic,
)
from loremaster.models.db import (
    CampaignMemberRow,
    CampaignRow,
    CharacterVersionRow,
    RulePackRow,
    UserRow,
)


def public_rule_pack(row: RulePackRow) -> RulePackPublic:
    return RulePackPublic(
        id=row.id,
        key=row.key,
        name=row.name,
        system=row.system,
        edition=row.edition,
        version=row.version,
        license_name=row.license_name,
    )


def public_campaign(row: CampaignRow) -> CampaignPublic:
    members = sorted(
        (
            CampaignMemberPublic(id=membership.user.id, username=membership.user.username)
            for membership in row.memberships
        ),
        key=lambda member: member.username.casefold(),
    )
    return CampaignPublic(
        id=row.id,
        name=row.name,
        rule_pack=public_rule_pack(row.rule_pack),
        max_characters_per_player=row.max_characters_per_player,
        starting_level=row.starting_level,
        lifecycle=CampaignLifecycle(row.lifecycle),
        is_active=row.is_active,
        members=members,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _campaign_query():
    return select(CampaignRow).options(
        selectinload(CampaignRow.rule_pack),
        selectinload(CampaignRow.memberships).selectinload(CampaignMemberRow.user),
    )


async def list_rule_packs(sess: AsyncSession) -> list[RulePackRow]:
    result = await sess.execute(
        select(RulePackRow).order_by(RulePackRow.system, RulePackRow.edition, RulePackRow.version)
    )
    return list(result.scalars())


async def get_rule_pack(sess: AsyncSession, rule_pack_id: str) -> RulePackRow | None:
    return await sess.get(RulePackRow, rule_pack_id)


async def list_campaigns(sess: AsyncSession) -> list[CampaignRow]:
    result = await sess.execute(_campaign_query().order_by(CampaignRow.name, CampaignRow.id))
    return list(result.scalars().unique())


async def get_campaign(sess: AsyncSession, campaign_id: str) -> CampaignRow | None:
    result = await sess.execute(_campaign_query().where(CampaignRow.id == campaign_id))
    return result.scalars().unique().one_or_none()


async def valid_player_ids(sess: AsyncSession, user_ids: list[str]) -> set[str]:
    if not user_ids:
        return set()
    result = await sess.execute(
        select(UserRow.id).where(
            UserRow.id.in_(user_ids),
            UserRow.role == Role.PLAYER.value,
            UserRow.is_active.is_(True),
        )
    )
    return set(result.scalars())


async def create_campaign(
    sess: AsyncSession,
    *,
    name: str,
    rule_pack_id: str,
    starting_level: int,
    max_characters_per_player: int,
    member_ids: list[str],
    activate: bool,
    created_by_user_id: str,
) -> CampaignRow:
    now = utcnow()
    existing = await sess.scalar(select(CampaignRow.id).limit(1))
    should_activate = activate or existing is None
    if should_activate:
        await sess.execute(update(CampaignRow).values(is_active=False, updated_at=now))
    campaign = CampaignRow(
        id=str(uuid4()),
        name=name,
        rule_pack_id=rule_pack_id,
        starting_level=starting_level,
        lifecycle=CampaignLifecycle.PLANNING.value,
        max_characters_per_player=max_characters_per_player,
        is_active=should_activate,
        created_by_user_id=created_by_user_id,
        created_at=now,
        updated_at=now,
    )
    sess.add(campaign)
    for user_id in member_ids:
        sess.add(CampaignMemberRow(campaign_id=campaign.id, user_id=user_id, added_at=now))
    await sess.commit()
    loaded = await get_campaign(sess, campaign.id)
    assert loaded is not None
    return loaded


async def update_campaign(
    sess: AsyncSession,
    row: CampaignRow,
    *,
    name: str | None,
    max_characters_per_player: int | None,
    starting_level: int | None,
) -> CampaignRow:
    if (
        row.lifecycle != CampaignLifecycle.PLANNING.value
        and (max_characters_per_player is not None or starting_level is not None)
    ):
        raise ValueError("campaign entry settings are locked after start")
    if name is not None:
        row.name = name
    if max_characters_per_player is not None:
        owner_over_limit = await sess.scalar(
            select(CharacterVersionRow.owner_user_id)
            .where(CharacterVersionRow.campaign_id == row.id)
            .group_by(CharacterVersionRow.owner_user_id)
            .having(func.count(CharacterVersionRow.id) > max_characters_per_player)
            .limit(1)
        )
        if owner_over_limit is not None:
            raise ValueError("campaign character limit is below the existing roster")
        row.max_characters_per_player = max_characters_per_player
    if starting_level is not None:
        row.starting_level = starting_level
    row.updated_at = utcnow()
    await sess.commit()
    loaded = await get_campaign(sess, row.id)
    assert loaded is not None
    return loaded


async def set_campaign_members(
    sess: AsyncSession,
    row: CampaignRow,
    member_ids: list[str],
) -> CampaignRow:
    now = utcnow()
    await sess.execute(
        update(UserRow)
        .where(
            UserRow.selected_campaign_id == row.id,
            UserRow.id.not_in(member_ids),
        )
        .values(selected_campaign_id=None, updated_at=now)
    )
    await sess.execute(delete(CampaignMemberRow).where(CampaignMemberRow.campaign_id == row.id))
    for user_id in member_ids:
        sess.add(CampaignMemberRow(campaign_id=row.id, user_id=user_id, added_at=now))
    row.updated_at = now
    await sess.commit()
    loaded = await get_campaign(sess, row.id)
    assert loaded is not None
    return loaded


async def activate_campaign(sess: AsyncSession, row: CampaignRow) -> CampaignRow:
    now = utcnow()
    await sess.execute(update(CampaignRow).values(is_active=False, updated_at=now))
    row.is_active = True
    row.updated_at = now
    await sess.commit()
    loaded = await get_campaign(sess, row.id)
    assert loaded is not None
    return loaded


async def start_campaign(sess: AsyncSession, row: CampaignRow) -> CampaignRow:
    if row.lifecycle != CampaignLifecycle.PLANNING.value:
        raise ValueError("campaign can only start from planning")
    now = utcnow()
    row.lifecycle = CampaignLifecycle.IN_PROGRESS.value
    row.started_at = now
    row.updated_at = now
    await sess.commit()
    loaded = await get_campaign(sess, row.id)
    assert loaded is not None
    return loaded


async def complete_campaign(sess: AsyncSession, row: CampaignRow) -> CampaignRow:
    if row.lifecycle != CampaignLifecycle.IN_PROGRESS.value:
        raise ValueError("campaign can only complete from in progress")
    now = utcnow()
    row.lifecycle = CampaignLifecycle.COMPLETED.value
    row.completed_at = now
    row.updated_at = now
    await sess.commit()
    loaded = await get_campaign(sess, row.id)
    assert loaded is not None
    return loaded
