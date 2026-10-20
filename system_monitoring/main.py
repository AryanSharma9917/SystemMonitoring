"""Application factory and lifecycle."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest
from starlette.concurrency import run_in_threadpool
from starlette.responses import Response

from system_monitoring import __version__
from system_monitoring.api.authentication import router as auth_router
from system_monitoring.api.dashboard import router as dashboard_router
from system_monitoring.api.errors import error_response, register_error_handlers
from system_monitoring.api.health import router as health_router
from system_monitoring.api.services import register_repository_errors
from system_monitoring.api.services import router as services_router
from system_monitoring.auth import Authentication, require_admin
from system_monitoring.checker import HttpChecker
from system_monitoring.config import Settings
from system_monitoring.logging import configure_logging
from system_monitoring.metrics import Metrics, ServiceCollector
from system_monitoring.monitor import Monitor
from system_monitoring.notifications import WebhookDelivery
from system_monitoring.repository import Repository
from system_monitoring.storage import Database
from system_monitoring.targets import TargetPolicy

logger = logging.getLogger("system_monitoring.requests")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    database = Database(settings.database_path)
    metrics = Metrics()
    policy = TargetPolicy(settings.approved_origins, settings.private_origins)
    repository = Repository(
        database,
        settings.service_limit,
        settings.history_per_service,
        notifications_enabled=bool(settings.webhook_url),
    )
    authentication = Authentication(database, settings)
    delivery = WebhookDelivery(database, settings)
    monitor = Monitor(repository, HttpChecker(policy), settings.check_concurrency)
    metrics.registry.register(ServiceCollector(repository))
    Gauge(
        "monitor_scheduler_last_tick_timestamp_seconds",
        "Last successful scheduler tick.",
        registry=metrics.registry,
    ).set_function(lambda: monitor.last_tick or 0)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_in_threadpool(database.initialize)
        await run_in_threadpool(authentication.bootstrap)
        logging.getLogger("system_monitoring").info("Application storage initialized")
        if settings.scheduler_enabled:
            monitor.start()
        if settings.webhook_url:
            delivery.start()
        try:
            yield
        finally:
            await monitor.stop()
            await delivery.stop()

    app = FastAPI(
        title="System Monitoring",
        description="Service monitoring and incident tracking foundation.",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.database = database
    app.state.policy = policy
    app.state.repository = repository
    app.state.monitor = monitor
    app.state.authentication = authentication
    app.state.delivery = delivery
    app.include_router(health_router)
    app.include_router(services_router)
    app.include_router(auth_router)
    app.include_router(dashboard_router)
    register_repository_errors(app)
    register_error_handlers(app)

    @app.get("/api/v1/about", tags=["About"], dependencies=[Depends(require_admin)])
    def root() -> dict[str, str]:
        return {"name": "System Monitoring", "version": __version__, "docs": "/docs"}

    static = Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.get("/", include_in_schema=False)
    def interface():
        return FileResponse(static / "index.html")

    @app.get("/docs", include_in_schema=False, dependencies=[Depends(require_admin)])
    def docs():
        return get_swagger_ui_html(openapi_url="/openapi.json", title="System Monitoring API")

    @app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(require_admin)])
    def schema():
        return app.openapi()

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        request.state.request_id = str(uuid4())
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Unhandled request error", extra={"request_id": request.state.request_id}
            )
            response = error_response(
                request, 500, "internal_error", "An unexpected error occurred"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                "form-action 'self'; base-uri 'none'"
            )
        response.headers["X-Request-ID"] = request.state.request_id
        route = request.scope.get("route")
        handler = getattr(route, "path", "unmatched")
        if handler != "/metrics":
            metrics.observe(handler, request.method, response.status_code, perf_counter() - started)
        logger.info(
            "Request completed",
            extra={
                "request_id": request.state.request_id,
                "method": request.method,
                # Route templates avoid secret-bearing paths and unbounded labels.
                "route": handler,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            },
        )
        return response

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    return app
