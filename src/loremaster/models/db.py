"""SQLAlchemy async models — SQLite storage for scenes and audio file metadata."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
import logging
from pathlib import Path
import sqlite3
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from loremaster.models.migrations import MIGRATION_VERSIONS, apply_migrations


log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username_key", name="uq_users_username_key"),
        CheckConstraint("role IN ('player', 'gm')", name="ck_users_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(50))
    username_key: Mapped[str] = mapped_column(String(50))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="1")
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    password_changed_at: Mapped[datetime]

    sessions: Mapped[list["SessionRow"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class SessionRow(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    csrf_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime] = mapped_column(index=True)
    last_seen_at: Mapped[datetime]

    user: Mapped[UserRow] = relationship(back_populates="sessions")


class RulePackRow(Base):
    __tablename__ = "rule_packs"
    __table_args__ = (UniqueConstraint("key", "version", name="uq_rule_packs_key_version"),)

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    system: Mapped[str] = mapped_column(String(50))
    edition: Mapped[str] = mapped_column(String(50))
    version: Mapped[str] = mapped_column(String(50))
    license_name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime]

    campaigns: Mapped[list["CampaignRow"]] = relationship(back_populates="rule_pack")


class CampaignRow(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "max_characters_per_player BETWEEN 1 AND 100",
            name="ck_campaigns_character_limit",
        ),
        CheckConstraint("starting_level BETWEEN 1 AND 20", name="ck_campaigns_starting_level"),
        CheckConstraint(
            "lifecycle IN ('planning', 'in_progress', 'completed')",
            name="ck_campaigns_lifecycle",
        ),
        Index(
            "uq_campaigns_one_active",
            "is_active",
            unique=True,
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    rule_pack_id: Mapped[str] = mapped_column(ForeignKey("rule_packs.id"), index=True)
    max_characters_per_player: Mapped[int] = mapped_column(default=3, server_default="3")
    starting_level: Mapped[int] = mapped_column(default=1, server_default="1")
    lifecycle: Mapped[str] = mapped_column(String(20), default="planning", server_default="planning")
    is_active: Mapped[bool] = mapped_column(default=False, server_default="0")
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    rule_pack: Mapped[RulePackRow] = relationship(back_populates="campaigns")
    memberships: Mapped[list["CampaignMemberRow"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    character_versions: Mapped[list["CharacterVersionRow"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
    )


class CampaignMemberRow(Base):
    __tablename__ = "campaign_members"

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at: Mapped[datetime]

    campaign: Mapped[CampaignRow] = relationship(back_populates="memberships")
    user: Mapped[UserRow] = relationship()


class CharacterIdentityRow(Base):
    __tablename__ = "character_identities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    owner: Mapped[UserRow] = relationship()
    versions: Mapped[list["CharacterVersionRow"]] = relationship(
        back_populates="identity",
        cascade="all, delete-orphan",
    )


class CharacterVersionRow(Base):
    __tablename__ = "character_versions"
    __table_args__ = (
        UniqueConstraint(
            "character_identity_id",
            "campaign_id",
            name="uq_character_versions_identity_campaign",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'dead', 'retired')",
            name="ck_character_versions_status",
        ),
        CheckConstraint("level BETWEEN 1 AND 20", name="ck_character_versions_level"),
        Index(
            "uq_character_versions_one_active",
            "campaign_id",
            "owner_user_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    character_identity_id: Mapped[str] = mapped_column(
        ForeignKey("character_identities.id", ondelete="CASCADE"),
        index=True,
    )
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        index=True,
    )
    source_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("character_versions.id", ondelete="SET NULL"),
        default=None,
    )
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    level: Mapped[int]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    identity: Mapped[CharacterIdentityRow] = relationship(back_populates="versions")
    owner: Mapped[UserRow] = relationship()
    campaign: Mapped[CampaignRow] = relationship(back_populates="character_versions")
    ability_scores: Mapped["CharacterAbilityScoresRow | None"] = relationship(
        back_populates="character_version",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CharacterAbilityScoresRow(Base):
    __tablename__ = "character_ability_scores"
    __table_args__ = (
        CheckConstraint(
            "method IN ('standard_array', 'point_buy')",
            name="ck_character_ability_scores_method",
        ),
        *(
            CheckConstraint(
                f"{ability} IS NULL OR {ability} BETWEEN 8 AND 15",
                name=f"ck_character_ability_scores_{ability}",
            )
            for ability in (
                "strength",
                "dexterity",
                "constitution",
                "intelligence",
                "wisdom",
                "charisma",
            )
        ),
    )

    character_version_id: Mapped[str] = mapped_column(
        ForeignKey("character_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    method: Mapped[str] = mapped_column(String(20))
    strength: Mapped[int | None]
    dexterity: Mapped[int | None]
    constitution: Mapped[int | None]
    intelligence: Mapped[int | None]
    wisdom: Mapped[int | None]
    charisma: Mapped[int | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    completed_at: Mapped[datetime | None]

    character_version: Mapped[CharacterVersionRow] = relationship(
        back_populates="ability_scores"
    )


class AudioFileRow(Base):
    __tablename__ = "audio_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID as str
    original_name: Mapped[str] = mapped_column(String(500))
    path: Mapped[str] = mapped_column(String(500))
    duration_ms: Mapped[int]
    sample_rate: Mapped[int]
    channels: Mapped[int]
    size_bytes: Mapped[int]
    created_at: Mapped[datetime]

    layers: Mapped[list["LayerRow"]] = relationship(back_populates="audio_file")


class SceneRow(Base):
    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    on_end_json: Mapped[str] = mapped_column(Text)  # JSON serialized OnEndPolicy
    group_volumes_json: Mapped[str] = mapped_column(
        Text,
        default='{"music":1.0,"ambience":1.0,"sfx":1.0}',
        server_default='{"music":1.0,"ambience":1.0,"sfx":1.0}',
    )
    # Campaign graph opt-in: False keeps the scene in the palette only
    is_on_map: Mapped[bool] = mapped_column(default=False)
    # Node position on the campaign graph — null means "place on next open slot"
    graph_x: Mapped[float | None] = mapped_column(default=None)
    graph_y: Mapped[float | None] = mapped_column(default=None)
    # Singleton campaign entry scene. Enforced by the set_entry_scene helper,
    # not by a DB constraint (SQLite makes partial unique indexes clunky).
    is_entry: Mapped[bool] = mapped_column(default=False, server_default="0")
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    layers: Mapped[list["LayerRow"]] = relationship(
        back_populates="scene",
        cascade="all, delete-orphan",
        order_by="LayerRow.position",
    )


class LayerRow(Base):
    __tablename__ = "layers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"))
    audio_file_id: Mapped[str] = mapped_column(ForeignKey("audio_files.id"))
    position: Mapped[int]  # ordering within scene
    loop: Mapped[bool]
    volume: Mapped[float]
    group_name: Mapped[str] = mapped_column(String(16), default="ambience", server_default="ambience")
    pan_lr: Mapped[float] = mapped_column(default=0.0, server_default="0.0")
    fade_in_ms: Mapped[int]
    fade_out_ms: Mapped[int]
    loop_start_ms: Mapped[int | None] = mapped_column(default=None)
    loop_end_ms: Mapped[int | None] = mapped_column(default=None)

    scene: Mapped["SceneRow"] = relationship(back_populates="layers")
    audio_file: Mapped["AudioFileRow"] = relationship(back_populates="layers")


class Database:
    """Async SQLite session factory. One instance per app."""

    def __init__(self, url: str) -> None:
        self._sqlite_path = _sqlite_file_path(url)
        self.engine = create_async_engine(url, echo=False, future=True)
        event.listen(self.engine.sync_engine, "connect", _enable_sqlite_foreign_keys)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        backup = self._backup_before_pending_migrations()
        if backup is not None:
            log.info("created pre-migration database backup at %s", backup)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await apply_migrations(conn)
            violations = (await conn.execute(text("PRAGMA foreign_key_check"))).fetchall()
            if violations:
                details = ", ".join(
                    f"{table}[rowid={rowid}] -> {parent}" for table, rowid, parent, _ in violations
                )
                raise RuntimeError(f"database contains invalid foreign-key references: {details}")

    def _backup_before_pending_migrations(self) -> Path | None:
        path = self._sqlite_path
        if path is None or not path.is_file() or not _has_pending_migrations(path):
            return None
        backup_dir = path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        applied = _applied_migration_versions(path)
        next_version = len(applied) + 1
        backup = backup_dir / f"{path.stem}-pre-migration-{next_version:03d}{path.suffix}"
        if backup.exists():
            return backup
        with sqlite3.connect(path) as source, sqlite3.connect(backup) as destination:
            source.backup(destination)
        return backup

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as sess:
            yield sess

    async def close(self) -> None:
        await self.engine.dispose()


def uuid_str(u: UUID | str) -> str:
    return str(u)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _sqlite_file_path(url: str) -> Path | None:
    parsed = make_url(url)
    if not parsed.drivername.startswith("sqlite") or parsed.database in (None, ":memory:"):
        return None
    return Path(parsed.database).resolve()


def _applied_migration_versions(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if table is None:
            return set()
        return {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}


def _has_pending_migrations(path: Path) -> bool:
    return not MIGRATION_VERSIONS.issubset(_applied_migration_versions(path))
