"""Liveness and dependency readiness endpoints."""

import logging
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["Health"])
logger = logging.getLogger("system_monitoring.health")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    database: Literal["ok"] = "ok"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Process liveness; does not depend on storage or external services."""
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse)
def ready(request: Request) -> ReadyResponse:
    """Ready to serve only when the persistent schema is accessible."""
    try:
        request.app.state.database.check()
    except (sqlite3.Error, RuntimeError, OSError) as error:
        logger.warning(
            "Storage readiness check failed", extra={"request_id": request.state.request_id}
        )
        raise HTTPException(503, "Persistent storage is unavailable") from error
    if request.app.state.settings.scheduler_enabled and not request.app.state.monitor.ready():
        raise HTTPException(503, "Monitoring scheduler is unavailable")
    if request.app.state.settings.webhook_url and not request.app.state.delivery.ready():
        raise HTTPException(503, "Webhook delivery worker is unavailable")
    return ReadyResponse()
