import sqlite3
from uuid import UUID

from fastapi import HTTPException
from prometheus_client.parser import text_string_to_metric_families
from pydantic import BaseModel


def test_root_describes_application(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "System Monitoring"
    assert response.json()["docs"] == "/docs"


def test_liveness_and_readiness(client):
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_storage_failure_does_not_claim_readiness(client, app, monkeypatch):
    def unavailable():
        raise sqlite3.OperationalError("private storage failure details")

    monkeypatch.setattr(app.state.database, "check", unavailable)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "not_ready"
    assert "private storage" not in response.text
    assert client.get("/health").status_code == 200


def test_missing_database_is_not_silently_recreated(client, settings):
    settings.database_path.unlink()
    assert client.get("/ready").status_code == 503
    assert not settings.database_path.exists()


def test_request_ids_are_generated_and_returned(client):
    first = client.get("/health", headers={"X-Request-ID": "untrusted"})
    second = client.get("/health")
    UUID(first.headers["X-Request-ID"])
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_not_found_and_wrong_method_have_consistent_errors(client):
    for response, code in [
        (client.get("/missing"), "not_found"),
        (client.post("/health"), "method_not_allowed"),
    ]:
        assert response.json()["error"]["code"] == code
        assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert client.post("/health").headers["allow"] == "GET"


def test_validation_errors_do_not_echo_request_values(app, client):
    class Payload(BaseModel):
        count: int

    @app.post("/validation-example")
    def validate(payload: Payload):
        return payload

    response = client.post("/validation-example", json={"count": "private-value"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert response.json()["error"]["details"][0]["location"] == ["body", "count"]
    assert "private-value" not in response.text


def test_internal_errors_are_sanitized(app, client):
    @app.get("/failure-example")
    def fail():
        raise RuntimeError("implementation detail")

    response = client.get("/failure-example")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "implementation detail" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_http_error_headers_are_preserved(app, client):
    @app.get("/protected-example")
    def protected():
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})

    response = client.get("/protected-example")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_metrics_record_real_requests(client):
    client.get("/health")
    client.get("/health")
    response = client.get("/metrics")
    assert response.status_code == 200
    samples = [
        sample
        for family in text_string_to_metric_families(response.text)
        for sample in family.samples
    ]
    assert any(
        sample.name == "http_requests_total"
        and sample.labels.get("handler") == "/health"
        and sample.value >= 2
        for sample in samples
    )
    assert any(sample.name == "process_resident_memory_bytes" for sample in samples)


def test_openapi_documents_readiness(client):
    schema = client.get("/openapi.json").json()
    assert "/ready" in schema["paths"]
    assert "/metrics" not in schema["paths"]


def test_unknown_paths_share_one_metrics_label(client):
    client.get("/missing-one")
    client.get("/missing-two")
    metrics = client.get("/metrics").text
    assert "missing-one" not in metrics
    assert "missing-two" not in metrics
    assert 'handler="unmatched"' in metrics


def test_failed_request_is_counted_in_metrics(app, client):
    @app.get("/broken-for-metrics")
    def fail():
        raise RuntimeError("failure")

    assert client.get("/broken-for-metrics").status_code == 500
    metrics = client.get("/metrics").text
    assert 'handler="/broken-for-metrics",method="GET",status="5xx"} 1.0' in metrics
