"""GM-only administration for campaigns and their player memberships."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from loremaster.api.deps import AuthContext, db_session, require_csrf, require_gm
from loremaster.models.campaign import (
    CampaignPublic,
    CreateCampaignRequest,
    RulePackPublic,
    SetCampaignMembersRequest,
    UpdateCampaignRequest,
)
from loremaster.models.character import CampaignRosterPublic
from loremaster.models.character_repository import campaign_roster
from loremaster.models.campaign_repository import (
    activate_campaign,
    complete_campaign,
    create_campaign,
    get_campaign,
    get_rule_pack,
    list_campaigns,
    list_rule_packs,
    public_campaign,
    public_rule_pack,
    set_campaign_members,
    start_campaign,
    update_campaign,
    valid_player_ids,
)

router = APIRouter(
    prefix="/api/admin/campaigns",
    tags=["campaigns"],
    dependencies=[Depends(require_gm), Depends(require_csrf)],
)


async def _require_campaign(sess: AsyncSession, campaign_id: str):
    campaign = await get_campaign(sess, campaign_id)
    if campaign is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
    return campaign


async def _validate_members(sess: AsyncSession, member_ids: list[str]) -> None:
    valid = await valid_player_ids(sess, member_ids)
    if valid != set(member_ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "members must be active player accounts",
        )


@router.get("/rule-packs", response_model=list[RulePackPublic])
async def all_rule_packs(sess: AsyncSession = Depends(db_session)) -> list[RulePackPublic]:
    return [public_rule_pack(row) for row in await list_rule_packs(sess)]


@router.get("", response_model=list[CampaignPublic])
async def all_campaigns(sess: AsyncSession = Depends(db_session)) -> list[CampaignPublic]:
    return [public_campaign(row) for row in await list_campaigns(sess)]


@router.post("", response_model=CampaignPublic, status_code=status.HTTP_201_CREATED)
async def add_campaign(
    payload: CreateCampaignRequest,
    context: AuthContext = Depends(require_gm),
    sess: AsyncSession = Depends(db_session),
) -> CampaignPublic:
    if await get_rule_pack(sess, payload.rule_pack_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown rule pack")
    await _validate_members(sess, payload.member_ids)
    campaign = await create_campaign(
        sess,
        name=payload.name,
        rule_pack_id=payload.rule_pack_id,
        starting_level=payload.starting_level,
        max_characters_per_player=payload.max_characters_per_player,
        member_ids=payload.member_ids,
        activate=payload.activate,
        created_by_user_id=context.user.id,
    )
    return public_campaign(campaign)


@router.patch("/{campaign_id}", response_model=CampaignPublic)
async def change_campaign(
    campaign_id: str,
    payload: UpdateCampaignRequest,
    sess: AsyncSession = Depends(db_session),
) -> CampaignPublic:
    campaign = await _require_campaign(sess, campaign_id)
    try:
        campaign = await update_campaign(
            sess,
            campaign,
            name=payload.name,
            max_characters_per_player=payload.max_characters_per_player,
            starting_level=payload.starting_level,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return public_campaign(campaign)


@router.put("/{campaign_id}/members", response_model=CampaignPublic)
async def change_members(
    campaign_id: str,
    payload: SetCampaignMembersRequest,
    sess: AsyncSession = Depends(db_session),
) -> CampaignPublic:
    campaign = await _require_campaign(sess, campaign_id)
    await _validate_members(sess, payload.member_ids)
    return public_campaign(await set_campaign_members(sess, campaign, payload.member_ids))


@router.post("/{campaign_id}/activate", response_model=CampaignPublic)
async def make_active(
    campaign_id: str,
    sess: AsyncSession = Depends(db_session),
) -> CampaignPublic:
    campaign = await _require_campaign(sess, campaign_id)
    return public_campaign(await activate_campaign(sess, campaign))


@router.post("/{campaign_id}/start", response_model=CampaignPublic)
async def start_first_session(
    campaign_id: str,
    sess: AsyncSession = Depends(db_session),
) -> CampaignPublic:
    campaign = await _require_campaign(sess, campaign_id)
    try:
        return public_campaign(await start_campaign(sess, campaign))
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/{campaign_id}/complete", response_model=CampaignPublic)
async def finish_campaign(
    campaign_id: str,
    sess: AsyncSession = Depends(db_session),
) -> CampaignPublic:
    campaign = await _require_campaign(sess, campaign_id)
    try:
        return public_campaign(await complete_campaign(sess, campaign))
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/{campaign_id}/roster", response_model=CampaignRosterPublic)
async def get_campaign_roster(
    campaign_id: str,
    sess: AsyncSession = Depends(db_session),
) -> CampaignRosterPublic:
    campaign = await _require_campaign(sess, campaign_id)
    return await campaign_roster(sess, campaign)
