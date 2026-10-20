from system_monitoring.models import ProbeResult

CONFIG = {"name": "Example API", "url": "https://example.com/health", "failure_threshold": 1}


def observe(repository, service_id, outcome):
    claimed = repository.claim(service_id, force=True)
    return repository.record(
        claimed,
        ProbeResult(
            outcome,
            0.1,
            200 if outcome == "success" else None,
            None if outcome == "success" else "Unavailable",
        ),
    )


def test_observed_success_excludes_blocked_and_unknown_time(client, app):
    service = client.post("/api/v1/services", json=CONFIG).json()
    path = f"/api/v1/services/{service['id']}/availability"
    assert client.get(path).json()["success_percentage"] is None
    for outcome in ["success", "failure", "blocked"]:
        observe(app.state.repository, service["id"], outcome)
    result = client.get(path).json()
    assert result["success_percentage"] == 50
    assert result["successes"] == result["failures"] == result["blocked"] == 1
    assert result["observations"] == 3
    assert result["first_observation_at"] is not None


def test_window_and_retention_limits_are_visible(client, app):
    service = client.post("/api/v1/services", json=CONFIG).json()
    repository = app.state.repository
    repository.history_limit = 2
    for _ in range(3):
        observe(repository, service["id"], "success")
    summary = client.get(f"/api/v1/services/{service['id']}/availability").json()
    assert summary["history_may_be_truncated"]
    assert summary["observations"] == 2
    with app.state.database.connect() as connection:
        connection.execute("UPDATE checks SET checked_at='2000-01-01T00:00:00.000Z'")
    assert (
        client.get(f"/api/v1/services/{service['id']}/availability?window_hours=1").json()[
            "success_percentage"
        ]
        is None
    )
    assert client.get("/api/v1/dashboard?window_hours=999").status_code == 422


def test_target_changes_start_a_new_availability_window(client, app):
    service = client.post("/api/v1/services", json=CONFIG).json()
    observe(app.state.repository, service["id"], "success")
    path = f"/api/v1/services/{service['id']}"
    client.put(path, json={**CONFIG, "url": "https://example.com/changed"})
    result = client.get(path + "/availability").json()
    assert result["success_percentage"] is None
    assert result["observations"] == 0
