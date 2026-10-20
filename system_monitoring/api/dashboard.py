"""Authenticated dashboard summaries and delivery visibility."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from system_monitoring.auth import require_admin
from system_monitoring.availability import summarize

router = APIRouter(prefix="/api/v1", tags=["Dashboard"], dependencies=[Depends(require_admin)])
Hours = Annotated[int, Query(ge=1, le=168)]


@router.get("/dashboard")
def dashboard(request: Request, window_hours: Hours = 24):
    repository = request.app.state.repository
    services = repository.list_services(repository.service_limit, 0)
    availability = summarize(repository.database, repository.history_limit, window_hours)
    settings = request.app.state.settings
    return {
        "services": services,
        "availability": availability,
        "incidents": repository.incidents(None, "open", 100, 0),
        "counts": {
            state: sum(service["status"] == state for service in services)
            for state in ("healthy", "failing", "down", "blocked", "paused", "unknown")
        },
        "total": len(services),
        "open_incidents": sum(s["open_incident_id"] is not None for s in services),
        "environment": settings.environment,
        "approved_origins": settings.approved_origins,
        "scheduler_enabled": settings.scheduler_enabled,
        "webhook_configured": bool(settings.webhook_url),
    }


@router.get("/services/{service_id}/availability")
def availability(service_id: str, request: Request, window_hours: Hours = 24):
    repository = request.app.state.repository
    repository.get(service_id)
    return summarize(repository.database, repository.history_limit, window_hours, service_id)[0]


@router.get("/notifications")
def notifications(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    with request.app.state.database.connect() as connection:
        rows = connection.execute(
            """SELECT event_id,incident_id,service_id,event_type,created_at,status,
            attempts,last_error,delivered_at,next_attempt_at,
            json_extract(payload,'$.service.name') AS service_name FROM notifications
            ORDER BY id DESC LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    return {
        "configured": bool(request.app.state.settings.webhook_url),
        "worker_healthy": request.app.state.delivery.ready(),
        "deliveries": [dict(row) for row in rows],
    }


@router.post("/notifications/{event_id}/retry", status_code=202)
def retry(event_id: str, request: Request):
    if not request.app.state.settings.webhook_url:
        raise HTTPException(409, "Configure a webhook destination before retrying")
    with request.app.state.database.connect() as connection:
        result = connection.execute(
            """UPDATE notifications SET status='pending',attempts=0,next_attempt_at=0,
            last_error=NULL,lease_token=NULL,lease_until=0 WHERE event_id=? AND status='failed'""",
            (event_id,),
        )
        if not result.rowcount:
            raise HTTPException(409, "Only failed deliveries can be retried")
    return {"status": "pending"}
