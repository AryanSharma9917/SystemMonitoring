"""Validated settings shared by local development and containers."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from system_monitoring.targets import normalize_url, origin


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MONITOR_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    environment: Literal["development", "demo", "production"] = "development"
    database_path: Path = Path("var/monitoring.sqlite3")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    admin_username: str = Field(default="admin", min_length=1, max_length=100)
    admin_password: SecretStr | None = None
    secure_cookies: bool = False
    session_seconds: int = Field(default=28800, ge=300, le=86400)
    webhook_url: SecretStr | None = None
    webhook_allow_private: bool = False

    @field_validator("admin_password", "webhook_url", mode="before")
    @classmethod
    def empty_secrets_are_unset(cls, value):
        return None if value == "" else value

    @field_validator("admin_password")
    @classmethod
    def strong_bootstrap_password(cls, value):
        if value is not None and not 12 <= len(value.get_secret_value()) <= 1024:
            raise ValueError("Administrator password must contain between 12 and 1024 characters")
        return value

    @model_validator(mode="after")
    def validate_webhook(self):
        if self.webhook_url:
            value = normalize_url(self.webhook_url.get_secret_value())
            if not value.startswith("https://") and not self.webhook_allow_private:
                raise ValueError(
                    "Webhooks require HTTPS unless internal delivery is explicitly enabled"
                )
        if self.environment == "production" and not self.secure_cookies:
            raise ValueError("Production requires secure cookies and HTTPS")
        return self

    approved_origins: list[str] = []
    private_origins: list[str] = []
    scheduler_enabled: bool = True
    check_concurrency: int = Field(default=5, ge=1, le=20)
    service_limit: int = Field(default=100, ge=1, le=1000)
    history_per_service: int = Field(default=1000, ge=10, le=10000)

    @field_validator("approved_origins", "private_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        return [normalize_url(value, origin_only=True) for value in values]

    @model_validator(mode="after")
    def private_origins_are_approved(self):
        if not {origin(value) for value in self.private_origins} <= {
            origin(value) for value in self.approved_origins
        }:
            raise ValueError("Private origins must also appear in approved origins")
        return self

    @field_validator("database_path", mode="before")
    @classmethod
    def require_file_path(cls, value: object) -> object:
        if isinstance(value, str) and (not value.strip() or value == ":memory:"):
            raise ValueError("Use a filesystem path for persistent storage")
        return value
