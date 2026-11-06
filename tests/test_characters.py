"""Character ownership, campaign versions and status regressions."""

from __future__ import annotations


def _login(client, username: str, password: str) -> None:
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    csrf = client.cookies.get("loremaster_csrf")
    assert csrf
    client.headers["X-CSRF-Token"] = csrf


def _create_player(client, username: str) -> dict:
    response = client.post(
        "/api/admin/users",
        json={"username": username, "password": "player-password-123", "role": "player"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_campaign(client, name: str, member_ids: list[str], *, level: int = 1, limit: int = 3):
    response = client.post(
        "/api/admin/campaigns",
        json={
            "name": name,
            "rule_pack_id": "dnd5e-2024-srd-5.2.1",
            "starting_level": level,
            "max_characters_per_player": limit,
            "member_ids": member_ids,
            "activate": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _complete_standard_array(client, version_id: str) -> dict:
    saved = client.put(
        f"/api/player/characters/{version_id}/creator/ability-scores",
        json={
            "method": "standard_array",
            "scores": {
                "strength": 15,
                "dexterity": 14,
                "constitution": 13,
                "intelligence": 12,
                "wisdom": 10,
                "charisma": 8,
            },
        },
    )
    assert saved.status_code == 200, saved.text
    completed = client.post(
        f"/api/player/characters/{version_id}/creator/ability-scores/complete"
    )
    assert completed.status_code == 200, completed.text
    return completed.json()


def test_player_creates_versions_at_campaign_level_and_only_one_can_be_active(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "joao")
    campaign = _create_campaign(raw_client, "Curse of Strahd", [player["id"]], level=3, limit=2)

    _login(raw_client, "joao", "player-password-123")
    context = raw_client.get("/api/player/campaign")
    assert context.status_code == 200
    assert context.json()["id"] == campaign["id"]

    arthur = raw_client.post("/api/player/characters", json={"name": "Arthur"})
    assert arthur.status_code == 201, arthur.text
    arthur = arthur.json()
    assert arthur["identity"]["name"] == "Arthur"
    assert arthur["level"] == 3
    assert arthur["status"] == "draft"
    assert arthur["ability_score_progress"]["status"] == "not_started"

    premature = raw_client.post(f"/api/player/characters/{arthur['id']}/activate")
    assert premature.status_code == 409
    assert premature.json()["detail"] == "complete ability scores before activating the character"
    _complete_standard_array(raw_client, arthur["id"])
    activated = raw_client.post(f"/api/player/characters/{arthur['id']}/activate")
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"

    merlin = raw_client.post("/api/player/characters", json={"name": "Merlin"})
    assert merlin.status_code == 201
    merlin = merlin.json()
    _complete_standard_array(raw_client, merlin["id"])
    conflict = raw_client.post(f"/api/player/characters/{merlin['id']}/activate")
    assert conflict.status_code == 409

    retired = raw_client.post(f"/api/player/characters/{arthur['id']}/retire")
    assert retired.status_code == 200
    assert retired.json()["status"] == "retired"
    assert raw_client.post(f"/api/player/characters/{merlin['id']}/activate").status_code == 200

    over_limit = raw_client.post("/api/player/characters", json={"name": "Morgana"})
    assert over_limit.status_code == 409
    assert over_limit.json()["detail"] == "campaign character limit reached"


def test_same_identity_has_independent_versions_in_different_campaigns(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "joao")
    first = _create_campaign(raw_client, "Return", [player["id"]], level=5)

    _login(raw_client, "joao", "player-password-123")
    original = raw_client.post("/api/player/characters", json={"name": "Arthur"}).json()

    _login(raw_client, "test-gm", "test-password-123")
    second = _create_campaign(raw_client, "Strahd", [player["id"]], level=1)

    _login(raw_client, "joao", "player-password-123")
    reused = raw_client.post(
        "/api/player/characters",
        json={"identity_id": original["identity"]["id"]},
    )
    assert reused.status_code == 201, reused.text
    reused = reused.json()
    assert reused["identity"]["id"] == original["identity"]["id"]
    assert reused["campaign"]["id"] == second["id"]
    assert reused["level"] == 1
    assert original["campaign"]["id"] == first["id"]
    assert original["level"] == 5

    hidden_original = raw_client.post(f"/api/player/characters/{original['id']}/activate")
    assert hidden_original.status_code == 404

    identities = raw_client.get("/api/player/character-identities").json()
    arthur = next(identity for identity in identities if identity["name"] == "Arthur")
    assert {version["campaign"]["id"] for version in arthur["versions"]} == {
        first["id"],
        second["id"],
    }


def test_player_cannot_use_or_view_another_players_identity(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    joao = _create_player(raw_client, "joao")
    maria = _create_player(raw_client, "maria")
    _create_campaign(raw_client, "Shared", [joao["id"], maria["id"]])

    _login(raw_client, "joao", "player-password-123")
    arthur = raw_client.post("/api/player/characters", json={"name": "Arthur"}).json()

    _login(raw_client, "maria", "player-password-123")
    assert raw_client.get("/api/player/characters").json() == []
    stolen = raw_client.post(
        "/api/player/characters",
        json={"identity_id": arthur["identity"]["id"]},
    )
    assert stolen.status_code == 404
    assert raw_client.patch(
        f"/api/player/character-identities/{arthur['identity']['id']}",
        json={"name": "Stolen"},
    ).status_code == 404
    assert raw_client.post(f"/api/player/characters/{arthur['id']}/activate").status_code == 404


def test_non_member_cannot_create_and_gm_roster_sees_all_versions(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    joao = _create_player(raw_client, "joao")
    outsider = _create_player(raw_client, "outsider")
    campaign = _create_campaign(raw_client, "Return", [joao["id"]])

    _login(raw_client, "outsider", "player-password-123")
    assert raw_client.get("/api/player/campaign").status_code == 404
    assert raw_client.post("/api/player/characters", json={"name": "Nope"}).status_code == 404

    _login(raw_client, "joao", "player-password-123")
    raw_client.post("/api/player/characters", json={"name": "Arthur"})

    _login(raw_client, "test-gm", "test-password-123")
    roster = raw_client.get(f"/api/admin/campaigns/{campaign['id']}/roster")
    assert roster.status_code == 200
    members = {member["username"]: member for member in roster.json()["members"]}
    assert [character["identity"]["name"] for character in members["joao"]["characters"]] == [
        "Arthur"
    ]


def test_gm_marks_character_dead_and_can_restore_it_to_draft(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "joao")
    _create_campaign(raw_client, "Return", [player["id"]])
    _login(raw_client, "joao", "player-password-123")
    arthur = raw_client.post("/api/player/characters", json={"name": "Arthur"}).json()
    _complete_standard_array(raw_client, arthur["id"])
    raw_client.post(f"/api/player/characters/{arthur['id']}/activate")

    _login(raw_client, "test-gm", "test-password-123")
    dead = raw_client.post(f"/api/admin/characters/{arthur['id']}/mark-dead")
    assert dead.status_code == 200
    assert dead.json()["status"] == "dead"
    restored = raw_client.post(f"/api/admin/characters/{arthur['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "draft"


def test_membership_removal_and_account_disable_preserve_character_versions(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "joao")
    campaign = _create_campaign(raw_client, "Return", [player["id"]])

    _login(raw_client, "joao", "player-password-123")
    arthur = raw_client.post("/api/player/characters", json={"name": "Arthur"}).json()

    _login(raw_client, "test-gm", "test-password-123")
    removed = raw_client.put(
        f"/api/admin/campaigns/{campaign['id']}/members",
        json={"member_ids": []},
    )
    assert removed.status_code == 200

    _login(raw_client, "joao", "player-password-123")
    blocked = raw_client.post(f"/api/player/characters/{arthur['id']}/activate")
    assert blocked.status_code == 404

    _login(raw_client, "test-gm", "test-password-123")
    disabled = raw_client.patch(
        f"/api/admin/users/{player['id']}",
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    roster = raw_client.get(f"/api/admin/campaigns/{campaign['id']}/roster")
    assert roster.status_code == 200
    assert roster.json()["members"] == []

    enabled = raw_client.patch(
        f"/api/admin/users/{player['id']}",
        json={"is_active": True},
    )
    assert enabled.status_code == 200
    restored = raw_client.put(
        f"/api/admin/campaigns/{campaign['id']}/members",
        json={"member_ids": [player["id"]]},
    )
    assert restored.status_code == 200

    _login(raw_client, "joao", "player-password-123")
    versions = raw_client.get("/api/player/characters")
    assert versions.status_code == 200
    assert [version["id"] for version in versions.json()] == [arthur["id"]]


def test_campaign_limit_cannot_be_lowered_below_existing_versions(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "joao")
    campaign = _create_campaign(raw_client, "Return", [player["id"]], limit=2)

    _login(raw_client, "joao", "player-password-123")
    assert raw_client.post("/api/player/characters", json={"name": "Arthur"}).status_code == 201
    assert raw_client.post("/api/player/characters", json={"name": "Merlin"}).status_code == 201

    _login(raw_client, "test-gm", "test-password-123")
    response = raw_client.patch(
        f"/api/admin/campaigns/{campaign['id']}",
        json={"max_characters_per_player": 1},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "campaign character limit is below the existing roster"


def test_ability_creator_persists_partial_progress_and_completes_point_buy(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "joao")
    campaign = _create_campaign(raw_client, "Return", [player["id"]])
    _login(raw_client, "joao", "player-password-123")
    arthur = raw_client.post("/api/player/characters", json={"name": "Arthur"}).json()
    endpoint = f"/api/player/characters/{arthur['id']}/creator/ability-scores"

    initial = raw_client.get(endpoint)
    assert initial.status_code == 200
    assert initial.json()["status"] == "not_started"
    assert initial.json()["assigned_count"] == 0

    partial_payload = {
        "method": "point_buy",
        "scores": {
            "strength": 15,
            "dexterity": 15,
            "constitution": 15,
            "intelligence": None,
            "wisdom": None,
            "charisma": None,
        },
    }
    saved = raw_client.put(endpoint, json=partial_payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "in_progress"
    assert saved.json()["assigned_count"] == 3
    assert saved.json()["points_spent"] == 27
    assert saved.json()["points_remaining"] == 0
    assert saved.json()["modifiers"]["strength"] == 2

    _login(raw_client, "joao", "player-password-123")
    resumed = raw_client.get(endpoint)
    assert resumed.status_code == 200
    assert resumed.json()["scores"] == partial_payload["scores"]

    overspent = raw_client.put(
        endpoint,
        json={
            "method": "point_buy",
            "scores": {**partial_payload["scores"], "intelligence": 9},
        },
    )
    assert overspent.status_code == 422
    assert raw_client.get(endpoint).json()["scores"] == partial_payload["scores"]

    complete_payload = {
        "method": "point_buy",
        "scores": {
            "strength": 14,
            "dexterity": 14,
            "constitution": 13,
            "intelligence": 12,
            "wisdom": 10,
            "charisma": 8,
        },
    }
    assert raw_client.put(endpoint, json=complete_payload).status_code == 200
    completed = raw_client.post(f"{endpoint}/complete")
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "complete"
    assert completed.json()["points_spent"] == 25
    assert completed.json()["points_remaining"] == 2

    _login(raw_client, "test-gm", "test-password-123")
    roster = raw_client.get(f"/api/admin/campaigns/{campaign['id']}/roster").json()
    progress = roster["members"][0]["characters"][0]["ability_score_progress"]
    assert progress["status"] == "complete"
    assert progress["method"] == "point_buy"


def test_ability_creator_isolated_by_owner_selected_campaign_and_membership(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    joao = _create_player(raw_client, "joao")
    maria = _create_player(raw_client, "maria")
    campaign = _create_campaign(raw_client, "Return", [joao["id"], maria["id"]])

    _login(raw_client, "joao", "player-password-123")
    arthur = raw_client.post("/api/player/characters", json={"name": "Arthur"}).json()
    endpoint = f"/api/player/characters/{arthur['id']}/creator/ability-scores"
    partial = {
        "method": "standard_array",
        "scores": {
            "strength": 15,
            "dexterity": None,
            "constitution": None,
            "intelligence": None,
            "wisdom": None,
            "charisma": None,
        },
    }
    assert raw_client.put(endpoint, json=partial).status_code == 200

    _login(raw_client, "maria", "player-password-123")
    assert raw_client.get(endpoint).status_code == 404
    assert raw_client.put(endpoint, json=partial).status_code == 404
    assert raw_client.post(f"{endpoint}/complete").status_code == 404

    _login(raw_client, "test-gm", "test-password-123")
    assert raw_client.put(
        f"/api/admin/campaigns/{campaign['id']}/members",
        json={"member_ids": [maria["id"]]},
    ).status_code == 200

    _login(raw_client, "joao", "player-password-123")
    assert raw_client.get(endpoint).status_code == 404

    _login(raw_client, "test-gm", "test-password-123")
    assert raw_client.put(
        f"/api/admin/campaigns/{campaign['id']}/members",
        json={"member_ids": [joao["id"], maria["id"]]},
    ).status_code == 200
    _login(raw_client, "joao", "player-password-123")
    restored = raw_client.get(endpoint)
    assert restored.status_code == 200
    assert restored.json()["scores"]["strength"] == 15


def test_reused_identity_starts_with_independent_ability_progress(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "joao")
    _create_campaign(raw_client, "First", [player["id"]])
    _login(raw_client, "joao", "player-password-123")
    original = raw_client.post("/api/player/characters", json={"name": "Arthur"}).json()
    _complete_standard_array(raw_client, original["id"])

    _login(raw_client, "test-gm", "test-password-123")
    _create_campaign(raw_client, "Second", [player["id"]])
    _login(raw_client, "joao", "player-password-123")
    reused = raw_client.post(
        "/api/player/characters",
        json={"identity_id": original["identity"]["id"]},
    ).json()
    assert reused["ability_score_progress"]["status"] == "not_started"
    creator = raw_client.get(
        f"/api/player/characters/{reused['id']}/creator/ability-scores"
    ).json()
    assert creator["scores"] == {
        "strength": None,
        "dexterity": None,
        "constitution": None,
        "intelligence": None,
        "wisdom": None,
        "charisma": None,
    }


def test_character_mutations_require_csrf(raw_client):
    _login(raw_client, "test-gm", "test-password-123")
    player = _create_player(raw_client, "joao")
    _create_campaign(raw_client, "Return", [player["id"]])
    _login(raw_client, "joao", "player-password-123")
    arthur = raw_client.post("/api/player/characters", json={"name": "Arthur"}).json()
    raw_client.headers.pop("X-CSRF-Token", None)

    response = raw_client.post("/api/player/characters", json={"name": "Merlin"})
    assert response.status_code == 403
    assert response.json()["detail"] == "invalid csrf token"
    endpoint = f"/api/player/characters/{arthur['id']}/creator/ability-scores"
    payload = {
        "method": "standard_array",
        "scores": {
            "strength": 15,
            "dexterity": None,
            "constitution": None,
            "intelligence": None,
            "wisdom": None,
            "charisma": None,
        },
    }
    assert raw_client.put(endpoint, json=payload).status_code == 403
    assert raw_client.post(f"{endpoint}/complete").status_code == 403