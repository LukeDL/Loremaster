"""Runtime configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOREMASTER_", env_file=".env")

    data_dir: Path = Path("data")
    host: str = "0.0.0.0"
    port: int = 8765
    sample_rate: int = 48_000
    block_size: int = 1024
    audio_device: int | str | None = None

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "loremaster.db"

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path.resolve()}"


settings = Settings()
