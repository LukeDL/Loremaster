"""Persistence for class selection, imported sheets, HP, and import review."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from loremaster.models.ability_scores import CreationStepStatus
from loremaster.models.auth_repository import utcnow
from loremaster.models.character_creation import (
    CharacterClassLevelPublic,
    CharacterClassesPublic,
    CharacterImportPublic,
    CreationMode,
    HitPointSource,
    HitPointsPublic,
    ImportedAbilityScoresInput,
    ImportReviewState,
    SaveCharacterClassesRequest,
    SaveCharacterImportRequest,
    ability_modifier,
    calculate_new_character_hp,
    class_definition,
)
from loremaster.models.db import (
    CharacterClassLevelRow,
    CharacterCreationStateRow,
    CharacterHitPointsRow,
    CharacterImportedAbilityScoresRow,
    CharacterImportReviewRow,
    CharacterVersionRow,
)


async def get_creation_state(
    sess: AsyncSession, character_version_id: str
) -> CharacterCreationStateRow | None:
    return await sess.get(CharacterCreationStateRow, character_version_id)


async def ensure_creation_state(
    sess: AsyncSession, version: CharacterVersionRow
) -> CharacterCreationStateRow:
    state = await get_creation_state(sess, version.id)
    if state is None:
        now = utcnow()
        state = CharacterCreationStateRow(
            character_version_id=version.id,
            class_completed_at=None,
            revision=0,
            created_at=now,
            updated_at=now,
        )
        sess.add(state)
        await sess.flush()
    return state


def latest_review(version: CharacterVersionRow) -> CharacterImportReviewRow | None:
    if not version.import_reviews:
        return None
    return max(version.import_reviews, key=lambda row: row.revision)


def review_state(version: CharacterVersionRow) -> ImportReviewState:
    if version.creation_mode == CreationMode.NEW_CHARACTER.value:
        return ImportReviewState.NOT_REQUIRED
    review = latest_review(version)
    if review is None:
        return ImportReviewState.DRAFT
    return ImportReviewState(review.state)


def public_class_progress(version: CharacterVersionRow) -> CharacterClassesPublic:
    rows = sorted(version.class_levels, key=lambda row: (not row.is_starting_class, row.class_key))
    completed_at = None if version.creation_state is None else version.creation_state.class_completed_at
    status = CreationStepStatus.NOT_STARTED
    if rows:
        status = CreationStepStatus.COMPLETE if completed_at is not None else CreationStepStatus.IN_PROGRESS
    return CharacterClassesPublic(
        character_version_id=version.id,
        status=status,
        classes=[
            CharacterClassLevelPublic(
                class_key=row.class_key,
                levels=row.levels,
                is_starting_class=row.is_starting_class,
                definition=class_definition(row.class_key),
            )
            for row in rows
        ],
        completed_at=completed_at,
    )


def public_hit_points(row: CharacterHitPointsRow | None) -> HitPointsPublic:
    if row is None:
        return HitPointsPublic(
            status=CreationStepStatus.NOT_STARTED,
            source=None,
            baseline_level=None,
            maximum_hp=None,
            current_hp=None,
            temporary_hp=None,
            constitution_modifier=None,
            completed_at=None,
        )
    return HitPointsPublic(
        status=CreationStepStatus.COMPLETE,
        source=HitPointSource(row.source),
        baseline_level=row.baseline_level,
        maximum_hp=row.maximum_hp,
        current_hp=row.current_hp,
        temporary_hp=row.temporary_hp,
        constitution_modifier=row.constitution_modifier,
        completed_at=row.completed_at,
    )


def public_import(version: CharacterVersionRow) -> CharacterImportPublic:
    imported = version.imported_ability_scores
    review = latest_review(version)
    scores = None
    attestation = None
    if imported is not None:
        scores = ImportedAbilityScoresInput(
            strength=imported.strength,
            dexterity=imported.dexterity,
            constitution=imported.constitution,
            intelligence=imported.intelligence,
            wisdom=imported.wisdom,
            charisma=imported.charisma,
        )
        attestation = imported.attestation
    return CharacterImportPublic(
        character_version_id=version.id,
        review_state=review_state(version),
        revision=0 if version.creation_state is None else version.creation_state.revision,
        scores=scores,
        hit_points=public_hit_points(version.hit_points),
        attestation=attestation,
        submitted_at=None if review is None else review.submitted_at,
        reviewed_at=None if review is None else review.reviewed_at,
        reviewed_by_user_id=None if review is None else review.reviewed_by_user_id,
        review_note=None if review is None else review.note,
        submitted_snapshot_hash=None if review is None else review.snapshot_hash,
    )


def import_snapshot(version: CharacterVersionRow) -> tuple[str, str]:
    imported = version.imported_ability_scores
    hp = version.hit_points
    if imported is None or hp is None:
        raise ValueError("complete imported attributes and hit points before submitting")
    payload = {
        "attestation": imported.attestation,
        "character_version_id": version.id,
        "classes": [
            {
                "class_key": row.class_key,
                "is_starting_class": row.is_starting_class,
                "levels": row.levels,
            }
            for row in sorted(version.class_levels, key=lambda item: item.class_key)
        ],
        "creation_mode": version.creation_mode,
        "hit_points": {
            "baseline_level": hp.baseline_level,
            "constitution_modifier": hp.constitution_modifier,
            "current_hp": hp.current_hp,
            "maximum_hp": hp.maximum_hp,
            "source": hp.source,
            "temporary_hp": hp.temporary_hp,
        },
        "level": version.level,
        "scores": {
            "charisma": imported.charisma,
            "constitution": imported.constitution,
            "dexterity": imported.dexterity,
            "intelligence": imported.intelligence,
            "strength": imported.strength,
            "wisdom": imported.wisdom,
        },
    }
    snapshot_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
    return snapshot_json, snapshot_hash


def require_editable(version: CharacterVersionRow) -> None:
    if version.status != "draft":
        raise ValueError("only draft characters can be edited")
    if review_state(version) in {ImportReviewState.PENDING, ImportReviewState.APPROVED}:
        raise ValueError("submitted imports cannot be edited")


async def save_classes(
    sess: AsyncSession,
    version: CharacterVersionRow,
    payload: SaveCharacterClassesRequest,
) -> None:
    require_editable(version)
    if sum(entry.levels for entry in payload.classes) != version.level:
        raise ValueError("class levels must equal the character level")
    if version.creation_mode == CreationMode.NEW_CHARACTER.value and len(payload.classes) != 1:
        raise ValueError("new characters support one class in this increment")
    now = utcnow()
    await sess.execute(
        delete(CharacterClassLevelRow).where(
            CharacterClassLevelRow.character_version_id == version.id
        )
    )
    for entry in payload.classes:
        sess.add(
            CharacterClassLevelRow(
                character_version_id=version.id,
                class_key=entry.class_key,
                levels=entry.levels,
                is_starting_class=entry.is_starting_class,
                created_at=now,
                updated_at=now,
            )
        )
    state = await ensure_creation_state(sess, version)
    state.class_completed_at = now
    state.updated_at = now
    version.updated_at = now
    await sess.commit()


async def refresh_new_character_hp(
    sess: AsyncSession,
    version: CharacterVersionRow,
) -> CharacterHitPointsRow | None:
    if version.creation_mode != CreationMode.NEW_CHARACTER.value:
        return version.hit_points
    if version.creation_state is None or version.creation_state.class_completed_at is None:
        return None
    if version.ability_scores is None or version.ability_scores.completed_at is None:
        return None
    starting = next((row for row in version.class_levels if row.is_starting_class), None)
    if starting is None or version.ability_scores.constitution is None:
        return None
    maximum, source = calculate_new_character_hp(
        class_key=starting.class_key,
        level=version.level,
        constitution_score=version.ability_scores.constitution,
    )
    now = utcnow()
    row = version.hit_points
    if row is None:
        row = CharacterHitPointsRow(
            character_version_id=version.id,
            source=source.value,
            baseline_level=version.level,
            maximum_hp=maximum,
            current_hp=maximum,
            temporary_hp=0,
            constitution_modifier=ability_modifier(version.ability_scores.constitution),
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
        sess.add(row)
    else:
        row.source = source.value
        row.baseline_level = version.level
        row.maximum_hp = maximum
        row.current_hp = maximum
        row.constitution_modifier = ability_modifier(version.ability_scores.constitution)
        row.updated_at = now
        row.completed_at = now
    version.updated_at = now
    await sess.commit()
    return row


async def save_import(
    sess: AsyncSession,
    version: CharacterVersionRow,
    payload: SaveCharacterImportRequest,
) -> None:
    if version.creation_mode != CreationMode.MANUAL_IMPORT.value:
        raise ValueError("manual import data is only available for imported characters")
    require_editable(version)
    now = utcnow()
    scores = payload.scores.as_dict()
    imported = version.imported_ability_scores
    if imported is None:
        imported = CharacterImportedAbilityScoresRow(
            character_version_id=version.id,
            attestation=payload.attestation,
            created_at=now,
            updated_at=now,
            **scores,
        )
        sess.add(imported)
    else:
        for name, value in scores.items():
            setattr(imported, name, value)
        imported.attestation = payload.attestation
        imported.updated_at = now
    hp = version.hit_points
    constitution_modifier = ability_modifier(payload.scores.constitution)
    if hp is None:
        hp = CharacterHitPointsRow(
            character_version_id=version.id,
            source=HitPointSource.MANUAL_IMPORT.value,
            baseline_level=version.level,
            maximum_hp=payload.maximum_hp,
            current_hp=payload.current_hp,
            temporary_hp=payload.temporary_hp,
            constitution_modifier=constitution_modifier,
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
        sess.add(hp)
    else:
        hp.maximum_hp = payload.maximum_hp
        hp.current_hp = payload.current_hp
        hp.temporary_hp = payload.temporary_hp
        hp.constitution_modifier = constitution_modifier
        hp.updated_at = now
    version.updated_at = now
    await sess.commit()


async def submit_import(sess: AsyncSession, version: CharacterVersionRow) -> None:
    if version.creation_mode != CreationMode.MANUAL_IMPORT.value:
        raise ValueError("only imported characters require review")
    require_editable(version)
    if version.creation_state is None or version.creation_state.class_completed_at is None:
        raise ValueError("complete class levels before submitting the import")
    if version.imported_ability_scores is None or version.hit_points is None:
        raise ValueError("complete imported attributes and hit points before submitting")
    now = utcnow()
    state = version.creation_state
    state.revision += 1
    state.updated_at = now
    snapshot_json, snapshot_hash = import_snapshot(version)
    sess.add(
        CharacterImportReviewRow(
            character_version_id=version.id,
            revision=state.revision,
            state=ImportReviewState.PENDING.value,
            submitted_at=now,
            reviewed_by_user_id=None,
            reviewed_at=None,
            note=None,
            snapshot_json=snapshot_json,
            snapshot_hash=snapshot_hash,
        )
    )
    version.updated_at = now
    await sess.commit()


async def review_import(
    sess: AsyncSession,
    version: CharacterVersionRow,
    *,
    reviewer_user_id: str,
    decision: str,
    note: str | None,
    expected_revision: int,
    expected_snapshot_hash: str,
) -> None:
    review = latest_review(version)
    if version.creation_mode != CreationMode.MANUAL_IMPORT.value or review is None:
        raise ValueError("character import has not been submitted")
    if review.state != ImportReviewState.PENDING.value:
        raise ValueError("character import is not awaiting review")
    if review.revision != expected_revision or review.snapshot_hash != expected_snapshot_hash:
        raise ValueError("character import changed after this review was opened")
    _, current_snapshot_hash = import_snapshot(version)
    if current_snapshot_hash != review.snapshot_hash:
        raise ValueError("submitted import no longer matches its review snapshot")
    now = utcnow()
    review.state = decision
    review.reviewed_by_user_id = reviewer_user_id
    review.reviewed_at = now
    review.note = note
    version.updated_at = now
    await sess.commit()
