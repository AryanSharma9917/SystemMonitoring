import pytest
from fastapi.testclient import TestClient

from system_monitoring.config import Settings
from system_monitoring.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "monitoring.sqlite3", _env_file=None)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client
