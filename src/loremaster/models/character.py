"""Schemas for character identities and independent campaign versions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator, field_validator

from loremaster.models.ability_scores import AbilityScoreProgressPublic
from loremaster.models.campaign import CampaignLifecycle, RulePackPublic


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


class CharacterVersionPublic(BaseModel):
    id: str
    identity: CharacterIdentitySummary
    campaign: CharacterCampaignSummary
    status: CharacterStatus
    level: int
    source_version_id: str | None
    ability_score_progress: AbilityScoreProgressPublic
    created_at: datetime
    updated_at: datetime


class CharacterIdentityPublic(CharacterIdentitySummary):
    versions: list[CharacterVersionPublic]
    created_at: datetime
    updated_at: datetime


class CreateCharacterRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    identity_id: str | None = None

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
