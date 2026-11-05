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


def test_login_static_ui_serves_only_local_assets(raw_client):
    _assert_local_page(raw_client, "/login")


def test_headless_lifespan_does_not_start_hardware(client):
    assert client.app.state.engine.__class__.__name__ == "FakeEngine"
    assert not hasattr(client.app.state, "mdns")
