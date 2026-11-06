"""Persistence for the resumable ability-score creator step."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loremaster.models.ability_scores import (
    ABILITY_NAMES,
    AbilityScoreMethod,
    AbilityScoreProgressPublic,
    AbilityScoresInput,
    AbilityScoresPublic,
    CreationStepStatus,
    SaveAbilityScoresRequest,
    calculate_modifiers,
    validate_ability_scores,
)
from loremaster.models.auth_repository import utcnow
from loremaster.models.db import CharacterAbilityScoresRow, CharacterVersionRow


async def get_ability_scores(
    sess: AsyncSession,
    character_version_id: str,
) -> CharacterAbilityScoresRow | None:
    return await sess.scalar(
        select(CharacterAbilityScoresRow).where(
            CharacterAbilityScoresRow.character_version_id == character_version_id
        )
    )


def _score_dict(row: CharacterAbilityScoresRow | None) -> dict[str, int | None]:
    if row is None:
        return {name: None for name in ABILITY_NAMES}
    return {name: getattr(row, name) for name in ABILITY_NAMES}


def public_ability_progress(
    row: CharacterAbilityScoresRow | None,
) -> AbilityScoreProgressPublic:
    if row is None:
        return AbilityScoreProgressPublic(
            status=CreationStepStatus.NOT_STARTED,
            method=None,
            assigned_count=0,
            completed_at=None,
        )
    scores = _score_dict(row)
    return AbilityScoreProgressPublic(
        status=(
            CreationStepStatus.COMPLETE
            if row.completed_at is not None
            else CreationStepStatus.IN_PROGRESS
        ),
        method=AbilityScoreMethod(row.method),
        assigned_count=sum(value is not None for value in scores.values()),
        completed_at=row.completed_at,
    )


def public_ability_scores(
    row: CharacterAbilityScoresRow | None,
    character_version_id: str,
) -> AbilityScoresPublic:
    progress = public_ability_progress(row)
    scores = _score_dict(row)
    points_spent: int | None = None
    points_remaining: int | None = None
    if progress.method == AbilityScoreMethod.POINT_BUY:
        _, points_spent = validate_ability_scores(progress.method, scores)
        assert points_spent is not None
        points_remaining = 27 - points_spent
    return AbilityScoresPublic(
        **progress.model_dump(),
        character_version_id=character_version_id,
        scores=AbilityScoresInput(**scores),
        modifiers=calculate_modifiers(scores),
        points_spent=points_spent,
        points_remaining=points_remaining,
        updated_at=None if row is None else row.updated_at,
    )


async def save_ability_scores(
    sess: AsyncSession,
    version: CharacterVersionRow,
    payload: SaveAbilityScoresRequest,
) -> CharacterAbilityScoresRow:
    scores = payload.scores.as_dict()
    validate_ability_scores(payload.method, scores)
    row = await get_ability_scores(sess, version.id)
    now = utcnow()
    if row is None:
        row = CharacterAbilityScoresRow(
            character_version_id=version.id,
            method=payload.method.value,
            created_at=now,
            updated_at=now,
            completed_at=None,
            **scores,
        )
        sess.add(row)
    else:
        row.method = payload.method.value
        for name, value in scores.items():
            setattr(row, name, value)
        row.updated_at = now
        row.completed_at = None
    version.updated_at = now
    await sess.commit()
    return row


async def complete_ability_scores(
    sess: AsyncSession,
    version: CharacterVersionRow,
) -> CharacterAbilityScoresRow:
    row = await get_ability_scores(sess, version.id)
    if row is None:
        raise ValueError("save ability scores before completing the step")
    method = AbilityScoreMethod(row.method)
    validate_ability_scores(method, _score_dict(row), complete=True)
    now = utcnow()
    row.completed_at = row.completed_at or now
    row.updated_at = now
    version.updated_at = now
    await sess.commit()
    return row
