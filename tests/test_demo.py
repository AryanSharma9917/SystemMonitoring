from fastapi.testclient import TestClient

from system_monitoring.demo import app as demo_app


def test_demo_liveness_stays_available_during_simulated_failure():
    with TestClient(demo_app) as client:
        try:
            assert client.post("/mode", json={"mode": "failing"}).status_code == 200
            assert client.get("/health").status_code == 503
            assert client.get("/live").json() == {"status": "ok"}
            assert client.post("/mode", json={"mode": "invalid"}).status_code == 422
        finally:
            client.post("/mode", json={"mode": "healthy"})
        assert client.get("/health").status_code == 200


def test_demo_controls_are_not_part_of_monitoring_application(client):
    assert client.get("/mode").status_code == 404
    assert client.post("/mode", json={"mode": "failing"}).status_code == 404
