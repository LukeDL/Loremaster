"""Class, hit-point, manual-import, and GM-review regressions."""

from __future__ import annotations

import json
import sqlite3

from loremaster.models.character_creation import (
    HitPointSource,
    ability_modifier,
    calculate_new_character_hp,
)


def _login(client, username: str, password: str) -> None:
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies["loremaster_csrf"]


def _create_player(client, username: str) -> dict:
    response = client.post(
        "/api/admin/users",
        json={"username": username, "password": "player-password-123", "role": "player"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_campaign(client, player_id: str, *, level: int = 1, start: bool = False) -> dict:
    response = client.post(
        "/api/admin/campaigns",
        json={
            "name": "Character creation",
            "rule_pack_id": "dnd5e-2024-srd-5.2.1",
            "starting_level": level,
            "member_ids": [player_id],
            "activate": True,
        },
    )
    assert response.status_code == 201, response.text
    campaign = response.json()
    if start:
        started = client.post(f"/api/admin/campaigns/{campaign['id']}/start")
        assert started.status_code == 200, started.text
        campaign = started.json()
    return campaign


def _scores(constitution: int = 13) -> dict[str, int]:
    return {
        "strength": 15,
        "dexterity": 14,
        "constitution": constitution,
        "intelligence": 12,
        "wisdom": 10,
        "charisma": 8,
    }


def test_srd_class_catalog_and_hp_rules_are_pinned() -> None:
    assert ability_modifier(8) == -1
    assert ability_modifier(10) == 0
    assert ability_modifier(13) == 1
    assert calculate_new_character_hp(
        class_key="fighter", level=1, constitution_score=14
    ) == (12, HitPointSource.LEVEL_ONE_FORMULA)
    assert calculate_new_character_hp(
        class_key="wizard", level=1, constitution_score=14
    ) == (8, HitPointSource.LEVEL_ONE_FORMULA)
    assert calculate_new_character_hp(
        class_key="fighter", level=3, constitution_score=14
    ) == (28, HitPointSource.FIXED_PROGRESSION)


def test_new_character_class_and_completed_attributes_generate_hp(raw_client) -> None:
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "new-player")
    _create_campaign(raw_client, player["id"], level=3)

    _login(raw_client, "new-player", "player-password-123")
    options = raw_client.get("/api/player/rule-options/classes")
    assert options.status_code == 200
    assert len(options.json()) == 12
    assert {entry["key"] for entry in options.json()} >= {"fighter", "wizard"}
    assert "artificer" not in {entry["key"] for entry in options.json()}

    created = raw_client.post("/api/player/characters", json={"name": "Arthur"})
    assert created.status_code == 201, created.text
    character = created.json()
    assert character["creation_mode"] == "new_character"
    assert character["class_progress"]["status"] == "not_started"
    assert character["hit_point_progress"]["status"] == "not_started"

    wrong_total = raw_client.put(
        f"/api/player/characters/{character['id']}/creator/classes",
        json={"classes": [{"class_key": "fighter", "levels": 2, "is_starting_class": True}]},
    )
    assert wrong_total.status_code == 422

    classes = raw_client.put(
        f"/api/player/characters/{character['id']}/creator/classes",
        json={"classes": [{"class_key": "fighter", "levels": 3, "is_starting_class": True}]},
    )
    assert classes.status_code == 200, classes.text
    assert classes.json()["status"] == "complete"

    endpoint = f"/api/player/characters/{character['id']}/creator/ability-scores"
    assert raw_client.put(
        endpoint, json={"method": "standard_array", "scores": _scores()}
    ).status_code == 200
    completed = raw_client.post(f"{endpoint}/complete")
    assert completed.status_code == 200, completed.text

    refreshed = raw_client.get("/api/player/characters").json()[0]
    assert refreshed["hit_point_progress"] == {
        "status": "complete",
        "source": "fixed_progression",
        "baseline_level": 3,
        "maximum_hp": 25,
        "current_hp": 25,
        "temporary_hp": 0,
        "constitution_modifier": 1,
        "completed_at": refreshed["hit_point_progress"]["completed_at"],
    }
    changed_scores = _scores(15)
    changed_scores["strength"] = 13
    assert raw_client.put(
        endpoint, json={"method": "standard_array", "scores": changed_scores}
    ).status_code == 200
    assert raw_client.post(f"{endpoint}/complete").status_code == 200
    recalculated = raw_client.get("/api/player/characters").json()[0]["hit_point_progress"]
    assert recalculated["maximum_hp"] == 28
    assert recalculated["current_hp"] == 28
    assert raw_client.post(
        f"/api/player/characters/{character['id']}/activate"
    ).status_code == 200


def test_manual_import_requires_started_campaign_and_gm_approval(raw_client) -> None:
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "import-player")
    campaign = _create_campaign(raw_client, player["id"])

    _login(raw_client, "import-player", "player-password-123")
    blocked = raw_client.post(
        "/api/player/characters",
        json={"name": "Existing", "creation_mode": "manual_import", "level": 7},
    )
    assert blocked.status_code == 409

    _login(raw_client, "test-gm", "test-password-123")
    assert raw_client.post(f"/api/admin/campaigns/{campaign['id']}/start").status_code == 200
    _login(raw_client, "import-player", "player-password-123")

    created = raw_client.post(
        "/api/player/characters",
        json={"name": "Existing", "creation_mode": "manual_import", "level": 7},
    )
    assert created.status_code == 201, created.text
    character = created.json()
    assert character["level"] == 7
    assert character["creation_mode"] == "manual_import"
    assert character["import_review_state"] == "draft"

    classes = raw_client.put(
        f"/api/player/characters/{character['id']}/creator/classes",
        json={
            "classes": [
                {"class_key": "fighter", "levels": 5, "is_starting_class": True},
                {"class_key": "wizard", "levels": 2, "is_starting_class": False},
            ]
        },
    )
    assert classes.status_code == 200, classes.text

    too_large = raw_client.put(
        f"/api/player/characters/{character['id']}/creator/import",
        json={
            "scores": _scores(14),
            "maximum_hp": 10**30,
            "current_hp": 0,
            "temporary_hp": 0,
        },
    )
    assert too_large.status_code == 422

    imported = raw_client.put(
        f"/api/player/characters/{character['id']}/creator/import",
        json={
            "scores": _scores(14),
            "maximum_hp": 52,
            "current_hp": 0,
            "temporary_hp": 4,
            "attestation": "Transcrito da ficha física da campanha.",
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["hit_points"]["current_hp"] == 0
    assert imported.json()["hit_points"]["source"] == "manual_import"

    submitted = raw_client.post(
        f"/api/player/characters/{character['id']}/creator/import/submit"
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["review_state"] == "pending"
    assert submitted.json()["revision"] == 1
    assert len(submitted.json()["submitted_snapshot_hash"]) == 64
    assert raw_client.put(
        f"/api/player/characters/{character['id']}/creator/import",
        json={
            "scores": _scores(14),
            "maximum_hp": 53,
            "current_hp": 0,
            "temporary_hp": 0,
        },
    ).status_code == 422
    assert raw_client.put(
        f"/api/player/characters/{character['id']}/creator/classes",
        json={
            "classes": [
                {"class_key": "fighter", "levels": 6, "is_starting_class": True},
                {"class_key": "wizard", "levels": 1, "is_starting_class": False},
            ]
        },
    ).status_code == 422
    assert raw_client.put(
        f"/api/player/characters/{character['id']}/creator/ability-scores",
        json={"method": "standard_array", "scores": _scores()},
    ).status_code == 409
    assert raw_client.post(
        f"/api/player/characters/{character['id']}/activate"
    ).status_code == 409

    _login(raw_client, "test-gm", "test-password-123")
    review = raw_client.get(f"/api/admin/characters/{character['id']}/import")
    assert review.status_code == 200
    assert review.json()["scores"]["constitution"] == 14
    loaded_review = review.json()
    approved = raw_client.post(
        f"/api/admin/characters/{character['id']}/import/review",
        json={
            "decision": "approved",
            "note": "Conferido com o jogador.",
            "expected_revision": loaded_review["revision"],
            "expected_snapshot_hash": loaded_review["submitted_snapshot_hash"],
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["review_state"] == "approved"

    _login(raw_client, "import-player", "player-password-123")
    activated = raw_client.post(f"/api/player/characters/{character['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "active"


def test_changes_requested_unlocks_same_snapshot_for_correction(raw_client) -> None:
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "revision-player")
    _create_campaign(raw_client, player["id"], start=True)
    _login(raw_client, "revision-player", "player-password-123")
    character = raw_client.post(
        "/api/player/characters",
        json={"name": "Revision", "creation_mode": "manual_import", "level": 1},
    ).json()
    assert raw_client.put(
        f"/api/player/characters/{character['id']}/creator/classes",
        json={"classes": [{"class_key": "cleric", "levels": 1, "is_starting_class": True}]},
    ).status_code == 200
    assert raw_client.put(
        f"/api/player/characters/{character['id']}/creator/import",
        json={"scores": _scores(12), "maximum_hp": 9, "current_hp": 9},
    ).status_code == 200
    first_submission = raw_client.post(
        f"/api/player/characters/{character['id']}/creator/import/submit"
    )
    assert first_submission.status_code == 200
    first_snapshot_hash = first_submission.json()["submitted_snapshot_hash"]

    with sqlite3.connect(raw_client.app.state.db._sqlite_path) as connection:
        first_snapshot_json = connection.execute(
            "SELECT snapshot_json FROM character_import_reviews "
            "WHERE character_version_id = ? AND revision = 1",
            (character["id"],),
        ).fetchone()[0]
    first_snapshot = json.loads(first_snapshot_json)
    assert first_snapshot["hit_points"]["maximum_hp"] == 9
    assert first_snapshot["classes"] == [
        {"class_key": "cleric", "is_starting_class": True, "levels": 1}
    ]

    _login(raw_client, "test-gm", "test-password-123")
    returned = raw_client.post(
        f"/api/admin/characters/{character['id']}/import/review",
        json={
            "decision": "changes_requested",
            "note": "Confira o HP máximo.",
            "expected_revision": first_submission.json()["revision"],
            "expected_snapshot_hash": first_snapshot_hash,
        },
    )
    assert returned.status_code == 200
    assert returned.json()["review_state"] == "changes_requested"

    _login(raw_client, "revision-player", "player-password-123")
    corrected = raw_client.put(
        f"/api/player/characters/{character['id']}/creator/import",
        json={"scores": _scores(12), "maximum_hp": 10, "current_hp": 9},
    )
    assert corrected.status_code == 200, corrected.text
    submitted = raw_client.post(
        f"/api/player/characters/{character['id']}/creator/import/submit"
    )
    assert submitted.status_code == 200
    assert submitted.json()["revision"] == 2
    assert submitted.json()["review_state"] == "pending"
    assert submitted.json()["submitted_snapshot_hash"] != first_snapshot_hash

    _login(raw_client, "test-gm", "test-password-123")
    stale_approval = raw_client.post(
        f"/api/admin/characters/{character['id']}/import/review",
        json={
            "decision": "approved",
            "note": "Aprovação da ficha antiga.",
            "expected_revision": 1,
            "expected_snapshot_hash": first_snapshot_hash,
        },
    )
    assert stale_approval.status_code == 409
    assert "changed after this review was opened" in stale_approval.json()["detail"]

    current_approval = raw_client.post(
        f"/api/admin/characters/{character['id']}/import/review",
        json={
            "decision": "approved",
            "note": "Conferido novamente.",
            "expected_revision": submitted.json()["revision"],
            "expected_snapshot_hash": submitted.json()["submitted_snapshot_hash"],
        },
    )
    assert current_approval.status_code == 200
    assert current_approval.json()["review_state"] == "approved"

    with sqlite3.connect(raw_client.app.state.db._sqlite_path) as connection:
        snapshots = connection.execute(
            "SELECT revision, snapshot_json FROM character_import_reviews "
            "WHERE character_version_id = ? ORDER BY revision",
            (character["id"],),
        ).fetchall()
    assert [revision for revision, _ in snapshots] == [1, 2]
    assert snapshots[0][1] == first_snapshot_json
    assert json.loads(snapshots[1][1])["hit_points"]["maximum_hp"] == 10
