import os
import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from system_monitoring.backup import snapshot
from system_monitoring.config import Settings
from system_monitoring.main import create_app
from system_monitoring.storage import MIGRATIONS, SCHEMA, Database


def test_live_wal_snapshot_and_restore_preserve_history_and_revoke_sessions(settings, tmp_path):
    with TestClient(create_app(settings)) as client:
        login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "test-operator-password"}
        )
        token = client.cookies.get("monitor_session")
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        service = client.post(
            "/api/v1/services", json={"name": "Site", "url": "https://example.com"}, headers=headers
        ).json()
        database = Database(settings.database_path)
        with database.connect() as connection:
            connection.execute(
                "UPDATE services SET check_token='old', check_lease_until=9999999999"
            )
            connection.execute(
                "INSERT INTO incidents(id,service_id,reason) VALUES('incident',?,'Timeout')",
                (service["id"],),
            )
            connection.execute(
                """INSERT INTO notifications(event_id,incident_id,service_id,event_type,payload,
                created_at,lease_token,lease_until) VALUES('event','incident',?,'opened','{}',
                '2026-01-01T00:00:00Z','old',9999999999)""",
                (service["id"],),
            )
            # Keep a connection open so committed data still resides in the WAL.
            connection.commit()
            assert settings.database_path.with_suffix(".sqlite3-wal").stat().st_size > 0
            backup = tmp_path / "backup.sqlite3"
            assert snapshot(settings.database_path, backup) == 3
        assert os.stat(backup).st_mode & 0o777 == 0o600
        restored = tmp_path / "restored.sqlite3"
        snapshot(backup, restored, restore=True)
        with closing(sqlite3.connect(backup)) as copy:
            assert copy.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        with closing(sqlite3.connect(restored)) as copy:
            assert copy.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
            assert copy.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] == 1
            assert copy.execute("SELECT check_token FROM services").fetchone()[0] is None
            assert copy.execute("SELECT lease_until FROM notifications").fetchone()[0] == 0
        restored_settings = Settings(
            _env_file=None, database_path=restored, scheduler_enabled=False
        )
        with TestClient(create_app(restored_settings)) as recovered:
            recovered.cookies.set("monitor_session", token)
            assert recovered.get("/api/auth/session").status_code == 401
            sign_in = recovered.post(
                "/api/auth/login", json={"username": "admin", "password": "test-operator-password"}
            )
            assert sign_in.status_code == 200
            assert recovered.get("/api/v1/services").json()[0]["id"] == service["id"]


@pytest.mark.parametrize("version", [1, 2])
def test_backup_upgrade_and_rollback_to_previous_schema(tmp_path, version):
    previous, backup = tmp_path / "previous.sqlite3", tmp_path / "backup.sqlite3"
    with closing(sqlite3.connect(previous)) as connection:
        for statement in SCHEMA:
            connection.execute(statement)
        if version == 2:
            for statement in MIGRATIONS[2]:
                connection.execute(statement)
        connection.execute(f"PRAGMA user_version={version}")
        connection.execute(
            "INSERT INTO services(id,name,url) VALUES('s','Existing site','https://example.com')"
        )
        connection.execute("INSERT INTO incidents(id,service_id,reason) VALUES('i','s','Timeout')")
        connection.commit()
    snapshot(previous, backup)
    Database(previous).initialize()
    with closing(sqlite3.connect(previous)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        assert connection.execute("SELECT reason FROM incidents").fetchone()[0] == "Timeout"
    rollback = tmp_path / "rollback.sqlite3"
    snapshot(backup, rollback, restore=True)
    with closing(sqlite3.connect(rollback)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == version
        assert connection.execute("SELECT name FROM services").fetchone()[0] == "Existing site"
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_snapshot_refuses_overwrites_and_never_creates_missing_source(tmp_path):
    missing, output = tmp_path / "missing.sqlite3", tmp_path / "output.sqlite3"
    with pytest.raises(sqlite3.Error):
        snapshot(missing, output)
    assert not missing.exists() and not output.exists()
    output.write_bytes(b"preserve me")
    with pytest.raises(ValueError, match="unused"):
        snapshot(missing, output)
    assert output.read_bytes() == b"preserve me"
    link = tmp_path / "link.sqlite3"
    link.symlink_to(missing)
    with pytest.raises(ValueError):
        snapshot(output, link)
    assert not list(tmp_path.glob(".monitoring-snapshot-*"))


@pytest.mark.parametrize("kind", ["corrupt", "newer", "unrelated", "invalid_reference"])
def test_invalid_backup_never_publishes_destination(tmp_path, kind):
    source, output = tmp_path / "source.sqlite3", tmp_path / "output.sqlite3"
    if kind == "corrupt":
        source.write_bytes(b"not a sqlite file")
    else:
        Database(source).initialize()
        with closing(sqlite3.connect(source)) as connection:
            if kind == "newer":
                connection.execute("PRAGMA user_version=99")
            elif kind == "unrelated":
                connection.execute("DROP TABLE sessions")
            else:
                connection.execute(
                    "INSERT INTO incidents(id,service_id,reason) VALUES('i','missing','Timeout')"
                )
            connection.commit()
    with pytest.raises((ValueError, sqlite3.Error)):
        snapshot(source, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".monitoring-snapshot-*"))
