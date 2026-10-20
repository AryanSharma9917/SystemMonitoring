"""One public error shape for routing, validation and dependency failures."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: list | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "error": {"code": code, "message": message, "details": details or []},
            "request_id": request.state.request_id,
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        codes = {
            404: "not_found",
            405: "method_not_allowed",
            422: "validation_error",
            503: "not_ready",
        }
        return error_response(
            request,
            error.status_code,
            codes.get(error.status_code, "request_failed"),
            str(error.detail),
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        # Validation input/context can contain user-supplied secrets. Return only
        # field locations, error types and explanatory messages.
        details = [
            {"location": item["loc"], "type": item["type"], "message": item["msg"]}
            for item in error.errors()
        ]
        return error_response(request, 422, "validation_error", "Invalid request", details)
