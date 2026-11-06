"""Schemas for versioned rule packs and campaign administration."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class CampaignLifecycle(StrEnum):
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class RulePackPublic(BaseModel):
    id: str
    key: str
    name: str
    system: str
    edition: str
    version: str
    license_name: str


class CampaignMemberPublic(BaseModel):
    id: str
    username: str


class CampaignPublic(BaseModel):
    id: str
    name: str
    rule_pack: RulePackPublic
    max_characters_per_player: int
    starting_level: int
    lifecycle: CampaignLifecycle
    is_active: bool
    members: list[CampaignMemberPublic]
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class CreateCampaignRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rule_pack_id: str = Field(min_length=1, max_length=100)
    max_characters_per_player: int = Field(default=3, ge=1, le=100)
    starting_level: int = Field(default=1, ge=1, le=20)
    member_ids: list[str] = Field(default_factory=list, max_length=100)
    activate: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("campaign name cannot be blank")
        return value

    @field_validator("member_ids")
    @classmethod
    def unique_members(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("member_ids must be unique")
        return value


class UpdateCampaignRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    max_characters_per_player: int | None = Field(default=None, ge=1, le=100)
    starting_level: int | None = Field(default=None, ge=1, le=20)

    @field_validator("name")
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("campaign name cannot be blank")
        return value


class SetCampaignMembersRequest(BaseModel):
    member_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("member_ids")
    @classmethod
    def unique_members(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("member_ids must be unique")
        return value
