import sqlite3

import pytest

from system_monitoring.storage import Database


def test_schema_initialization_is_repeatable_and_keeps_data(settings):
    database = Database(settings.database_path)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO services (id, name, url) VALUES (?, ?, ?)",
            ("sample", "Sample service", "https://example.com/health"),
        )
    database.initialize()
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_incidents_require_a_service_and_only_one_open_incident(settings):
    database = Database(settings.database_path)
    database.initialize()
    with pytest.raises(sqlite3.IntegrityError), database.connect() as connection:
        connection.execute(
            "INSERT INTO incidents (id, service_id, reason) VALUES ('a', 'missing', 'Timeout')"
        )
    with database.connect() as connection:
        connection.execute("INSERT INTO services (id, name, url) VALUES ('s', 'Site', 'https://x')")
        connection.execute(
            "INSERT INTO incidents (id, service_id, reason) VALUES ('a', 's', 'Timeout')"
        )
    with pytest.raises(sqlite3.IntegrityError), database.connect() as connection:
        connection.execute(
            "INSERT INTO incidents (id, service_id, reason) VALUES ('b', 's', 'Timeout')"
        )


def test_newer_schema_is_never_downgraded(settings):
    database = Database(settings.database_path)
    database.initialize()
    with database.connect() as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError, match="newer"):
        database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 99


def test_failed_transaction_rolls_back(settings):
    database = Database(settings.database_path)
    database.initialize()
    with pytest.raises(RuntimeError), database.connect() as connection:
        connection.execute("INSERT INTO services (id, name, url) VALUES ('s', 'Site', 'https://x')")
        raise RuntimeError("cancel operation")
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM services").fetchone()[0] == 0
