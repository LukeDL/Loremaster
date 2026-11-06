"""D&D 5e 2024 ability-score rules and public schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, StrictInt


ABILITY_NAMES = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)
STANDARD_ARRAY = (15, 14, 13, 12, 10, 8)
POINT_BUY_COSTS = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
SUPPORTED_ABILITY_RULE_PACKS = frozenset({"dnd5e-2024-srd-5.2.1"})
ScoreValue = StrictInt | None


class AbilityScoreMethod(StrEnum):
    STANDARD_ARRAY = "standard_array"
    POINT_BUY = "point_buy"


class CreationStepStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


class AbilityScoresInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strength: ScoreValue = None
    dexterity: ScoreValue = None
    constitution: ScoreValue = None
    intelligence: ScoreValue = None
    wisdom: ScoreValue = None
    charisma: ScoreValue = None

    def as_dict(self) -> dict[str, int | None]:
        return {name: getattr(self, name) for name in ABILITY_NAMES}


class SaveAbilityScoresRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: AbilityScoreMethod
    scores: AbilityScoresInput


class AbilityScoreProgressPublic(BaseModel):
    status: CreationStepStatus
    method: AbilityScoreMethod | None
    assigned_count: int
    completed_at: datetime | None


class AbilityScoresPublic(AbilityScoreProgressPublic):
    character_version_id: str
    scores: AbilityScoresInput
    modifiers: dict[str, int | None]
    points_spent: int | None
    points_remaining: int | None
    updated_at: datetime | None


def point_buy_cost(score: int) -> int:
    try:
        return POINT_BUY_COSTS[score]
    except KeyError as exc:
        raise ValueError("point-buy scores must be between 8 and 15") from exc


def validate_ability_scores(
    method: AbilityScoreMethod,
    scores: dict[str, int | None],
    *,
    complete: bool = False,
) -> tuple[int, int | None]:
    if set(scores) != set(ABILITY_NAMES):
        raise ValueError("all six named abilities must be provided")
    assigned = [scores[name] for name in ABILITY_NAMES if scores[name] is not None]
    if complete and len(assigned) != len(ABILITY_NAMES):
        raise ValueError("all six ability scores are required")

    if method == AbilityScoreMethod.STANDARD_ARRAY:
        remaining = list(STANDARD_ARRAY)
        for value in assigned:
            if type(value) is not int or value not in remaining:
                raise ValueError("standard array assignments must use each available value once")
            remaining.remove(value)
        if complete and remaining:
            raise ValueError("completed standard array must use all six values")
        return len(assigned), None

    points_spent = 0
    for value in assigned:
        if type(value) is not int:
            raise ValueError("point-buy scores must be integers between 8 and 15")
        points_spent += point_buy_cost(value)
    if points_spent > 27:
        raise ValueError("point-buy assignment exceeds the 27-point budget")
    return len(assigned), points_spent


def calculate_modifiers(scores: dict[str, int | None]) -> dict[str, int | None]:
    return {
        name: None if value is None else (value - 10) // 2
        for name, value in scores.items()
    }
