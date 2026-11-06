"""Campaign administration, membership and persistence regressions."""

from __future__ import annotations

import pytest

from loremaster.models.auth import Role
from loremaster.models.auth_repository import create_user
from loremaster.models.campaign_repository import create_campaign, list_campaigns
from loremaster.models.db import Database


def _create_player(client, username: str) -> dict:
    response = client.post(
        "/api/admin/users",
        json={"username": username, "password": "player-password-123", "role": "player"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_gm_creates_campaign_with_versioned_rules_and_members(client):
    arthur = _create_player(client, "arthur")
    merlin = _create_player(client, "merlin")

    packs = client.get("/api/admin/campaigns/rule-packs")
    assert packs.status_code == 200
    assert packs.json() == [
        {
            "id": "dnd5e-2024-srd-5.2.1",
            "key": "dnd5e-2024-srd",
            "name": "D&D 5e 2024 — SRD",
            "system": "dnd5e",
            "edition": "2024",
            "version": "5.2.1",
            "license_name": "CC-BY-4.0",
        }
    ]

    created = client.post(
        "/api/admin/campaigns",
        json={
            "name": " Return of the Setting Sun ",
            "rule_pack_id": "dnd5e-2024-srd-5.2.1",
            "max_characters_per_player": 4,
            "member_ids": [arthur["id"], merlin["id"]],
            "activate": True,
        },
    )
    assert created.status_code == 201, created.text
    campaign = created.json()
    assert campaign["name"] == "Return of the Setting Sun"
    assert campaign["is_active"] is True
    assert campaign["lifecycle"] == "planning"
    assert campaign["starting_level"] == 1
    assert campaign["started_at"] is None
    assert campaign["completed_at"] is None
    assert campaign["max_characters_per_player"] == 4
    assert [member["username"] for member in campaign["members"]] == ["arthur", "merlin"]
    assert campaign["rule_pack"]["version"] == "5.2.1"


def test_only_one_campaign_is_active_and_settings_are_editable(client):
    first = client.post(
        "/api/admin/campaigns",
        json={"name": "First", "rule_pack_id": "dnd5e-2024-srd-5.2.1", "activate": False},
    ).json()
    assert first["is_active"] is True
    second_response = client.post(
        "/api/admin/campaigns",
        json={"name": "Second", "rule_pack_id": "dnd5e-2024-srd-5.2.1", "activate": True},
    )
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()

    campaigns = client.get("/api/admin/campaigns").json()
    assert [campaign["name"] for campaign in campaigns if campaign["is_active"]] == ["Second"]

    activated = client.post(f"/api/admin/campaigns/{first['id']}/activate")
    assert activated.status_code == 200
    updated = client.patch(
        f"/api/admin/campaigns/{first['id']}",
        json={"name": "First revised", "max_characters_per_player": 7},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "First revised"
    assert updated.json()["max_characters_per_player"] == 7
    assert updated.json()["rule_pack"]["id"] == "dnd5e-2024-srd-5.2.1"
    campaigns = client.get("/api/admin/campaigns").json()
    assert [campaign["id"] for campaign in campaigns if campaign["is_active"]] == [first["id"]]
    assert second["id"] != first["id"]


def test_campaign_start_locks_entry_settings_without_changing_selection(client):
    campaign = client.post(
        "/api/admin/campaigns",
        json={
            "name": "Curse of Strahd",
            "rule_pack_id": "dnd5e-2024-srd-5.2.1",
            "starting_level": 3,
            "max_characters_per_player": 5,
        },
    ).json()
    assert campaign["lifecycle"] == "planning"
    assert campaign["starting_level"] == 3

    selected = client.post(f"/api/admin/campaigns/{campaign['id']}/activate")
    assert selected.status_code == 200
    assert selected.json()["lifecycle"] == "planning"

    started = client.post(f"/api/admin/campaigns/{campaign['id']}/start")
    assert started.status_code == 200, started.text
    assert started.json()["lifecycle"] == "in_progress"
    assert started.json()["started_at"] is not None

    locked = client.patch(
        f"/api/admin/campaigns/{campaign['id']}",
        json={"starting_level": 1, "max_characters_per_player": 6},
    )
    assert locked.status_code == 409
    assert locked.json()["detail"] == "campaign entry settings are locked after start"

    renamed = client.patch(
        f"/api/admin/campaigns/{campaign['id']}",
        json={"name": "Curse of Strahd revised"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Curse of Strahd revised"

    duplicate_start = client.post(f"/api/admin/campaigns/{campaign['id']}/start")
    assert duplicate_start.status_code == 409

    completed = client.post(f"/api/admin/campaigns/{campaign['id']}/complete")
    assert completed.status_code == 200
    assert completed.json()["lifecycle"] == "completed"
    assert completed.json()["completed_at"] is not None
    assert completed.json()["is_active"] is True

    duplicate_complete = client.post(f"/api/admin/campaigns/{campaign['id']}/complete")
    assert duplicate_complete.status_code == 409


def test_campaign_cannot_complete_before_start(client):
    campaign = client.post(
        "/api/admin/campaigns",
        json={"name": "Planning", "rule_pack_id": "dnd5e-2024-srd-5.2.1"},
    ).json()
    response = client.post(f"/api/admin/campaigns/{campaign['id']}/complete")
    assert response.status_code == 409


def test_membership_accepts_only_active_players(client):
    player = _create_player(client, "inactive-player")
    campaign = client.post(
        "/api/admin/campaigns",
        json={"name": "Campaign", "rule_pack_id": "dnd5e-2024-srd-5.2.1"},
    ).json()
    disabled = client.patch(
        f"/api/admin/users/{player['id']}",
        json={"is_active": False},
    )
    assert disabled.status_code == 200
    response = client.put(
        f"/api/admin/campaigns/{campaign['id']}/members",
        json={"member_ids": [player["id"]]},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "members must be active player accounts"


def test_player_cannot_administer_campaigns(raw_client):
    assert raw_client.post(
        "/api/auth/login",
        json={"username": "test-gm", "password": "test-password-123"},
    ).status_code == 200
    csrf = raw_client.cookies.get("loremaster_csrf")
    raw_client.headers["X-CSRF-Token"] = csrf
    _create_player(raw_client, "player")
    raw_client.cookies.clear()
    raw_client.headers.pop("X-CSRF-Token", None)
    assert raw_client.post(
        "/api/auth/login",
        json={"username": "player", "password": "player-password-123"},
    ).status_code == 200
    assert raw_client.get("/api/admin/campaigns").status_code == 403
    page = raw_client.get("/campaigns", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/player"


def test_campaign_mutations_require_csrf(raw_client):
    assert raw_client.post(
        "/api/auth/login",
        json={"username": "test-gm", "password": "test-password-123"},
    ).status_code == 200
    response = raw_client.post(
        "/api/admin/campaigns",
        json={"name": "Blocked", "rule_pack_id": "dnd5e-2024-srd-5.2.1"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "invalid csrf token"


def test_campaign_validation_rejects_invalid_limits_and_rule_packs(client):
    too_small = client.post(
        "/api/admin/campaigns",
        json={
            "name": "Invalid",
            "rule_pack_id": "dnd5e-2024-srd-5.2.1",
            "max_characters_per_player": 0,
        },
    )
    assert too_small.status_code == 422
    unknown = client.post(
        "/api/admin/campaigns",
        json={"name": "Invalid", "rule_pack_id": "unknown"},
    )
    assert unknown.status_code == 422
    assert unknown.json()["detail"] == "unknown rule pack"
    invalid_level = client.post(
        "/api/admin/campaigns",
        json={
            "name": "Invalid level",
            "rule_pack_id": "dnd5e-2024-srd-5.2.1",
            "starting_level": 21,
        },
    )
    assert invalid_level.status_code == 422


@pytest.mark.asyncio
async def test_campaign_and_membership_survive_database_reopen(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'campaign.db'}"
    db = Database(url)
    await db.create_all()
    async with db.session() as sess:
        gm = await create_user(
            sess,
            username="persistent-gm",
            password="persistent-password-123",
            role=Role.GM,
        )
        player = await create_user(
            sess,
            username="persistent-player",
            password="persistent-password-123",
            role=Role.PLAYER,
        )
        await create_campaign(
            sess,
            name="Persistent campaign",
            rule_pack_id="dnd5e-2024-srd-5.2.1",
            starting_level=4,
            max_characters_per_player=6,
            member_ids=[player.id],
            activate=True,
            created_by_user_id=gm.id,
        )
    await db.close()

    reopened = Database(url)
    try:
        await reopened.create_all()
        async with reopened.session() as sess:
            campaigns = await list_campaigns(sess)
            assert len(campaigns) == 1
            assert campaigns[0].name == "Persistent campaign"
            assert campaigns[0].max_characters_per_player == 6
            assert campaigns[0].starting_level == 4
            assert campaigns[0].lifecycle == "planning"
            assert campaigns[0].is_active is True
            assert [membership.user.username for membership in campaigns[0].memberships] == [
                "persistent-player"
            ]
            assert campaigns[0].rule_pack.version == "5.2.1"
    finally:
        await reopened.close()
