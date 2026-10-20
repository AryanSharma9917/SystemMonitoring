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


def test_scheduler_checks_real_service_and_stops_cleanly(tmp_path, target_server):
    import time

    from system_monitoring.config import Settings

    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "scheduled.sqlite3",
        approved_origins=[target_server.url],
        private_origins=[target_server.url],
        scheduler_enabled=True,
        admin_password="test-operator-password",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        from conftest import sign_in

        sign_in(client)
        service = client.post(
            "/api/v1/services",
            json={
                "name": "Live service",
                "url": target_server.url,
                "failure_threshold": 1,
                "check_interval_seconds": 10,
                "timeout_seconds": 1,
            },
        ).json()
        path = f"/api/v1/services/{service['id']}"
        deadline = time.monotonic() + 5
        while client.get(path).json()["status"] != "healthy":
            assert time.monotonic() < deadline, "Scheduler never checked the registered service"
            time.sleep(0.05)
        assert target_server.paths
        assert client.get("/ready").status_code == 200
        assert "monitor_service_up{" in client.get("/metrics").text
        target_server.status = 503
        client.post(path + "/checks")
        assert client.get(path).json()["status"] == "down"
    assert application.state.monitor.task.done()
    with TestClient(
        create_app(settings.model_copy(update={"scheduler_enabled": False}))
    ) as restarted:
        from conftest import sign_in

        sign_in(restarted)
        assert restarted.get(path).json()["status"] == "down"
        assert len(restarted.get("/api/v1/incidents?status=open").json()) == 1
        assert "monitor_service_up{" in restarted.get("/metrics").text
        assert restarted.post(path + "/checks").json()["outcome"] == "failure"
        assert len(restarted.get("/api/v1/incidents?status=open").json()) == 1
        target_server.status = 200
        assert restarted.post(path + "/checks").json()["outcome"] == "success"
        assert restarted.get("/api/v1/incidents").json()[0]["resolution"] == "recovered"


def test_failed_migration_rolls_back_all_schema_changes(tmp_path, monkeypatch):
    from system_monitoring.storage import MIGRATIONS, SCHEMA, Database

    database = Database(tmp_path / "migration.sqlite3")
    with database.connect() as connection:
        for statement in SCHEMA:
            connection.execute(statement)
        connection.execute("PRAGMA user_version=1")
    monkeypatch.setitem(MIGRATIONS, 2, (*MIGRATIONS[2], "THIS IS NOT VALID SQL"))
    with pytest.raises(sqlite3.OperationalError):
        database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        columns = [row[1] for row in connection.execute("PRAGMA table_info(services)")]
        assert "revision" not in columns


def test_stopped_scheduler_fails_readiness_without_breaking_liveness(settings):
    from system_monitoring.main import create_app

    application = create_app(settings.model_copy(update={"scheduler_enabled": True}))
    with TestClient(application) as client:
        assert client.get("/ready").status_code == 200
        client.portal.call(application.state.monitor.stop)
        assert client.get("/ready").status_code == 503
        assert client.get("/health").status_code == 200
