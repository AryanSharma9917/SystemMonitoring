"""Validated settings shared by local development and containers."""

from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MONITOR_", env_file=".env", extra="ignore")

    environment: Literal["development", "demo", "production"] = "development"
    database_path: Path = Path("var/monitoring.sqlite3")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("database_path", mode="before")
    @classmethod
    def require_file_path(cls, value: object) -> object:
        if isinstance(value, str) and (not value.strip() or value == ":memory:"):
            raise ValueError("Use a filesystem path for persistent storage")
        return value
