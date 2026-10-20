"""Inventory and check-history API. Operator policy cannot be edited over HTTP."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from system_monitoring.auth import require_admin
from system_monitoring.models import (
    CheckResponse,
    IncidentResponse,
    ServiceConfiguration,
    ServiceResponse,
)
from system_monitoring.repository import MissingService, ServiceConflict
from system_monitoring.targets import TargetBlocked

router = APIRouter(prefix="/api/v1", tags=["Monitoring"], dependencies=[Depends(require_admin)])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def approve(request: Request, configuration: ServiceConfiguration) -> None:
    try:
        request.app.state.policy.validate(configuration.url)
    except TargetBlocked as error:
        raise HTTPException(422, str(error)) from error


@router.post("/services", response_model=ServiceResponse, status_code=201)
def create_service(request: Request, configuration: ServiceConfiguration, response: Response):
    approve(request, configuration)
    service = request.app.state.repository.create(configuration)
    response.headers["Location"] = f"/api/v1/services/{service['id']}"
    return service


@router.get("/services", response_model=list[ServiceResponse])
def list_services(request: Request, limit: Limit = 50, offset: Offset = 0):
    return request.app.state.repository.list_services(limit, offset)


@router.get("/services/{service_id}", response_model=ServiceResponse)
def get_service(service_id: str, request: Request):
    return request.app.state.repository.get(service_id)


@router.put("/services/{service_id}", response_model=ServiceResponse)
def update_service(service_id: str, configuration: ServiceConfiguration, request: Request):
    previous = request.app.state.repository.get(service_id)
    # Operators can pause a target even after removing its origin from policy.
    if configuration.enabled or configuration.url != previous["url"]:
        approve(request, configuration)
    return request.app.state.repository.update(service_id, configuration)


@router.delete("/services/{service_id}", status_code=204)
def delete_service(service_id: str, request: Request):
    """Permanently remove this service, its check history and its incidents."""
    request.app.state.repository.delete(service_id)
    return Response(status_code=204)


@router.post("/services/{service_id}/checks", response_model=CheckResponse, status_code=201)
async def check_service(service_id: str, request: Request):
    return await request.app.state.monitor.check(service_id)


@router.get("/services/{service_id}/checks", response_model=list[CheckResponse])
def list_checks(service_id: str, request: Request, limit: Limit = 50, offset: Offset = 0):
    return request.app.state.repository.checks(service_id, limit, offset)


@router.get("/incidents", response_model=list[IncidentResponse])
def list_incidents(
    request: Request,
    service_id: str | None = None,
    status: Literal["open", "resolved"] | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    return request.app.state.repository.incidents(service_id, status, limit, offset)


def register_repository_errors(app):
    @app.exception_handler(MissingService)
    async def missing(request, error):
        from system_monitoring.api.errors import error_response

        return error_response(request, 404, "not_found", "Service not found")

    @app.exception_handler(ServiceConflict)
    async def conflict(request, error):
        from system_monitoring.api.errors import error_response

        return error_response(request, 409, "conflict", str(error))
