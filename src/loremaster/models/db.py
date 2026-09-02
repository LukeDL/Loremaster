"""SQLAlchemy async models — SQLite storage for scenes and audio file metadata."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


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
        self.engine = create_async_engine(url, echo=False, future=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await self._ensure_columns(conn)

    async def _ensure_columns(self, conn) -> None:
        """Idempotent ALTER TABLE ADD COLUMN for columns added after initial
        release. Base.metadata.create_all only creates missing tables — it
        never adds columns to existing ones (see ISSUES.md #2)."""
        additions = [
            ("scenes", "is_entry", "BOOLEAN NOT NULL DEFAULT 0"),
            ("layers", "pan_lr", "REAL NOT NULL DEFAULT 0.0"),
        ]
        for table, column, decl in additions:
            result = await conn.execute(text(f"PRAGMA table_info({table})"))
            existing = {row[1] for row in result}
            if column not in existing:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {decl}"))

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as sess:
            yield sess

    async def close(self) -> None:
        await self.engine.dispose()


def uuid_str(u: UUID | str) -> str:
    return str(u)
