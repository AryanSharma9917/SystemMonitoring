import asyncio

import pytest

from system_monitoring.models import ProbeResult
from system_monitoring.repository import ServiceConflict

CONFIG = {"name": "Example API", "url": "https://example.com/health", "failure_threshold": 2}


class ScriptedChecker:
    def __init__(self, results):
        self.results = iter(results)

    async def probe(self, service):
        await asyncio.sleep(0)
        return next(self.results)


def create(client, **changes):
    response = client.post("/api/v1/services", json={**CONFIG, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_service_inventory_edit_pause_resume_and_delete(client):
    service = create(client)
    url = f"/api/v1/services/{service['id']}"
    assert service["status"] == "unknown"
    assert client.get(url).json()["url"] == CONFIG["url"]
    assert len(client.get("/api/v1/services").json()) == 1
    assert client.put(url, json={**CONFIG, "enabled": False}).json()["status"] == "paused"
    assert client.post(url + "/checks").status_code == 409
    assert client.put(url, json=CONFIG).json()["status"] == "unknown"
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    assert client.post(url + "/checks").status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "http://example.com"},
        {"name": "  "},
        {"timeout_seconds": 31},
        {"check_interval_seconds": 0},
        {"failure_threshold": 0},
        {"expected_status": 999},
        {"url": "https://example.com:444/health"},
        {"unexpected_field": True},
    ],
)
def test_invalid_service_configuration_is_rejected(client, changes):
    assert client.post("/api/v1/services", json={**CONFIG, **changes}).status_code == 422
    assert client.get("/api/v1/services").json() == []


def test_failure_threshold_one_incident_and_recovery(client, app):
    failure = ProbeResult("failure", 0.2, 503, "Unexpected HTTP status 503")
    success = ProbeResult("success", 0.1, 200)
    app.state.monitor.checker = ScriptedChecker([failure, failure, failure, success])
    service = create(client)
    url = f"/api/v1/services/{service['id']}"
    assert client.post(url + "/checks").status_code == 201
    assert client.get(url).json()["status"] == "failing"
    assert client.get("/api/v1/incidents").json() == []
    client.post(url + "/checks")
    client.post(url + "/checks")
    incidents = client.get("/api/v1/incidents?status=open").json()
    assert len(incidents) == 1
    assert client.get(url).json()["status"] == "down"
    assert client.post(url + "/checks").json()["outcome"] == "success"
    assert client.get("/api/v1/incidents?status=open").json() == []
    resolved = client.get("/api/v1/incidents?status=resolved").json()
    assert len(resolved) == 1 and resolved[0]["resolution"] == "recovered"
    assert resolved[0]["resolved_at"] is not None
    assert client.get(url).json()["consecutive_failures"] == 0
    history = client.get(url + "/checks?limit=2").json()
    assert [check["outcome"] for check in history] == ["success", "failure"]
    assert client.delete(url).status_code == 204
    assert client.get("/api/v1/incidents").json() == []
    assert service["id"] not in client.get("/metrics").text


def test_blocked_checks_do_not_open_or_resolve_incidents(client, app):
    app.state.monitor.checker = ScriptedChecker(
        [
            ProbeResult("failure", 0.1, 503, "Unavailable"),
            ProbeResult("blocked", 0.0, reason="Target blocked"),
        ]
    )
    service = create(client, failure_threshold=1)
    url = f"/api/v1/services/{service['id']}"
    client.post(url + "/checks")
    client.post(url + "/checks")
    assert client.get(url).json()["status"] == "blocked"
    assert len(client.get("/api/v1/incidents?status=open").json()) == 1
    assert "monitor_service_up{" not in client.get("/metrics").text


def test_leases_and_revisions_prevent_duplicate_or_stale_results(client, app):
    service = create(client)
    repository = app.state.repository
    claimed = repository.claim(service["id"], force=True)
    with pytest.raises(ServiceConflict, match="already running"):
        repository.claim(service["id"], force=True)
    client.put(f"/api/v1/services/{service['id']}", json={**CONFIG, "enabled": False})
    with pytest.raises(ServiceConflict, match="Configuration changed"):
        repository.record(claimed, ProbeResult("failure", 0.1, 503, "Unavailable"))
    assert repository.checks(service["id"], 50, 0) == []


def test_target_edit_resolves_incident_as_configuration_change(client, app):
    app.state.monitor.checker = ScriptedChecker([ProbeResult("failure", 0.1, 503, "Unavailable")])
    service = create(client, failure_threshold=1)
    url = f"/api/v1/services/{service['id']}"
    client.post(url + "/checks")
    updated = client.put(url, json={**CONFIG, "url": "https://example.com/another"})
    assert updated.json()["status"] == "unknown"
    assert client.get("/api/v1/incidents").json()[0]["resolution"] == "configuration_changed"


