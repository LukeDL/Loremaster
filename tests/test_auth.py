"""Authentication, role isolation and local bootstrap regressions."""

from __future__ import annotations

import sqlite3

import pytest
from starlette.websockets import WebSocketDisconnect

from loremaster.bootstrap import bootstrap_gm
from loremaster.config import settings
from loremaster.models.auth import Role
from loremaster.models.auth_repository import create_session, create_user, get_session_user
from loremaster.models.db import Database


def _login(client, username: str, password: str):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    if response.status_code == 200:
        csrf = client.cookies.get("loremaster_csrf")
        assert csrf
        client.headers["X-CSRF-Token"] = csrf
    return response


def test_anonymous_engine_surfaces_are_protected(raw_client):
    assert raw_client.get("/api/scenes").status_code == 401
    page = raw_client.get("/", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/login"
    alias = raw_client.get("/index.html", follow_redirects=False)
    assert alias.status_code == 303
    assert alias.headers["location"] == "/login"
    for path in ("/map", "/map.html", "/users", "/users.html", "/player"):
        protected = raw_client.get(path, follow_redirects=False)
        assert protected.status_code == 303
        assert protected.headers["location"] == "/login"
    with pytest.raises(WebSocketDisconnect) as exc:
        with raw_client.websocket_connect("/ws"):
            pass
    assert exc.value.code == 4401


def test_login_sets_opaque_session_and_logout_revokes_it(raw_client):
    failed = _login(raw_client, "test-gm", "wrong-password")
    assert failed.status_code == 401
    assert failed.json()["detail"] == "invalid username or password"

    response = _login(raw_client, "TEST-GM", "test-password-123")
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "gm"
    session_cookie = raw_client.cookies.get("loremaster_session")
    assert session_cookie and "test-password" not in session_cookie
    assert raw_client.get("/api/auth/me").status_code == 200

    logout = raw_client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert raw_client.get("/api/auth/me").status_code == 401


def test_mutations_require_csrf_after_login(raw_client):
    assert _login(raw_client, "test-gm", "test-password-123").status_code == 200
    raw_client.headers.pop("X-CSRF-Token", None)
    assert raw_client.post("/api/playback/stop").status_code == 403


def test_gm_creates_player_and_player_cannot_access_engine(raw_client):
    assert _login(raw_client, "test-gm", "test-password-123").status_code == 200
    created = raw_client.post(
        "/api/admin/users",
        json={"username": "arthur", "password": "player-password-123", "role": "player"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "player"

    raw_client.cookies.clear()
    raw_client.headers.pop("X-CSRF-Token", None)
    assert _login(raw_client, "arthur", "player-password-123").status_code == 200
    assert raw_client.get("/api/scenes").status_code == 403
    assert raw_client.get("/api/admin/users").status_code == 403
    root = raw_client.get("/", follow_redirects=False)
    assert root.status_code == 303
    assert root.headers["location"] == "/player"
    assert raw_client.get("/player").status_code == 200
    with pytest.raises(WebSocketDisconnect) as exc:
        with raw_client.websocket_connect("/ws"):
            pass
    assert exc.value.code == 4403


@pytest.mark.asyncio
async def test_bootstrap_creates_only_first_gm(tmp_path, monkeypatch):
    data_dir = tmp_path / "bootstrap"
    monkeypatch.setattr(settings, "data_dir", data_dir)
    await bootstrap_gm(username="lucas", password="bootstrap-password-123")

    with sqlite3.connect(data_dir / "loremaster.db") as connection:
        user = connection.execute(
            "SELECT username, role, password_hash FROM users"
        ).fetchone()
    assert user is not None
    assert user[0:2] == ("lucas", "gm")
    assert user[2] != "bootstrap-password-123"
    assert "bootstrap-password-123" not in user[2]

    with pytest.raises(RuntimeError, match="already exists"):
        await bootstrap_gm(username="other", password="another-password-123")


@pytest.mark.asyncio
async def test_session_survives_database_reopen(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'persistent.db'}"
    db = Database(url)
    await db.create_all()
    async with db.session() as sess:
        user = await create_user(
            sess,
            username="persistent-player",
            password="persistent-password-123",
            role=Role.PLAYER,
        )
        token, _, _ = await create_session(sess, user_id=user.id, lifetime_hours=24)
    await db.close()

    reopened = Database(url)
    try:
        await reopened.create_all()
        async with reopened.session() as sess:
            found = await get_session_user(sess, token)
        assert found is not None
        assert found[1].username == "persistent-player"
    finally:
        await reopened.close()
