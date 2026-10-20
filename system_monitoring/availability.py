"""Observed check success, with explicit sample coverage and retention limits."""

from datetime import UTC, datetime, timedelta


def summarize(database, history_limit: int, hours: int, service_id=None) -> list[dict]:
    end = datetime.now(UTC)
    start = (end - timedelta(hours=hours)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    stop = end.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    with database.connect() as connection:
        connection.execute("BEGIN")
        services = connection.execute(
            "SELECT id, availability_since, availability_revision FROM services"
            + (" WHERE id=?" if service_id else ""),
            (service_id,) if service_id else (),
        ).fetchall()
        results = []
        for service in services:
            effective_start = max(start, service["availability_since"] or start)
            row = connection.execute(
                """SELECT COUNT(*) AS observations,
                COALESCE(SUM(outcome='success'),0) AS successes,
                COALESCE(SUM(outcome='failure'),0) AS failures,
                COALESCE(SUM(outcome='blocked'),0) AS blocked,
                MIN(checked_at) AS first_observation_at,MAX(checked_at) AS last_observation_at
                FROM checks WHERE service_id=? AND checked_at>=? AND checked_at<=?
                AND revision>=?""",
                (service["id"], effective_start, stop, service["availability_revision"]),
            ).fetchone()
            retained = connection.execute(
                "SELECT COUNT(*),MIN(checked_at) FROM checks WHERE service_id=?", (service["id"],)
            ).fetchone()
            known = row["successes"] + row["failures"]
            results.append(
                {
                    **dict(row),
                    "service_id": service["id"],
                    "window_hours": hours,
                    "window_start": start,
                    "window_end": stop,
                    "effective_start": effective_start,
                    "success_percentage": round(100 * row["successes"] / known, 2)
                    if known
                    else None,
                    "history_may_be_truncated": bool(
                        retained[0] >= history_limit and retained[1] > effective_start
                    ),
                }
            )
    return results
