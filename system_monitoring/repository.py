"""Transactional inventory, check history and incident transitions."""

import time
from datetime import UTC, datetime
from uuid import uuid4

from system_monitoring.models import ProbeResult, ServiceConfiguration
from system_monitoring.notifications import enqueue
from system_monitoring.storage import Database


class MissingService(Exception):
    pass


class ServiceConflict(Exception):
    pass


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Repository:
    def __init__(
        self,
        database: Database,
        service_limit: int,
        history_limit: int,
        notifications_enabled: bool = False,
    ) -> None:
        self.database = database
        self.service_limit = service_limit
        self.history_limit = history_limit
        self.notifications_enabled = notifications_enabled

    def get(self, service_id: str) -> dict:
        with self.database.connect() as connection:
            row = connection.execute(
                """SELECT s.*, i.id AS open_incident_id FROM services s
                LEFT JOIN incidents i ON i.service_id=s.id AND i.resolved_at IS NULL
                WHERE s.id=?""",
                (service_id,),
            ).fetchone()
        if row is None:
            raise MissingService()
        return self.present(dict(row))

    @staticmethod
    def present(result: dict) -> dict:
        if not result["enabled"]:
            result["status"] = "paused"
        elif result["last_outcome"] == "blocked":
            result["status"] = "blocked"
        elif result["open_incident_id"]:
            result["status"] = "down"
        else:
            result["status"] = {
                "unknown": "unknown",
                "success": "healthy",
                "failure": "failing",
            }[result["last_outcome"]]
        return result

    def list_services(self, limit: int, offset: int) -> list[dict]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT s.*, i.id AS open_incident_id FROM services s
                LEFT JOIN incidents i ON i.service_id=s.id AND i.resolved_at IS NULL
                ORDER BY s.created_at, s.id LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        return [self.present(dict(row)) for row in rows]

    def create(self, configuration: ServiceConfiguration) -> dict:
        service_id = str(uuid4())
        values = configuration.model_dump()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if (
                connection.execute("SELECT COUNT(*) FROM services").fetchone()[0]
                >= self.service_limit
            ):
                raise ServiceConflict("Service inventory limit reached")
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            connection.execute(
                f"INSERT INTO services (id, {columns}) VALUES (?, {placeholders})",
                (service_id, *values.values()),
            )
        return self.get(service_id)

    def update(self, service_id: str, configuration: ServiceConfiguration) -> dict:
        values = configuration.model_dump()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
            if old is None:
                raise MissingService()
            target_changed = any(old[key] != values[key] for key in ("url", "expected_status"))
            if target_changed:
                self.close_incidents(connection, dict(old), timestamp(), "configuration_changed")
                connection.execute(
                    """UPDATE services SET last_outcome='unknown', last_checked_at=NULL,
                    last_check_timestamp=NULL, last_status_code=NULL, last_duration_seconds=NULL,
                    last_error=NULL, availability_since=?, availability_revision=revision+1
                    WHERE id=?""",
                    (timestamp(), service_id),
                )
            policy_changed = any(old[key] != values[key] for key in values if key != "name")
            failures = 0 if policy_changed else old["consecutive_failures"]
            assignments = ", ".join(f"{key}=?" for key in values)
            connection.execute(
                f"""UPDATE services SET {assignments}, revision=revision+1,
                consecutive_failures=?, next_check_at=0, check_token=NULL, check_lease_until=0
                WHERE id=?""",
                (*values.values(), failures, service_id),
            )
        return self.get(service_id)

    def delete(self, service_id: str) -> None:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute(
                "SELECT id FROM services WHERE id=?", (service_id,)
            ).fetchone():
                raise MissingService()
            connection.execute(
                "UPDATE notifications SET status='cancelled',last_error='Service removed' "
                "WHERE service_id=? AND status='pending'",
                (service_id,),
            )
            connection.execute("DELETE FROM incidents WHERE service_id=?", (service_id,))
            connection.execute("DELETE FROM services WHERE id=?", (service_id,))

    def due(self, now: float) -> list[str]:
        with self.database.connect() as connection:
            return [
                row[0]
                for row in connection.execute(
                    """SELECT id FROM services WHERE enabled=1 AND next_check_at<=?
                AND check_lease_until<=? ORDER BY next_check_at, id LIMIT ?""",
                    (now, now, self.service_limit),
                )
            ]

    def claim(self, service_id: str, *, force: bool) -> dict:
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
            if row is None:
                raise MissingService()
            now = time.time()
            if not row["enabled"]:
                raise ServiceConflict("Monitoring is paused for this service")
            if row["check_lease_until"] > now:
                raise ServiceConflict("A check is already running for this service")
            if not force and row["next_check_at"] > now:
                raise ServiceConflict("Service is not due for a check")
            token = str(uuid4())
            connection.execute(
                "UPDATE services SET check_token=?, check_lease_until=? WHERE id=?",
                (token, now + row["timeout_seconds"] + 5, service_id),
            )
        return {**dict(row), "check_token": token}

    def record(self, service: dict, result: ProbeResult) -> dict:
        service_id = service["id"]
        checked_at = timestamp()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT * FROM services WHERE id=?", (service_id,)
            ).fetchone()
            if current is None:
                raise MissingService()
            if (
                not current["enabled"]
                or current["revision"] != service["revision"]
                or current["check_token"] != service["check_token"]
            ):
                raise ServiceConflict("Configuration changed while the check was running")
            failures = current["consecutive_failures"] + 1 if result.outcome == "failure" else 0
            if result.outcome == "success":
                self.close_incidents(connection, dict(current), checked_at, "recovered")
            elif result.outcome == "failure" and failures >= current["failure_threshold"]:
                incident_id = str(uuid4())
                inserted = connection.execute(
                    """INSERT INTO incidents (id, service_id, opened_at, reason)
                    SELECT ?, ?, ?, ? WHERE NOT EXISTS (
                        SELECT 1 FROM incidents WHERE service_id=? AND resolved_at IS NULL
                    )""",
                    (incident_id, service_id, checked_at, result.reason, service_id),
                )
                if inserted.rowcount and self.notifications_enabled:
                    enqueue(
                        connection,
                        dict(current),
                        {
                            "id": incident_id,
                            "opened_at": checked_at,
                            "resolved_at": None,
                            "reason": result.reason,
                            "resolution": None,
                        },
                        "incident.opened",
                    )
            cursor = connection.execute(
                """INSERT INTO checks
                (service_id, revision, checked_at, outcome, status_code, duration_seconds, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    service_id,
                    current["revision"],
                    checked_at,
                    result.outcome,
                    result.status_code,
                    result.duration_seconds,
                    result.reason,
                ),
            )
            now = time.time()
            connection.execute(
                """UPDATE services SET consecutive_failures=?, last_checked_at=?,
                last_check_timestamp=?, last_outcome=?, last_status_code=?, last_duration_seconds=?,
                last_error=?, next_check_at=?, check_token=NULL, check_lease_until=0 WHERE id=?""",
                (
                    failures,
                    checked_at,
                    now,
                    result.outcome,
                    result.status_code,
                    result.duration_seconds,
                    result.reason,
                    now + current["check_interval_seconds"],
                    service_id,
                ),
            )
            connection.execute(
                """DELETE FROM checks WHERE service_id=? AND id NOT IN (
                    SELECT id FROM checks WHERE service_id=? ORDER BY id DESC LIMIT ?
                )""",
                (service_id, service_id, self.history_limit),
            )
            return dict(
                connection.execute(
                    "SELECT * FROM checks WHERE id=?", (cursor.lastrowid,)
                ).fetchone()
            )

    def checks(self, service_id: str, limit: int, offset: int) -> list[dict]:
        self.get(service_id)
        with self.database.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM checks WHERE service_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (service_id, limit, offset),
                )
            ]

    def incidents(self, service_id: str | None, status: str | None, limit: int, offset: int):
        conditions, values = [], []
        if service_id is not None:
            self.get(service_id)
            conditions.append("service_id=?")
            values.append(service_id)
        if status is not None:
            conditions.append("resolved_at IS " + ("NULL" if status == "open" else "NOT NULL"))
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.database.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM incidents{where} ORDER BY opened_at DESC, id LIMIT ? OFFSET ?",
                    (*values, limit, offset),
                )
            ]

    def close_incidents(self, connection, service, when, resolution):
        incidents = connection.execute(
            "SELECT * FROM incidents WHERE service_id=? AND resolved_at IS NULL", (service["id"],)
        ).fetchall()
        connection.execute(
            "UPDATE incidents SET resolved_at=?,resolution=? "
            "WHERE service_id=? AND resolved_at IS NULL",
            (when, resolution, service["id"]),
        )
        if self.notifications_enabled:
            for incident in incidents:
                enqueue(
                    connection,
                    service,
                    {
                        "id": incident["id"],
                        "opened_at": incident["opened_at"],
                        "resolved_at": when,
                        "reason": incident["reason"],
                        "resolution": resolution,
                    },
                    "incident.recovered" if resolution == "recovered" else "incident.closed",
                )
