"""Public service configuration and persisted probe outcomes."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from system_monitoring.targets import normalize_url


class ServiceConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=2048)
    enabled: bool = True
    check_interval_seconds: int = Field(default=60, ge=10, le=86400, strict=True)
    timeout_seconds: int = Field(default=5, ge=1, le=30, strict=True)
    failure_threshold: int = Field(default=3, ge=1, le=20, strict=True)
    expected_status: int = Field(default=200, ge=200, le=599, strict=True)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_url(value)

    @model_validator(mode="after")
    def timeout_within_interval(self):
        if self.timeout_seconds >= self.check_interval_seconds:
            raise ValueError("Check timeout must be shorter than the check interval")
        return self


class ServiceResponse(ServiceConfiguration):
    model_config = ConfigDict(extra="ignore")

    id: str
    created_at: str
    revision: int
    status: Literal["unknown", "healthy", "failing", "down", "blocked", "paused"]
    consecutive_failures: int
    last_checked_at: str | None
    last_status_code: int | None
    last_duration_seconds: float | None
    last_error: str | None
    open_incident_id: str | None


class CheckResponse(BaseModel):
    id: int
    service_id: str
    revision: int
    checked_at: str
    outcome: Literal["success", "failure", "blocked"]
    status_code: int | None
    duration_seconds: float
    reason: str | None


class IncidentResponse(BaseModel):
    id: str
    service_id: str
    opened_at: str
    resolved_at: str | None
    reason: str
    resolution: str | None


@dataclass(frozen=True)
class ProbeResult:
    outcome: Literal["success", "failure", "blocked"]
    duration_seconds: float
    status_code: int | None = None
    reason: str | None = None
