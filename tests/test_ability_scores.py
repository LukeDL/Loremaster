"""Pure D&D 5e 2024 ability-score rule regressions."""

from __future__ import annotations

import pytest

from loremaster.models.ability_scores import (
    AbilityScoreMethod,
    ABILITY_NAMES,
    calculate_modifiers,
    point_buy_cost,
    validate_ability_scores,
)


def _scores(*values: int | None) -> dict[str, int | None]:
    return dict(zip(ABILITY_NAMES, values, strict=True))


def test_standard_array_accepts_partial_assignments_and_exact_completion():
    partial = _scores(15, 14, None, None, None, None)
    assert validate_ability_scores(AbilityScoreMethod.STANDARD_ARRAY, partial) == (2, None)

    complete = _scores(8, 14, 13, 12, 10, 15)
    assert validate_ability_scores(AbilityScoreMethod.STANDARD_ARRAY, complete, complete=True) == (
        6,
        None,
    )


@pytest.mark.parametrize(
    "values",
    [
        (15, 15, None, None, None, None),
        (16, None, None, None, None, None),
        (11, None, None, None, None, None),
    ],
)
def test_standard_array_rejects_values_outside_its_remaining_multiset(values):
    with pytest.raises(ValueError, match="standard array"):
        validate_ability_scores(AbilityScoreMethod.STANDARD_ARRAY, _scores(*values))


def test_standard_array_cannot_complete_with_missing_scores():
    with pytest.raises(ValueError, match="all six"):
        validate_ability_scores(
            AbilityScoreMethod.STANDARD_ARRAY,
            _scores(15, 14, 13, 12, 10, None),
            complete=True,
        )


def test_point_buy_cost_table_and_budget():
    assert {score: point_buy_cost(score) for score in range(8, 16)} == {
        8: 0,
        9: 1,
        10: 2,
        11: 3,
        12: 4,
        13: 5,
        14: 7,
        15: 9,
    }
    assert validate_ability_scores(
        AbilityScoreMethod.POINT_BUY,
        _scores(15, 15, 15, None, None, None),
    ) == (3, 27)


@pytest.mark.parametrize(
    "values, message",
    [
        ((15, 15, 15, 9, None, None), "exceeds"),
        ((7, None, None, None, None, None), "between 8 and 15"),
        ((16, None, None, None, None, None), "between 8 and 15"),
    ],
)
def test_point_buy_rejects_invalid_ranges_and_overspending(values, message):
    with pytest.raises(ValueError, match=message):
        validate_ability_scores(AbilityScoreMethod.POINT_BUY, _scores(*values))


def test_point_buy_completion_requires_six_scores_within_the_27_point_budget():
    with pytest.raises(ValueError, match="all six"):
        validate_ability_scores(
            AbilityScoreMethod.POINT_BUY,
            _scores(15, 15, 15, None, None, None),
            complete=True,
        )
    assert validate_ability_scores(
        AbilityScoreMethod.POINT_BUY,
        _scores(14, 14, 13, 12, 10, 8),
        complete=True,
    ) == (6, 25)
    assert validate_ability_scores(
        AbilityScoreMethod.POINT_BUY,
        _scores(15, 15, 15, 8, 8, 8),
        complete=True,
    ) == (6, 27)


def test_modifiers_use_floor_division_for_odd_scores():
    assert calculate_modifiers(_scores(8, 9, 10, 11, 14, 15)) == {
        "strength": -1,
        "dexterity": -1,
        "constitution": 0,
        "intelligence": 0,
        "wisdom": 2,
        "charisma": 2,
    }
