import sqlite3

import pytest
from fastapi.testclient import TestClient

from system_monitoring.main import create_app


def test_services_and_incidents_survive_application_restart(settings):
    with TestClient(create_app(settings)) as first:
        database = first.app.state.database
        with database.connect() as connection:
            connection.execute(
                "INSERT INTO services (id, name, url) VALUES ('s', 'Example', 'https://example.com')"
            )
            connection.execute(
                "INSERT INTO incidents (id, service_id, reason) VALUES ('i', 's', 'Timeout')"
            )
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/ready").status_code == 200
        with restarted.app.state.database.connect() as connection:
            assert connection.execute("SELECT name FROM services").fetchone()[0] == "Example"
            assert connection.execute("SELECT reason FROM incidents").fetchone()[0] == "Timeout"


def test_unusable_storage_prevents_startup(settings):
    settings.database_path.mkdir()
    with pytest.raises(sqlite3.OperationalError), TestClient(create_app(settings)):
        pytest.fail("Application started without usable storage")
