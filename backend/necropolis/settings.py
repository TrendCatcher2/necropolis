"""Environment config (tech.md "Config"). The only module that reads the environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """`NECROPOLIS_*` variables, with safe defaults. No `.env` file is read: settings come from the environment."""

    model_config = SettingsConfigDict(env_prefix="NECROPOLIS_", env_file=None, extra="ignore", frozen=True)

    probes_disabled: bool = False
    db_path: Path = Path("data/necropolis.db")
    public_url: str | None = None
    # safety.md rule 6: no more than 1 request per second to the archive. Lower is allowed.
    archive_rps: float = Field(default=1.0, gt=0, le=1.0)
    # safety.md rule 4: 1 per second per host by default, adjustable down to 0.2, never above 2.
    probe_rps: float = Field(default=1.0, ge=0.2, le=2.0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
