"""SQLite schema and connection management for a single application instance."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

SCHEMA_VERSION = 2
SCHEMA = (
    """CREATE TABLE services (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        url TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        check_interval_seconds INTEGER NOT NULL DEFAULT 60
            CHECK (check_interval_seconds >= 10),
        timeout_seconds INTEGER NOT NULL DEFAULT 10 CHECK (timeout_seconds > 0),
        failure_threshold INTEGER NOT NULL DEFAULT 3 CHECK (failure_threshold > 0),
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )""",
    """CREATE TABLE incidents (
        id TEXT PRIMARY KEY,
        service_id TEXT NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
        opened_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        resolved_at TEXT,
        reason TEXT NOT NULL,
        CHECK (resolved_at IS NULL OR resolved_at >= opened_at)
    )""",
    """CREATE UNIQUE INDEX one_open_incident_per_service
        ON incidents(service_id) WHERE resolved_at IS NULL""",
    "CREATE INDEX incidents_service_history ON incidents(service_id, opened_at)",
)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            # Acquire a write lock before reading the version so concurrent starts
            # cannot both attempt to create the initial schema.
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                for statement in SCHEMA:
                    connection.execute(statement)
                version = 1
            if version > SCHEMA_VERSION:
                raise RuntimeError("Database schema is newer than this application supports")
            for target_version in range(version + 1, SCHEMA_VERSION + 1):
                for statement in MIGRATIONS[target_version]:
                    connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.check()

    def check(self) -> None:
        # mode=rw avoids silently recreating a database deleted after startup.
        uri = self.path.resolve().as_uri() + "?mode=rw"
        with closing(sqlite3.connect(uri, uri=True, timeout=1)) as connection:
            # Verify write access as well as schema visibility. Closing rolls back
            # this empty transaction without changing application data.
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise RuntimeError("Database schema is not initialized")
            connection.execute("SELECT id, revision, check_token FROM services LIMIT 1").fetchall()
            connection.execute("SELECT id FROM checks LIMIT 1").fetchall()
            connection.execute("SELECT id FROM incidents LIMIT 1").fetchall()


# Each migration runs in the same transaction as its schema-version update.
MIGRATIONS = {
    2: (
        "ALTER TABLE services ADD COLUMN expected_status INTEGER NOT NULL DEFAULT 200",
        "ALTER TABLE services ADD COLUMN revision INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE services ADD COLUMN consecutive_failures INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE services ADD COLUMN last_checked_at TEXT",
        "ALTER TABLE services ADD COLUMN last_check_timestamp REAL",
        "ALTER TABLE services ADD COLUMN last_outcome TEXT NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE services ADD COLUMN last_status_code INTEGER",
        "ALTER TABLE services ADD COLUMN last_duration_seconds REAL",
        "ALTER TABLE services ADD COLUMN last_error TEXT",
        "ALTER TABLE services ADD COLUMN next_check_at REAL NOT NULL DEFAULT 0",
        "ALTER TABLE services ADD COLUMN check_token TEXT",
        "ALTER TABLE services ADD COLUMN check_lease_until REAL NOT NULL DEFAULT 0",
        "ALTER TABLE incidents ADD COLUMN resolution TEXT",
        """CREATE TABLE checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id TEXT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
            revision INTEGER NOT NULL,
            checked_at TEXT NOT NULL,
            outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'blocked')),
            status_code INTEGER,
            duration_seconds REAL NOT NULL,
            reason TEXT
        )""",
        "CREATE INDEX checks_service_history ON checks(service_id, id DESC)",
    ),
}
