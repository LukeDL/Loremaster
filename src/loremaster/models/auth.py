"""Public authentication and user-management schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class Role(StrEnum):
    PLAYER = "player"
    GM = "gm"


class UserPublic(BaseModel):
    id: str
    username: str
    role: Role
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    user: UserPublic


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=10, max_length=256)
    role: Role = Role.PLAYER

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        value = value.strip()
        if not value or any(not (char.isalnum() or char in "._-") for char in value):
            raise ValueError("username must contain only letters, numbers, dot, underscore or hyphen")
        return value


class UpdateUserRequest(BaseModel):
    is_active: bool


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=10, max_length=256)
