"""Small, ordered SQLite migrations for local Loremaster databases."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


MigrationAction = Callable[[AsyncConnection], Awaitable[None]]


@dataclass(frozen=True)
class Migration:
    version: str
    apply: MigrationAction


async def _column_names(conn: AsyncConnection, table: str) -> set[str]:
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    return {row[1] for row in result}


async def _add_column(
    conn: AsyncConnection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    if column not in await _column_names(conn, table):
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"))
    if column not in await _column_names(conn, table):
        raise RuntimeError(f"migration failed to add {table}.{column}")


async def _add_loop_region_columns(conn: AsyncConnection) -> None:
    await _add_column(conn, "layers", "loop_start_ms", "INTEGER")
    await _add_column(conn, "layers", "loop_end_ms", "INTEGER")


async def _add_scene_entry(conn: AsyncConnection) -> None:
    await _add_column(conn, "scenes", "is_entry", "BOOLEAN NOT NULL DEFAULT 0")


async def _add_layer_pan(conn: AsyncConnection) -> None:
    await _add_column(conn, "layers", "pan_lr", "REAL NOT NULL DEFAULT 0.0")


async def _add_lookup_indexes(conn: AsyncConnection) -> None:
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_layers_scene_id ON layers(scene_id)"))
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_layers_audio_file_id ON layers(audio_file_id)")
    )
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_scenes_name ON scenes(name)"))


async def _add_mixer_groups(conn: AsyncConnection) -> None:
    await _add_column(
        conn,
        "scenes",
        "group_volumes_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    initialize_groups = text(
        "UPDATE scenes SET group_volumes_json = :volumes WHERE group_volumes_json = '{}'"
    )
    await conn.execute(
        initialize_groups,
        {"volumes": '{"music":1.0,"ambience":1.0,"sfx":1.0}'},
    )
    await _add_column(conn, "layers", "group_name", "VARCHAR(16) NOT NULL DEFAULT 'ambience'")


async def _create_auth_tables(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS users ("
            "id VARCHAR(36) PRIMARY KEY, "
            "username VARCHAR(50) NOT NULL, "
            "username_key VARCHAR(50) NOT NULL, "
            "password_hash TEXT NOT NULL, "
            "role VARCHAR(16) NOT NULL CHECK (role IN ('player', 'gm')), "
            "is_active BOOLEAN NOT NULL DEFAULT 1, "
            "created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL, "
            "password_changed_at DATETIME NOT NULL, "
            "CONSTRAINT uq_users_username_key UNIQUE (username_key))"
        )
    )
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "token_hash VARCHAR(64) PRIMARY KEY, "
            "user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
            "csrf_hash VARCHAR(64) NOT NULL, "
            "created_at DATETIME NOT NULL, "
            "expires_at DATETIME NOT NULL, "
            "last_seen_at DATETIME NOT NULL)"
        )
    )
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id)"))
    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_expires_at ON sessions(expires_at)"))


MIGRATIONS = (
    Migration("001_add_loop_region_columns", _add_loop_region_columns),
    Migration("002_add_scene_entry", _add_scene_entry),
    Migration("003_add_layer_pan", _add_layer_pan),
    Migration("004_add_lookup_indexes", _add_lookup_indexes),
    Migration("005_add_mixer_groups", _add_mixer_groups),
    Migration("006_create_auth_tables", _create_auth_tables),
)
MIGRATION_VERSIONS = frozenset(migration.version for migration in MIGRATIONS)


async def apply_migrations(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
    )
    result = await conn.execute(text("SELECT version FROM schema_migrations"))
    applied = {row[0] for row in result}

    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        await migration.apply(conn)
        await conn.execute(
            text("INSERT INTO schema_migrations(version, applied_at) VALUES (:version, :applied_at)"),
            {
                "version": migration.version,
                "applied_at": datetime.now(UTC).isoformat(),
            },
        )
