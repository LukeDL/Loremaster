"""Player-owned character APIs and GM status controls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from loremaster.api.deps import AuthContext, db_session, require_authenticated, require_csrf, require_gm
from loremaster.models.auth import Role
from loremaster.models.ability_scores import (
    AbilityScoresPublic,
    SUPPORTED_ABILITY_RULE_PACKS,
    SaveAbilityScoresRequest,
)
from loremaster.models.ability_score_repository import (
    complete_ability_scores,
    get_ability_scores,
    public_ability_scores,
    save_ability_scores,
)
from loremaster.models.character import (
    CharacterIdentityPublic,
    CharacterIdentitySummary,
    CharacterStatus,
    CharacterVersionPublic,
    CreateCharacterRequest,
    RenameCharacterIdentityRequest,
)
from loremaster.models.character_creation import (
    CLASS_CATALOG,
    CharacterClassDefinition,
    CharacterClassesPublic,
    CharacterImportPublic,
    CreationMode,
    ImportReviewRequest,
    SUPPORTED_CHARACTER_RULE_PACKS,
    SaveCharacterClassesRequest,
    SaveCharacterImportRequest,
)
from loremaster.models.character_creation_repository import (
    public_class_progress,
    public_import,
    refresh_new_character_hp,
    review_import,
    save_classes,
    save_import,
    submit_import,
)
from loremaster.models.character_repository import (
    create_campaign_version,
    get_owned_identity,
    get_owned_version,
    get_selected_campaign_for_player,
    get_version,
    list_player_identities,
    list_player_versions,
    public_campaign_summary,
    public_version,
    rename_owned_identity,
    set_gm_version_status,
    set_owned_version_status,
)
from loremaster.models.character import CharacterCampaignSummary


player_router = APIRouter(
    prefix="/api/player",
    tags=["characters"],
    dependencies=[Depends(require_authenticated), Depends(require_csrf)],
)
admin_router = APIRouter(
    prefix="/api/admin/characters",
    tags=["characters"],
    dependencies=[Depends(require_gm), Depends(require_csrf)],
)


def _require_player(context: AuthContext) -> None:
    if context.user.role != Role.PLAYER.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "player access required")


async def _selected_campaign_or_404(sess: AsyncSession, user_id: str):
    campaign = await get_selected_campaign_for_player(sess, user_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no selected campaign for player")
    return campaign


async def _owned_version_in_selected_campaign(
    sess: AsyncSession,
    context: AuthContext,
    version_id: str,
):
    _require_player(context)
    campaign = await _selected_campaign_or_404(sess, context.user.id)
    row = await get_owned_version(sess, version_id, context.user.id)
    if row is None or row.campaign_id != campaign.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "character version not found")
    return row


def _require_ability_creator_available(row) -> None:
    if row.status != CharacterStatus.DRAFT.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "only draft characters can be edited")
    if row.creation_mode != CreationMode.NEW_CHARACTER.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "guided ability scores are unavailable for imported characters",
        )
    if row.campaign.rule_pack_id not in SUPPORTED_ABILITY_RULE_PACKS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "ability-score rules are unavailable for this rule pack",
        )


def _require_character_creator_available(row) -> None:
    if row.status != CharacterStatus.DRAFT.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "only draft characters can be edited")
    if row.campaign.rule_pack_id not in SUPPORTED_CHARACTER_RULE_PACKS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "character-creation rules are unavailable for this rule pack",
        )


@player_router.get("/campaign", response_model=CharacterCampaignSummary)
async def selected_campaign(
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterCampaignSummary:
    _require_player(context)
    campaign = await _selected_campaign_or_404(sess, context.user.id)
    return public_campaign_summary(campaign)


@player_router.get("/characters", response_model=list[CharacterVersionPublic])
async def player_characters(
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> list[CharacterVersionPublic]:
    _require_player(context)
    campaign = await _selected_campaign_or_404(sess, context.user.id)
    rows = await list_player_versions(sess, context.user.id, campaign.id)
    return [public_version(row) for row in rows]


@player_router.get("/rule-options/classes", response_model=list[CharacterClassDefinition])
async def class_options(
    context: AuthContext = Depends(require_authenticated),
) -> list[CharacterClassDefinition]:
    _require_player(context)
    return list(CLASS_CATALOG.values())


@player_router.get("/character-identities", response_model=list[CharacterIdentityPublic])
async def player_identities(
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> list[CharacterIdentityPublic]:
    _require_player(context)
    return await list_player_identities(sess, context.user.id)


@player_router.post(
    "/characters",
    response_model=CharacterVersionPublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_character(
    payload: CreateCharacterRequest,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterVersionPublic:
    _require_player(context)
    campaign = await _selected_campaign_or_404(sess, context.user.id)
    try:
        row = await create_campaign_version(
            sess,
            owner_user_id=context.user.id,
            campaign=campaign,
            name=payload.name,
            identity_id=payload.identity_id,
            creation_mode=payload.creation_mode,
            level=payload.level,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return public_version(row)


@player_router.patch(
    "/character-identities/{identity_id}",
    response_model=CharacterIdentitySummary,
)
async def rename_identity(
    identity_id: str,
    payload: RenameCharacterIdentityRequest,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterIdentitySummary:
    _require_player(context)
    identity = await get_owned_identity(sess, identity_id, context.user.id)
    if identity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "character identity not found")
    identity = await rename_owned_identity(sess, identity, payload.name)
    return CharacterIdentitySummary(id=identity.id, name=identity.name)


async def _player_status_change(
    version_id: str,
    target: CharacterStatus,
    context: AuthContext,
    sess: AsyncSession,
) -> CharacterVersionPublic:
    row = await _owned_version_in_selected_campaign(sess, context, version_id)
    try:
        row = await set_owned_version_status(sess, row, target)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return public_version(row)


@player_router.get(
    "/characters/{version_id}/creator/classes",
    response_model=CharacterClassesPublic,
)
async def character_classes(
    version_id: str,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterClassesPublic:
    row = await _owned_version_in_selected_campaign(sess, context, version_id)
    if row.campaign.rule_pack_id not in SUPPORTED_CHARACTER_RULE_PACKS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "character-creation rules are unavailable for this rule pack",
        )
    return public_class_progress(row)


@player_router.put(
    "/characters/{version_id}/creator/classes",
    response_model=CharacterClassesPublic,
)
async def save_character_classes(
    version_id: str,
    payload: SaveCharacterClassesRequest,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterClassesPublic:
    row = await _owned_version_in_selected_campaign(sess, context, version_id)
    _require_character_creator_available(row)
    try:
        await save_classes(sess, row, payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    refreshed = await get_owned_version(sess, version_id, context.user.id)
    assert refreshed is not None
    await refresh_new_character_hp(sess, refreshed)
    refreshed = await get_owned_version(sess, version_id, context.user.id)
    assert refreshed is not None
    return public_class_progress(refreshed)


@player_router.get(
    "/characters/{version_id}/creator/import",
    response_model=CharacterImportPublic,
)
async def character_import(
    version_id: str,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterImportPublic:
    row = await _owned_version_in_selected_campaign(sess, context, version_id)
    if row.creation_mode != "manual_import":
        raise HTTPException(status.HTTP_409_CONFLICT, "character is not a manual import")
    return public_import(row)


@player_router.put(
    "/characters/{version_id}/creator/import",
    response_model=CharacterImportPublic,
)
async def save_character_import(
    version_id: str,
    payload: SaveCharacterImportRequest,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterImportPublic:
    row = await _owned_version_in_selected_campaign(sess, context, version_id)
    _require_character_creator_available(row)
    try:
        await save_import(sess, row, payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    refreshed = await get_owned_version(sess, version_id, context.user.id)
    assert refreshed is not None
    return public_import(refreshed)


@player_router.post(
    "/characters/{version_id}/creator/import/submit",
    response_model=CharacterImportPublic,
)
async def submit_character_import(
    version_id: str,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterImportPublic:
    row = await _owned_version_in_selected_campaign(sess, context, version_id)
    _require_character_creator_available(row)
    try:
        await submit_import(sess, row)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    refreshed = await get_owned_version(sess, version_id, context.user.id)
    assert refreshed is not None
    return public_import(refreshed)


@player_router.get(
    "/characters/{version_id}/creator/ability-scores",
    response_model=AbilityScoresPublic,
)
async def ability_scores(
    version_id: str,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> AbilityScoresPublic:
    row = await _owned_version_in_selected_campaign(sess, context, version_id)
    if row.campaign.rule_pack_id not in SUPPORTED_ABILITY_RULE_PACKS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "ability-score rules are unavailable for this rule pack",
        )
    ability_row = await get_ability_scores(sess, row.id)
    return public_ability_scores(ability_row, row.id)


@player_router.put(
    "/characters/{version_id}/creator/ability-scores",
    response_model=AbilityScoresPublic,
)
async def save_character_ability_scores(
    version_id: str,
    payload: SaveAbilityScoresRequest,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> AbilityScoresPublic:
    row = await _owned_version_in_selected_campaign(sess, context, version_id)
    _require_ability_creator_available(row)
    try:
        ability_row = await save_ability_scores(sess, row, payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return public_ability_scores(ability_row, row.id)


@player_router.post(
    "/characters/{version_id}/creator/ability-scores/complete",
    response_model=AbilityScoresPublic,
)
async def complete_character_ability_scores(
    version_id: str,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> AbilityScoresPublic:
    row = await _owned_version_in_selected_campaign(sess, context, version_id)
    _require_ability_creator_available(row)
    try:
        ability_row = await complete_ability_scores(sess, row)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    refreshed = await get_owned_version(sess, row.id, context.user.id)
    assert refreshed is not None
    await refresh_new_character_hp(sess, refreshed)
    return public_ability_scores(ability_row, row.id)


@player_router.post("/characters/{version_id}/activate", response_model=CharacterVersionPublic)
async def activate_character(
    version_id: str,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterVersionPublic:
    return await _player_status_change(version_id, CharacterStatus.ACTIVE, context, sess)


@player_router.post("/characters/{version_id}/retire", response_model=CharacterVersionPublic)
async def retire_character(
    version_id: str,
    context: AuthContext = Depends(require_authenticated),
    sess: AsyncSession = Depends(db_session),
) -> CharacterVersionPublic:
    return await _player_status_change(version_id, CharacterStatus.RETIRED, context, sess)


async def _gm_status_change(
    version_id: str,
    target: CharacterStatus,
    sess: AsyncSession,
) -> CharacterVersionPublic:
    row = await get_version(sess, version_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "character version not found")
    try:
        row = await set_gm_version_status(sess, row, target)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return public_version(row)


@admin_router.get("/{version_id}/import", response_model=CharacterImportPublic)
async def gm_character_import(
    version_id: str,
    sess: AsyncSession = Depends(db_session),
) -> CharacterImportPublic:
    row = await get_version(sess, version_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "character version not found")
    if row.creation_mode != "manual_import":
        raise HTTPException(status.HTTP_409_CONFLICT, "character is not a manual import")
    return public_import(row)


@admin_router.post("/{version_id}/import/review", response_model=CharacterImportPublic)
async def gm_review_character_import(
    version_id: str,
    payload: ImportReviewRequest,
    context: AuthContext = Depends(require_gm),
    sess: AsyncSession = Depends(db_session),
) -> CharacterImportPublic:
    row = await get_version(sess, version_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "character version not found")
    try:
        await review_import(
            sess,
            row,
            reviewer_user_id=context.user.id,
            decision=payload.decision,
            note=payload.note,
            expected_revision=payload.expected_revision,
            expected_snapshot_hash=payload.expected_snapshot_hash,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    refreshed = await get_version(sess, version_id)
    assert refreshed is not None
    return public_import(refreshed)


@admin_router.post("/{version_id}/mark-dead", response_model=CharacterVersionPublic)
async def mark_character_dead(
    version_id: str,
    sess: AsyncSession = Depends(db_session),
) -> CharacterVersionPublic:
    return await _gm_status_change(version_id, CharacterStatus.DEAD, sess)


@admin_router.post("/{version_id}/restore", response_model=CharacterVersionPublic)
async def restore_character(
    version_id: str,
    sess: AsyncSession = Depends(db_session),
) -> CharacterVersionPublic:
    return await _gm_status_change(version_id, CharacterStatus.DRAFT, sess)
