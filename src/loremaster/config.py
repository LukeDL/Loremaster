"""Runtime configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_LEGACY_DATA_DIR = _PROJECT_ROOT / "data"


def default_data_dir(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return a user-writable, platform-appropriate application data folder."""
    platform = platform or sys.platform
    environment = os.environ if environ is None else environ
    home = home or Path.home()
    if platform == "win32":
        root = Path(
            environment.get("LOCALAPPDATA")
            or environment.get("APPDATA")
            or home / "AppData/Local"
        )
        return root / "Loremaster"
    if platform == "darwin":
        return home / "Library/Application Support/Loremaster"
    root = Path(environment.get("XDG_DATA_HOME", home / ".local/share"))
    return root / "loremaster"


def _initial_data_dir() -> Path:
    """Keep an existing source-checkout database visible during the transition."""
    if (_LEGACY_DATA_DIR / "loremaster.db").is_file():
        return _LEGACY_DATA_DIR
    return default_data_dir()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOREMASTER_", env_file=".env")

    data_dir: Path = _initial_data_dir()
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
