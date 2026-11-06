"""Persistence and ownership rules for character identities and campaign versions."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from loremaster.models.auth_repository import utcnow
from loremaster.models.ability_score_repository import public_ability_progress
from loremaster.models.character import (
    CampaignRosterMemberPublic,
    CampaignRosterPublic,
    CharacterCampaignSummary,
    CharacterIdentityPublic,
    CharacterIdentitySummary,
    CharacterStatus,
    CharacterVersionPublic,
)
from loremaster.models.character_creation import CreationMode, ImportReviewState
from loremaster.models.character_creation_repository import (
    public_class_progress,
    public_hit_points,
    review_state,
)
from loremaster.models.campaign_repository import public_rule_pack
from loremaster.models.db import (
    CampaignMemberRow,
    CampaignRow,
    CharacterIdentityRow,
    CharacterVersionRow,
)


def _version_query():
    return (
        select(CharacterVersionRow)
        .options(
            selectinload(CharacterVersionRow.identity),
            selectinload(CharacterVersionRow.campaign).selectinload(CampaignRow.rule_pack),
            selectinload(CharacterVersionRow.ability_scores),
            selectinload(CharacterVersionRow.creation_state),
            selectinload(CharacterVersionRow.class_levels),
            selectinload(CharacterVersionRow.imported_ability_scores),
            selectinload(CharacterVersionRow.hit_points),
            selectinload(CharacterVersionRow.import_reviews),
        )
        .execution_options(populate_existing=True)
    )


def public_campaign_summary(row: CampaignRow) -> CharacterCampaignSummary:
    return CharacterCampaignSummary(
        id=row.id,
        name=row.name,
        starting_level=row.starting_level,
        lifecycle=row.lifecycle,
        rule_pack=public_rule_pack(row.rule_pack),
    )


def public_version(row: CharacterVersionRow) -> CharacterVersionPublic:
    return CharacterVersionPublic(
        id=row.id,
        identity=CharacterIdentitySummary(id=row.identity.id, name=row.identity.name),
        campaign=public_campaign_summary(row.campaign),
        status=CharacterStatus(row.status),
        level=row.level,
        creation_mode=CreationMode(row.creation_mode),
        source_version_id=row.source_version_id,
        ability_score_progress=public_ability_progress(row.ability_scores),
        class_progress=public_class_progress(row),
        hit_point_progress=public_hit_points(row.hit_points),
        import_review_state=review_state(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_selected_campaign_for_player(
    sess: AsyncSession,
    owner_user_id: str,
) -> CampaignRow | None:
    result = await sess.execute(
        select(CampaignRow)
        .join(CampaignMemberRow)
        .options(selectinload(CampaignRow.rule_pack))
        .where(
            CampaignRow.is_active.is_(True),
            CampaignMemberRow.user_id == owner_user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_owned_identity(
    sess: AsyncSession,
    identity_id: str,
    owner_user_id: str,
) -> CharacterIdentityRow | None:
    result = await sess.execute(
        select(CharacterIdentityRow).where(
            CharacterIdentityRow.id == identity_id,
            CharacterIdentityRow.owner_user_id == owner_user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_owned_version(
    sess: AsyncSession,
    version_id: str,
    owner_user_id: str,
) -> CharacterVersionRow | None:
    result = await sess.execute(
        _version_query().where(
            CharacterVersionRow.id == version_id,
            CharacterVersionRow.owner_user_id == owner_user_id,
        )
    )
    return result.scalar_one_or_none()


async def get_version(sess: AsyncSession, version_id: str) -> CharacterVersionRow | None:
    result = await sess.execute(_version_query().where(CharacterVersionRow.id == version_id))
    return result.scalar_one_or_none()


async def list_player_versions(
    sess: AsyncSession,
    owner_user_id: str,
    campaign_id: str,
) -> list[CharacterVersionRow]:
    result = await sess.execute(
        _version_query()
        .where(
            CharacterVersionRow.owner_user_id == owner_user_id,
            CharacterVersionRow.campaign_id == campaign_id,
        )
        .order_by(CharacterVersionRow.created_at, CharacterVersionRow.id)
    )
    return list(result.scalars().unique())


async def list_player_identities(
    sess: AsyncSession,
    owner_user_id: str,
) -> list[CharacterIdentityPublic]:
    result = await sess.execute(
        select(CharacterIdentityRow)
        .where(CharacterIdentityRow.owner_user_id == owner_user_id)
        .order_by(CharacterIdentityRow.name, CharacterIdentityRow.id)
    )
    identities = list(result.scalars())
    output: list[CharacterIdentityPublic] = []
    for identity in identities:
        versions_result = await sess.execute(
            _version_query()
            .where(CharacterVersionRow.character_identity_id == identity.id)
            .order_by(CharacterVersionRow.created_at, CharacterVersionRow.id)
        )
        versions = list(versions_result.scalars().unique())
        output.append(
            CharacterIdentityPublic(
                id=identity.id,
                name=identity.name,
                versions=[public_version(version) for version in versions],
                created_at=identity.created_at,
                updated_at=identity.updated_at,
            )
        )
    return output


async def create_campaign_version(
    sess: AsyncSession,
    *,
    owner_user_id: str,
    campaign: CampaignRow,
    name: str | None,
    identity_id: str | None,
    creation_mode: CreationMode = CreationMode.NEW_CHARACTER,
    level: int | None = None,
) -> CharacterVersionRow:
    count = await sess.scalar(
        select(func.count()).select_from(CharacterVersionRow).where(
            CharacterVersionRow.owner_user_id == owner_user_id,
            CharacterVersionRow.campaign_id == campaign.id,
        )
    )
    if int(count or 0) >= campaign.max_characters_per_player:
        raise ValueError("campaign character limit reached")
    if creation_mode == CreationMode.MANUAL_IMPORT and campaign.lifecycle != "in_progress":
        raise ValueError("manual imports are available only for campaigns in progress")
    if creation_mode == CreationMode.MANUAL_IMPORT and level is None:
        raise ValueError("manual imports require the character's current level")
    version_level = campaign.starting_level if creation_mode == CreationMode.NEW_CHARACTER else level

    now = utcnow()
    source_version_id: str | None = None
    if identity_id is None:
        assert name is not None
        identity = CharacterIdentityRow(
            id=str(uuid4()),
            owner_user_id=owner_user_id,
            name=name,
            created_at=now,
            updated_at=now,
        )
        sess.add(identity)
    else:
        identity = await get_owned_identity(sess, identity_id, owner_user_id)
        if identity is None:
            raise LookupError("character identity not found")
        duplicate = await sess.scalar(
            select(CharacterVersionRow.id).where(
                CharacterVersionRow.character_identity_id == identity.id,
                CharacterVersionRow.campaign_id == campaign.id,
            )
        )
        if duplicate is not None:
            raise ValueError("character already has a version in this campaign")
        source_version_id = await sess.scalar(
            select(CharacterVersionRow.id)
            .where(CharacterVersionRow.character_identity_id == identity.id)
            .order_by(CharacterVersionRow.updated_at.desc())
            .limit(1)
        )

    version = CharacterVersionRow(
        id=str(uuid4()),
        character_identity_id=identity.id,
        owner_user_id=owner_user_id,
        campaign_id=campaign.id,
        source_version_id=source_version_id,
        status=CharacterStatus.DRAFT.value,
        level=version_level,
        creation_mode=creation_mode.value,
        created_at=now,
        updated_at=now,
    )
    sess.add(version)
    await sess.commit()
    loaded = await get_owned_version(sess, version.id, owner_user_id)
    assert loaded is not None
    return loaded


async def rename_owned_identity(
    sess: AsyncSession,
    row: CharacterIdentityRow,
    name: str,
) -> CharacterIdentityRow:
    row.name = name
    row.updated_at = utcnow()
    await sess.commit()
    return row


async def set_owned_version_status(
    sess: AsyncSession,
    row: CharacterVersionRow,
    target: CharacterStatus,
) -> CharacterVersionRow:
    current = CharacterStatus(row.status)
    if target == CharacterStatus.ACTIVE:
        if current != CharacterStatus.DRAFT:
            raise ValueError("only draft characters can be activated")
        if row.creation_mode == CreationMode.MANUAL_IMPORT.value:
            if review_state(row) != ImportReviewState.APPROVED:
                raise ValueError("the imported character must be approved before activation")
        else:
            if row.creation_state is None or row.creation_state.class_completed_at is None:
                raise ValueError("complete the class step before activating the character")
            if row.ability_scores is None or row.ability_scores.completed_at is None:
                raise ValueError("complete ability scores before activating the character")
            if row.hit_points is None or row.hit_points.completed_at is None:
                raise ValueError("complete hit points before activating the character")
        existing = await sess.scalar(
            select(CharacterVersionRow.id).where(
                CharacterVersionRow.campaign_id == row.campaign_id,
                CharacterVersionRow.owner_user_id == row.owner_user_id,
                CharacterVersionRow.status == CharacterStatus.ACTIVE.value,
            )
        )
        if existing is not None:
            raise ValueError("another character is already active in this campaign")
    elif target == CharacterStatus.RETIRED:
        if current not in {CharacterStatus.DRAFT, CharacterStatus.ACTIVE}:
            raise ValueError("only draft or active characters can be retired")
    else:
        raise ValueError("unsupported player status transition")
    row.status = target.value
    row.updated_at = utcnow()
    await sess.commit()
    loaded = await get_owned_version(sess, row.id, row.owner_user_id)
    assert loaded is not None
    return loaded


async def set_gm_version_status(
    sess: AsyncSession,
    row: CharacterVersionRow,
    target: CharacterStatus,
) -> CharacterVersionRow:
    current = CharacterStatus(row.status)
    if target == CharacterStatus.DEAD and current not in {
        CharacterStatus.DRAFT,
        CharacterStatus.ACTIVE,
    }:
        raise ValueError("only draft or active characters can be marked dead")
    if target == CharacterStatus.DRAFT and current != CharacterStatus.DEAD:
        raise ValueError("only dead characters can be restored")
    row.status = target.value
    row.updated_at = utcnow()
    await sess.commit()
    loaded = await get_version(sess, row.id)
    assert loaded is not None
    return loaded


async def campaign_roster(sess: AsyncSession, campaign: CampaignRow) -> CampaignRosterPublic:
    members: list[CampaignRosterMemberPublic] = []
    for membership in sorted(
        campaign.memberships,
        key=lambda item: item.user.username.casefold(),
    ):
        versions_result = await sess.execute(
            _version_query()
            .where(
                CharacterVersionRow.campaign_id == campaign.id,
                CharacterVersionRow.owner_user_id == membership.user_id,
            )
            .order_by(CharacterVersionRow.created_at, CharacterVersionRow.id)
        )
        versions = list(versions_result.scalars().unique())
        members.append(
            CampaignRosterMemberPublic(
                id=membership.user.id,
                username=membership.user.username,
                characters=[public_version(version) for version in versions],
            )
        )
    return CampaignRosterPublic(campaign=public_campaign_summary(campaign), members=members)
