"""Headless HTTP smoke coverage for the vendored web interface."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from urllib.parse import urlparse


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: set[str] = set()
        self.importmap_chunks: list[str] = []
        self._in_importmap = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "script" and attr.get("type") == "importmap":
            self._in_importmap = True
        if tag == "script" and attr.get("src"):
            self.assets.add(attr["src"] or "")
        if tag == "link" and attr.get("href"):
            self.assets.add(attr["href"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_importmap:
            self._in_importmap = False

    def handle_data(self, data: str) -> None:
        if self._in_importmap:
            self.importmap_chunks.append(data)

    def importmap_assets(self) -> set[str]:
        if not self.importmap_chunks:
            return set()
        return set(json.loads("".join(self.importmap_chunks)).get("imports", {}).values())


class StructureParser(HTMLParser):
    """Collect stable UI ids and whether they are nested in a dialog."""

    _void_tags = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.id_tags: dict[str, str] = {}
        self.ids_inside_dialog: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element_id = dict(attrs).get("id")
        if element_id:
            self.id_tags[element_id] = tag
            if "dialog" in self.stack:
                self.ids_inside_dialog.add(element_id)
        if tag not in self._void_tags:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.stack:
            return
        reverse_index = self.stack[::-1].index(tag)
        del self.stack[len(self.stack) - reverse_index - 1 :]


def _assert_local_page(client, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    parser = AssetParser()
    parser.feed(response.text)
    assets = parser.assets | parser.importmap_assets()
    assert assets
    assert all(
        not urlparse(asset).scheme and not urlparse(asset).netloc and asset.startswith("/")
        for asset in assets
    )
    for asset in assets:
        asset_response = client.get(asset)
        assert asset_response.status_code == 200, asset
        assert asset_response.content, asset


def test_index_static_ui_serves_only_local_assets(client):
    _assert_local_page(client, "/")


def test_map_static_ui_serves_only_local_assets(client):
    _assert_local_page(client, "/map")


def test_users_static_ui_serves_only_local_assets(client):
    _assert_local_page(client, "/users")


def test_campaigns_static_ui_serves_only_local_assets(client):
    _assert_local_page(client, "/campaigns")


def test_player_administration_keeps_bounded_forms_inside_dialogs(client):
    response = client.get("/users")
    assert response.status_code == 200
    parser = StructureParser()
    parser.feed(response.text)

    assert parser.id_tags["users-list"] == "div"
    assert parser.id_tags["create-player-dialog"] == "dialog"
    assert parser.id_tags["password-dialog"] == "dialog"
    assert parser.id_tags["status-dialog"] == "dialog"
    assert {"create-player", "password-form", "status-form"} <= parser.ids_inside_dialog

    script = client.get("/users.js")
    assert script.status_code == 200
    assert "prompt(" not in script.text
    assert "alert(" not in script.text


def test_campaign_administration_keeps_bounded_forms_inside_dialogs(client):
    response = client.get("/campaigns")
    assert response.status_code == 200
    parser = StructureParser()
    parser.feed(response.text)

    assert parser.id_tags["campaigns-list"] == "div"
    assert parser.id_tags["create-campaign-dialog"] == "dialog"
    assert parser.id_tags["members-dialog"] == "dialog"
    assert parser.id_tags["settings-dialog"] == "dialog"
    assert parser.id_tags["lifecycle-dialog"] == "dialog"
    assert parser.id_tags["roster-dialog"] == "dialog"
    assert parser.id_tags["import-review-dialog"] == "dialog"
    assert {
        "create-campaign",
        "members-form",
        "settings-form",
        "lifecycle-form",
        "roster-list",
        "import-review-form",
        "import-review-content",
    } <= parser.ids_inside_dialog

    script = client.get("/campaigns.js")
    assert script.status_code == 200
    assert "prompt(" not in script.text
    assert "alert(" not in script.text
    assert "requestId !== reviewRequest" in script.text
    assert "expected_revision: reviewSnapshot.revision" in script.text
    assert "expected_snapshot_hash: reviewSnapshot.hash" in script.text


def test_player_character_workflows_keep_bounded_forms_inside_dialogs(client):
    created = client.post(
        "/api/admin/users",
        json={
            "username": "static-player",
            "password": "test-password-123",
            "role": "player",
        },
    )
    assert created.status_code == 201
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    login = client.post(
        "/api/auth/login",
        json={"username": "static-player", "password": "test-password-123"},
    )
    assert login.status_code == 200
    response = client.get("/player")
    assert response.status_code == 200
    parser = StructureParser()
    parser.feed(response.text)

    assert parser.id_tags["characters-list"] == "div"
    assert parser.id_tags["create-character-dialog"] == "dialog"
    assert parser.id_tags["rename-character-dialog"] == "dialog"
    assert parser.id_tags["character-status-dialog"] == "dialog"
    assert {
        "create-character",
        "rename-character",
        "character-status-form",
    } <= parser.ids_inside_dialog
    assert "manual-import-option" in parser.ids_inside_dialog
    assert "import-level-field" in parser.ids_inside_dialog

    script = client.get("/player.js")
    assert script.status_code == 200
    assert "prompt(" not in script.text
    assert "alert(" not in script.text


def test_character_creator_is_a_dedicated_player_page_with_local_assets(raw_client):
    created = raw_client.post(
        "/api/auth/login",
        json={"username": "test-gm", "password": "test-password-123"},
    )
    assert created.status_code == 200
    csrf = raw_client.cookies.get("loremaster_csrf")
    raw_client.headers["X-CSRF-Token"] = csrf
    player = raw_client.post(
        "/api/admin/users",
        json={
            "username": "creator-player",
            "password": "test-password-123",
            "role": "player",
        },
    )
    assert player.status_code == 201

    gm_page = raw_client.get("/player/characters/example/creator", follow_redirects=False)
    assert gm_page.status_code == 303
    assert gm_page.headers["location"] == "/"

    raw_client.cookies.clear()
    raw_client.headers.pop("X-CSRF-Token", None)
    anonymous = raw_client.get("/player/characters/example/creator", follow_redirects=False)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/login"

    login = raw_client.post(
        "/api/auth/login",
        json={"username": "creator-player", "password": "test-password-123"},
    )
    assert login.status_code == 200
    _assert_local_page(raw_client, "/player/characters/example/creator")
    response = raw_client.get("/player/characters/example/creator")
    parser = StructureParser()
    parser.feed(response.text)
    assert parser.id_tags["ability-form"] == "form"
    assert parser.id_tags["ability-grid"] == "div"
    assert parser.id_tags["class-form"] == "form"
    assert parser.id_tags["class-list"] == "div"
    assert parser.id_tags["import-form"] == "form"
    assert parser.id_tags["import-ability-grid"] == "div"
    assert "ability-form" not in parser.ids_inside_dialog
    assert "class-form" not in parser.ids_inside_dialog
    assert "import-form" not in parser.ids_inside_dialog
    assert response.text.index("<strong>Classe</strong>") < response.text.index("<strong>Origem</strong>")
    assert response.text.index("<strong>Origem</strong>") < response.text.index("<strong>Atributos</strong>")
    assert response.text.index("<strong>Atributos</strong>") < response.text.index("<strong>Alinhamento</strong>")
    assert response.text.index("<strong>Alinhamento</strong>") < response.text.index("<strong>Detalhes</strong>")

    script = raw_client.get("/character-creator.js")
    assert script.status_code == 200
    assert "prompt(" not in script.text
    assert "alert(" not in script.text
    assert 'if (method !== next) scores = Object.fromEntries' not in script.text
    assert "Método alterado sem apagar os valores" in script.text
    assert 'controls.className = "score-stepper"' in script.text
    assert 'decrease.textContent = "−"' in script.text
    assert 'increase.textContent = "+"' in script.text
    assert "const classEndpoint" in script.text
    assert "const importEndpoint" in script.text
    assert "Snapshot enviado ao Mestre para revisão" in script.text
    assert "lockClassEditor(locked)" in script.text
    assert "submitImport.disabled = locked;" in script.text
    assert "submitImport.disabled = locked ||" not in script.text


def test_login_static_ui_serves_only_local_assets(raw_client):
    _assert_local_page(raw_client, "/login")


def test_headless_lifespan_does_not_start_hardware(client):
    assert client.app.state.engine.__class__.__name__ == "FakeEngine"
    assert not hasattr(client.app.state, "mdns")
