"""Schemas for character identities and independent campaign versions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator, field_validator

from loremaster.models.ability_scores import AbilityScoreProgressPublic
from loremaster.models.campaign import CampaignLifecycle, RulePackPublic
from loremaster.models.character_creation import (
    CharacterClassesPublic,
    CreationMode,
    HitPointsPublic,
    ImportReviewState,
)


class CharacterStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEAD = "dead"
    RETIRED = "retired"


class CharacterIdentitySummary(BaseModel):
    id: str
    name: str


class CharacterCampaignSummary(BaseModel):
    id: str
    name: str
    starting_level: int
    lifecycle: CampaignLifecycle
    rule_pack: RulePackPublic


class SelectPlayerCampaignRequest(BaseModel):
    campaign_id: str = Field(min_length=1, max_length=36)


class CharacterVersionPublic(BaseModel):
    id: str
    identity: CharacterIdentitySummary
    campaign: CharacterCampaignSummary
    status: CharacterStatus
    level: int
    creation_mode: CreationMode
    source_version_id: str | None
    ability_score_progress: AbilityScoreProgressPublic
    class_progress: CharacterClassesPublic
    hit_point_progress: HitPointsPublic
    import_review_state: ImportReviewState
    created_at: datetime
    updated_at: datetime


class CharacterIdentityPublic(CharacterIdentitySummary):
    versions: list[CharacterVersionPublic]
    created_at: datetime
    updated_at: datetime


class CreateCharacterRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    identity_id: str | None = None
    creation_mode: CreationMode = CreationMode.NEW_CHARACTER
    level: int | None = Field(default=None, ge=1, le=20)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("character name cannot be blank")
        return value

    @model_validator(mode="after")
    def require_exactly_one_source(self):
        if (self.name is None) == (self.identity_id is None):
            raise ValueError("provide either name or identity_id")
        if self.creation_mode == CreationMode.MANUAL_IMPORT and self.level is None:
            raise ValueError("manual imports require the character's current level")
        if self.creation_mode == CreationMode.NEW_CHARACTER and self.level is not None:
            raise ValueError("new characters use the campaign starting level")
        return self


class RenameCharacterIdentityRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("character name cannot be blank")
        return value


class CampaignRosterMemberPublic(BaseModel):
    id: str
    username: str
    characters: list[CharacterVersionPublic]


class CampaignRosterPublic(BaseModel):
    campaign: CharacterCampaignSummary
    members: list[CampaignRosterMemberPublic]
