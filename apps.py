"""Compatibility entry point for existing `uvicorn apps:app` commands."""

from system_monitoring.main import create_app

app = create_app()
