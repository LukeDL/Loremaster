"""Runtime configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor the default data dir to the project root (three parents up from this
# file: src/loremaster/config.py -> project root), NOT the current working
# directory. Running uvicorn from any subfolder used to silently create a
# stray data/ next to the cwd; this keeps everyone pointed at the same place.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOREMASTER_", env_file=".env")

    data_dir: Path = _PROJECT_ROOT / "data"
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
