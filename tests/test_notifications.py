import asyncio
import json

import pytest
from pydantic import SecretStr

from system_monitoring.models import ProbeResult
from system_monitoring.notifications import WebhookDelivery, WebhookPolicy
from system_monitoring.targets import TargetBlocked

CONFIG = {"name": "Example API", "url": "https://example.com/health", "failure_threshold": 1}


def make_outage(client, app):
    app.state.repository.notifications_enabled = True
    service = client.post("/api/v1/services", json=CONFIG).json()
    repository = app.state.repository
    for _ in range(2):
        claim = repository.claim(service["id"], force=True)
        repository.record(claim, ProbeResult("failure", 0.1, 503, "Unavailable"))
    return service


def test_repeated_failures_queue_one_event_and_recovery_is_separate(client, app):
    service = make_outage(client, app)
    repository = app.state.repository
    repository.record(repository.claim(service["id"], force=True), ProbeResult("success", 0.1, 200))
    events = client.get("/api/v1/notifications").json()["deliveries"]
    assert len(events) == 2
    assert {row["event_type"] for row in events} == {"incident.opened", "incident.recovered"}
    assert len({row["event_id"] for row in events}) == 2
    assert all(row["status"] == "pending" for row in events)
    with app.state.database.connect() as connection:
        payload = json.loads(connection.execute("SELECT payload FROM notifications").fetchone()[0])
    assert payload["service"]["name"] == "Example API"
    assert "url" not in payload["service"]


@pytest.mark.parametrize(
    "http_status,expected",
    [(204, "delivered"), (503, "pending"), (429, "pending"), (400, "failed"), (302, "failed")],
)
def test_real_webhook_delivery_and_retry_classification(
    client, app, settings, webhook_server, http_status, expected
):
    make_outage(client, app)
    webhook_server.status = http_status
    configured = settings.model_copy(
        update={"webhook_url": SecretStr(webhook_server.url), "webhook_allow_private": True}
    )
    worker = WebhookDelivery(app.state.database, configured)
    event = worker.claim()
    status, error = asyncio.run(worker.send(event))
    assert status == expected
    worker.complete(event, status, error)
    payload, key = webhook_server.events[0]
    assert payload["event_id"] == event["event_id"] == key
    assert "url" not in payload["service"]
    events = client.get("/api/v1/notifications").json()["deliveries"]
    assert events[0]["status"] == expected
    assert "payload" not in events[0]


def test_retry_keeps_event_id_and_preserves_incident_order(client, app, settings, webhook_server):
    service = make_outage(client, app)
    repository = app.state.repository
    repository.record(repository.claim(service["id"], force=True), ProbeResult("success", 0.1, 200))
    worker = WebhookDelivery(
        app.state.database,
        settings.model_copy(
            update={"webhook_url": SecretStr(webhook_server.url), "webhook_allow_private": True}
        ),
    )
    first = worker.claim()
    worker.complete(first, "pending", "Temporary failure")
    assert worker.claim() is None
    with app.state.database.connect() as connection:
        connection.execute("UPDATE notifications SET next_attempt_at=0")
    repeated = worker.claim()
    assert repeated["event_id"] == first["event_id"]
    status, error = asyncio.run(worker.send(repeated))
    worker.complete(repeated, status, error)
    next_event = worker.claim()
    assert next_event["event_type"] == "incident.recovered"
    assert next_event["event_id"] != first["event_id"]


def test_retry_limit_is_terminal_and_service_removal_cancels_pending(client, app, settings):
    service = make_outage(client, app)
    worker = WebhookDelivery(app.state.database, settings)
    event = worker.claim()
    event["attempts"] = 7
    assert asyncio.run(worker.send(event))[0] == "failed"
    client.delete(f"/api/v1/services/{service['id']}")
    worker.complete(event, "delivered")
    assert client.get("/api/v1/notifications").json()["deliveries"][0]["status"] == "cancelled"


def test_plain_http_webhook_cannot_reach_public_or_metadata_addresses():
    policy = WebhookPolicy(["http://receiver"], ["http://receiver"])
    policy.validate_address("127.0.0.1", "http://receiver")
    for ip in ["93.184.216.34", "169.254.169.254"]:
        with pytest.raises(TargetBlocked):
            policy.validate_address(ip, "http://receiver")


def test_incident_and_notification_are_rolled_back_together(client, app, monkeypatch):
    import system_monitoring.repository as module

    service = client.post("/api/v1/services", json=CONFIG).json()
    app.state.repository.notifications_enabled = True

    def cannot_enqueue(*args):
        raise RuntimeError("Storage failure")

    monkeypatch.setattr(module, "enqueue", cannot_enqueue)
    claimed = app.state.repository.claim(service["id"], force=True)
    with pytest.raises(RuntimeError):
        app.state.repository.record(claimed, ProbeResult("failure", 0.1, 503, "Unavailable"))
    assert client.get("/api/v1/incidents").json() == []
    assert client.get("/api/v1/notifications").json()["deliveries"] == []


def test_operator_can_retry_failed_delivery_without_changing_event_id(
    client, app, settings, webhook_server
):
    make_outage(client, app)
    app.state.settings.webhook_url = SecretStr(webhook_server.url)
    with app.state.database.connect() as connection:
        connection.execute("UPDATE notifications SET status='failed', attempts=6")
    event = client.get("/api/v1/notifications").json()["deliveries"][0]
    endpoint = f"/api/v1/notifications/{event['event_id']}/retry"
    assert client.post(endpoint, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert client.post(endpoint).status_code == 202
    queued = client.get("/api/v1/notifications").json()["deliveries"][0]
    assert queued["event_id"] == event["event_id"]
    assert queued["status"] == "pending" and queued["attempts"] == 0
    assert client.post(endpoint).status_code == 409
    assert webhook_server.url not in client.get("/api/v1/notifications").text


def test_expired_delivery_claim_is_resumed_without_accepting_stale_acknowledgment(
    client, app, settings
):
    make_outage(client, app)
    first_worker = WebhookDelivery(app.state.database, settings)
    first = first_worker.claim()
    with app.state.database.connect() as connection:
        connection.execute("UPDATE notifications SET lease_until=0")
    resumed_worker = WebhookDelivery(app.state.database, settings)
    resumed = resumed_worker.claim()
    assert resumed["event_id"] == first["event_id"]
    assert resumed["attempts"] == 2
    first_worker.complete(first, "delivered")
    assert client.get("/api/v1/notifications").json()["deliveries"][0]["status"] == "pending"
    resumed_worker.complete(resumed, "delivered")
    assert client.get("/api/v1/notifications").json()["deliveries"][0]["status"] == "delivered"