def test_history_retention_and_inventory_limit(client, app):
    app.state.repository.service_limit = 1
    app.state.repository.history_limit = 2
    service = create(client)
    assert client.post("/api/v1/services", json=CONFIG).status_code == 409
    app.state.monitor.checker = ScriptedChecker([ProbeResult("success", 0.1, 200)] * 3)
    for _ in range(3):
        client.post(f"/api/v1/services/{service['id']}/checks")
    assert len(client.get(f"/api/v1/services/{service['id']}/checks").json()) == 2


def test_unknown_history_filters_and_pagination(client):
    assert client.get("/api/v1/services/missing/checks").status_code == 404
    assert client.get("/api/v1/incidents?service_id=missing").status_code == 404
    assert client.get("/api/v1/incidents?status=invalid").status_code == 422
    assert client.get("/api/v1/services?limit=1000").status_code == 422
    create(client)
    assert client.get("/api/v1/services?offset=1").json() == []


def test_storage_migration_preserves_existing_inventory(tmp_path):
    from system_monitoring.storage import SCHEMA, Database

    database = Database(tmp_path / "old.sqlite3")
    with database.connect() as connection:
        for statement in SCHEMA:
            connection.execute(statement)
        connection.execute("PRAGMA user_version=1")
        connection.execute(
            "INSERT INTO services (id, name, url) VALUES ('s', 'Old', 'https://example.com')"
        )
        connection.execute(
            "INSERT INTO incidents (id, service_id, reason) VALUES ('i', 's', 'Old outage')"
        )
    database.initialize()
    database.initialize()
    with database.connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT revision FROM services").fetchone()[0] == 1
        assert connection.execute("SELECT reason FROM incidents").fetchone()[0] == "Old outage"


def test_pausing_disallowed_target_does_not_require_reapproval(client, app):
    from system_monitoring.targets import TargetPolicy

    service = create(client)
    app.state.policy = TargetPolicy([], [])
    response = client.put(f"/api/v1/services/{service['id']}", json={**CONFIG, "enabled": False})
    assert response.status_code == 200
    assert response.json()["status"] == "paused"
    assert client.put(f"/api/v1/services/{service['id']}", json=CONFIG).status_code == 422


def test_renaming_keeps_failure_streak(client, app):
    app.state.monitor.checker = ScriptedChecker([ProbeResult("failure", 0.1, 503, "Unavailable")])
    service = create(client)
    url = f"/api/v1/services/{service['id']}"
    client.post(url + "/checks")
    response = client.put(url, json={**CONFIG, "name": "Renamed service"})
    assert response.json()["consecutive_failures"] == 1


def test_expired_lease_cannot_commit_over_a_newer_check(client, app):
    repository = app.state.repository
    service = create(client)
    first = repository.claim(service["id"], force=True)
    with app.state.database.connect() as connection:
        connection.execute("UPDATE services SET check_lease_until=0 WHERE id=?", (service["id"],))
    second = repository.claim(service["id"], force=True)
    with pytest.raises(ServiceConflict):
        repository.record(first, ProbeResult("failure", 0.1, 503, "Unavailable"))
    repository.record(second, ProbeResult("success", 0.1, 200))
    assert len(repository.checks(service["id"], 50, 0)) == 1


def test_removed_service_cannot_receive_an_inflight_result(client, app):
    from system_monitoring.repository import MissingService

    repository = app.state.repository
    service = create(client)
    claimed = repository.claim(service["id"], force=True)
    repository.delete(service["id"])
    with pytest.raises(MissingService):
        repository.record(claimed, ProbeResult("failure", 0.1, 503, "Unavailable"))


def test_concurrent_probes_respect_worker_limit(client, app):
    from system_monitoring.monitor import Monitor

    services = [create(client) for _ in range(3)]

    async def scenario():
        class BlockingChecker:
            def __init__(self):
                self.active = self.peak = 0
                self.two_started = asyncio.Event()
                self.release = asyncio.Event()

            async def probe(self, service):
                self.active += 1
                self.peak = max(self.peak, self.active)
                if self.active == 2:
                    self.two_started.set()
                await self.release.wait()
                self.active -= 1
                return ProbeResult("success", 0.1, 200)

        checker = BlockingChecker()
        monitor = Monitor(app.state.repository, checker, 2)
        tasks = [asyncio.create_task(monitor.check(service["id"])) for service in services]
        try:
            await asyncio.wait_for(checker.two_started.wait(), 2)
            assert checker.peak == 2
        finally:
            checker.release.set()
            results = await asyncio.gather(*tasks)
        assert checker.peak == 2
        assert len(results) == 3

    asyncio.run(scenario())
