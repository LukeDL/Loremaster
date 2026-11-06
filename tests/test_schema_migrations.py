"""Versioned SQLite migration and integrity regressions."""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from loremaster.models.db import Database
from loremaster.models.migrations import MIGRATION_VERSIONS


LEGACY_SCHEMA = """
CREATE TABLE audio_files (
    id VARCHAR(36) PRIMARY KEY,
    original_name VARCHAR(500) NOT NULL,
    path VARCHAR(500) NOT NULL,
    duration_ms INTEGER NOT NULL,
    sample_rate INTEGER NOT NULL,
    channels INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at DATETIME NOT NULL
);
CREATE TABLE scenes (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    on_end_json TEXT NOT NULL,
    is_on_map BOOLEAN NOT NULL,
    graph_x FLOAT,
    graph_y FLOAT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);
CREATE TABLE layers (
    id VARCHAR(36) PRIMARY KEY,
    scene_id VARCHAR(36) NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
    audio_file_id VARCHAR(36) NOT NULL REFERENCES audio_files(id),
    position INTEGER NOT NULL,
    loop BOOLEAN NOT NULL,
    volume FLOAT NOT NULL,
    fade_in_ms INTEGER NOT NULL,
    fade_out_ms INTEGER NOT NULL
);
"""


def _create_legacy_database(path, *, orphan: bool = False) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(LEGACY_SCHEMA)
        connection.execute(
            "INSERT INTO audio_files VALUES (?,?,?,?,?,?,?,?)",
            ("a1", "rain.wav", "rain.wav", 1000, 48000, 2, 100, "2026-01-01"),
        )
        connection.execute(
            "INSERT INTO scenes VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "s1",
                "Rain",
                "legacy scene",
                '{"type":"return_previous"}',
                1,
                10.0,
                20.0,
                "2026-01-01",
                "2026-01-01",
            ),
        )
        connection.execute(
            "INSERT INTO layers VALUES (?,?,?,?,?,?,?,?)",
            ("l1", "missing" if orphan else "s1", "a1", 0, 1, 0.5, 100, 200),
        )


@pytest.mark.asyncio
async def test_fresh_database_records_all_migrations_and_enables_foreign_keys(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        await db.create_all()
        async with db.engine.connect() as conn:
            applied = {
                row[0] for row in (await conn.execute(text("SELECT version FROM schema_migrations")))
            }
            foreign_keys = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
            tables = {
                row[0]
                for row in (
                    await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
                )
            }
    finally:
        await db.close()

    assert applied == MIGRATION_VERSIONS
    assert foreign_keys == 1
    assert {
        "users",
        "sessions",
        "rule_packs",
        "campaigns",
        "campaign_members",
        "character_identities",
        "character_versions",
        "character_ability_scores",
    } <= tables


@pytest.mark.asyncio
async def test_legacy_database_is_backed_up_and_migrated_without_data_loss(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_database(db_path)
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    try:
        await db.create_all()
        await db.create_all()
    finally:
        await db.close()

    with sqlite3.connect(db_path) as connection:
        layer_columns = {row[1] for row in connection.execute("PRAGMA table_info(layers)")}
        scene_columns = {row[1] for row in connection.execute("PRAGMA table_info(scenes)")}
        layer = connection.execute(
            "SELECT id, scene_id, audio_file_id, volume, pan_lr, loop_start_ms, loop_end_ms, "
            "group_name "
            "FROM layers"
        ).fetchone()
        scene = connection.execute(
            "SELECT id, name, is_entry, group_volumes_json FROM scenes"
        ).fetchone()
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        new_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('users', 'sessions', 'rule_packs', 'campaigns', "
                "'campaign_members', 'character_identities', 'character_versions', "
                "'character_ability_scores')"
            )
        }
        campaign_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(campaigns)")
        }
        rule_pack = connection.execute(
            "SELECT id, edition, version, license_name FROM rule_packs"
        ).fetchone()

    assert {"pan_lr", "loop_start_ms", "loop_end_ms", "group_name"} <= layer_columns
    assert {"is_entry", "group_volumes_json"} <= scene_columns
    assert layer == ("l1", "s1", "a1", 0.5, 0.0, None, None, "ambience")
    assert scene == (
        "s1",
        "Rain",
        0,
        '{"music":1.0,"ambience":1.0,"sfx":1.0}',
    )
    assert applied == MIGRATION_VERSIONS
    assert new_tables == {
        "users",
        "sessions",
        "rule_packs",
        "campaigns",
        "campaign_members",
        "character_identities",
        "character_versions",
        "character_ability_scores",
    }
    assert {"starting_level", "lifecycle", "started_at", "completed_at"} <= campaign_columns
    assert rule_pack == ("dnd5e-2024-srd-5.2.1", "2024", "5.2.1", "CC-BY-4.0")
    backups = list((tmp_path / "backups").glob("legacy-pre-migration-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert "loop_start_ms" not in {
            row[1] for row in backup.execute("PRAGMA table_info(layers)")
        }
        assert backup.execute("SELECT name FROM scenes").fetchone() == ("Rain",)


@pytest.mark.asyncio
async def test_foreign_key_constraint_rejects_invalid_layer(tmp_path):
    db = Database(f"sqlite+aiosqlite:///{tmp_path / 'foreign-key.db'}")
    try:
        await db.create_all()
        with pytest.raises(IntegrityError):
            async with db.engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO layers "
                        "(id, scene_id, audio_file_id, position, loop, volume, pan_lr, "
                        "fade_in_ms, fade_out_ms) VALUES "
                        "('l1','missing-scene','missing-audio',0,1,1.0,0.0,0,0)"
                    )
                )
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_startup_rejects_preexisting_orphan_references(tmp_path):
    db_path = tmp_path / "orphan.db"
    _create_legacy_database(db_path, orphan=True)
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    try:
        with pytest.raises(RuntimeError, match="invalid foreign-key references"):
            await db.create_all()
    finally:
        await db.close()
