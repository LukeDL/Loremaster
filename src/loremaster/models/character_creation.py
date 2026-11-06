"""D&D 5e 2024 class, import, and hit-point creation rules."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from loremaster.models.ability_scores import CreationStepStatus


SUPPORTED_CHARACTER_RULE_PACKS = frozenset({"dnd5e-2024-srd-5.2.1"})


class CreationMode(StrEnum):
    NEW_CHARACTER = "new_character"
    MANUAL_IMPORT = "manual_import"


class ImportReviewState(StrEnum):
    NOT_REQUIRED = "not_required"
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class HitPointSource(StrEnum):
    LEVEL_ONE_FORMULA = "level_one_formula"
    FIXED_PROGRESSION = "fixed_progression"
    MANUAL_IMPORT = "manual_import"


class CharacterClassDefinition(BaseModel):
    key: str
    name: str
    hit_die: int
    fixed_hp_per_level: int
    primary_abilities: tuple[str, ...]
    saving_throws: tuple[str, str]


_CLASS_ROWS = (
    ("barbarian", "Bárbaro", 12, 7, ("strength",), ("strength", "constitution")),
    ("bard", "Bardo", 8, 5, ("charisma",), ("dexterity", "charisma")),
    ("cleric", "Clérigo", 8, 5, ("wisdom",), ("wisdom", "charisma")),
    ("druid", "Druida", 8, 5, ("wisdom",), ("intelligence", "wisdom")),
    ("fighter", "Guerreiro", 10, 6, ("strength", "dexterity"), ("strength", "constitution")),
    ("monk", "Monge", 8, 5, ("dexterity", "wisdom"), ("strength", "dexterity")),
    ("paladin", "Paladino", 10, 6, ("strength", "charisma"), ("wisdom", "charisma")),
    ("ranger", "Patrulheiro", 10, 6, ("dexterity", "wisdom"), ("strength", "dexterity")),
    ("rogue", "Ladino", 8, 5, ("dexterity",), ("dexterity", "intelligence")),
    ("sorcerer", "Feiticeiro", 6, 4, ("charisma",), ("constitution", "charisma")),
    ("warlock", "Bruxo", 8, 5, ("charisma",), ("wisdom", "charisma")),
    ("wizard", "Mago", 6, 4, ("intelligence",), ("intelligence", "wisdom")),
)
CLASS_CATALOG = {
    row[0]: CharacterClassDefinition(
        key=row[0],
        name=row[1],
        hit_die=row[2],
        fixed_hp_per_level=row[3],
        primary_abilities=row[4],
        saving_throws=row[5],
    )
    for row in _CLASS_ROWS
}


def class_definition(class_key: str) -> CharacterClassDefinition:
    try:
        return CLASS_CATALOG[class_key]
    except KeyError as exc:
        raise ValueError("class is unavailable in this rule pack") from exc


class CharacterClassLevelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_key: str
    levels: StrictInt = Field(ge=1, le=20)
    is_starting_class: bool = False


class SaveCharacterClassesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classes: list[CharacterClassLevelInput] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_composition(self):
        keys = [entry.class_key for entry in self.classes]
        if len(keys) != len(set(keys)):
            raise ValueError("each class can appear only once")
        if sum(entry.is_starting_class for entry in self.classes) != 1:
            raise ValueError("exactly one starting class is required")
        for key in keys:
            class_definition(key)
        if sum(entry.levels for entry in self.classes) > 20:
            raise ValueError("total class levels cannot exceed 20")
        return self


class CharacterClassLevelPublic(CharacterClassLevelInput):
    definition: CharacterClassDefinition


class CharacterClassesPublic(BaseModel):
    character_version_id: str
    status: CreationStepStatus
    classes: list[CharacterClassLevelPublic]
    completed_at: datetime | None


class ImportedAbilityScoresInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strength: StrictInt = Field(ge=1, le=30)
    dexterity: StrictInt = Field(ge=1, le=30)
    constitution: StrictInt = Field(ge=1, le=30)
    intelligence: StrictInt = Field(ge=1, le=30)
    wisdom: StrictInt = Field(ge=1, le=30)
    charisma: StrictInt = Field(ge=1, le=30)

    def as_dict(self) -> dict[str, int]:
        return self.model_dump()


class SaveCharacterImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: ImportedAbilityScoresInput
    maximum_hp: StrictInt = Field(ge=1, le=1_000_000)
    current_hp: StrictInt = Field(ge=0, le=1_000_000)
    temporary_hp: StrictInt = Field(default=0, ge=0, le=1_000_000)
    attestation: str = Field(default="Transcrito da ficha usada nesta campanha", min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_hp(self):
        if self.current_hp > self.maximum_hp:
            raise ValueError("current hit points cannot exceed maximum hit points")
        self.attestation = self.attestation.strip()
        if not self.attestation:
            raise ValueError("import attestation cannot be blank")
        return self


class ImportReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str
    note: str | None = Field(default=None, max_length=1000)
    expected_revision: StrictInt = Field(ge=1)
    expected_snapshot_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_decision(self):
        if self.decision not in {"approved", "changes_requested"}:
            raise ValueError("review decision must be approved or changes_requested")
        if self.decision == "changes_requested" and not (self.note or "").strip():
            raise ValueError("a review note is required when requesting changes")
        self.note = None if self.note is None else self.note.strip() or None
        return self


class HitPointsPublic(BaseModel):
    status: CreationStepStatus
    source: HitPointSource | None
    baseline_level: int | None
    maximum_hp: int | None
    current_hp: int | None
    temporary_hp: int | None
    constitution_modifier: int | None
    completed_at: datetime | None


class CharacterImportPublic(BaseModel):
    character_version_id: str
    review_state: ImportReviewState
    revision: int
    scores: ImportedAbilityScoresInput | None
    hit_points: HitPointsPublic
    attestation: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_user_id: str | None
    review_note: str | None
    submitted_snapshot_hash: str | None


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def calculate_new_character_hp(
    *,
    class_key: str,
    level: int,
    constitution_score: int,
) -> tuple[int, HitPointSource]:
    if not 1 <= level <= 20:
        raise ValueError("character level must be between 1 and 20")
    definition = class_definition(class_key)
    constitution_modifier = ability_modifier(constitution_score)
    maximum = definition.hit_die + constitution_modifier
    source = HitPointSource.LEVEL_ONE_FORMULA
    if level > 1:
        maximum += (level - 1) * max(1, definition.fixed_hp_per_level + constitution_modifier)
        source = HitPointSource.FIXED_PROGRESSION
    return max(1, maximum), source
