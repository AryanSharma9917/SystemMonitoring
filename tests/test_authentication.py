import time

from fastapi.testclient import TestClient

from system_monitoring.auth import COOKIE
from system_monitoring.main import create_app

CREDENTIALS = {"username": "admin", "password": "test-operator-password"}


def test_inventory_dashboard_and_api_docs_require_sign_in(app):
    with TestClient(app) as anonymous:
        for path in [
            "/api/v1/services",
            "/api/v1/incidents",
            "/api/v1/dashboard",
            "/api/v1/notifications",
            "/docs",
            "/openapi.json",
        ]:
            assert anonymous.get(path).status_code == 401
        assert anonymous.get("/").status_code == 200
        assert anonymous.get("/assets/app.js").status_code == 200
        assert anonymous.get("/ready").status_code == 200


def test_sessions_are_http_only_revocable_and_passwords_are_hashed(app):
    with TestClient(app) as browser:
        response = browser.post("/api/auth/login", json=CREDENTIALS)
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert COOKIE not in response.json()
        token = browser.cookies[COOKIE]
        with app.state.database.connect() as connection:
            stored = connection.execute("SELECT password_hash FROM administrators").fetchone()[0]
            session = connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
        assert CREDENTIALS["password"] not in stored
        assert token != session
        assert browser.get("/api/auth/session").json()["username"] == "admin"
        assert browser.post("/api/auth/logout").status_code == 403
        csrf = response.json()["csrf_token"]
        assert browser.post("/api/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
        browser.cookies.set(COOKIE, token)
        assert browser.get("/api/v1/services").status_code == 401


def test_csrf_and_origin_validation_prevent_cross_site_changes(client):
    payload = {"name": "Example", "url": "https://example.com"}
    assert (
        client.post("/api/v1/services", json=payload, headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/services", json=payload, headers={"Origin": "https://other.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/auth/login", json=CREDENTIALS, headers={"Origin": "https://other.example"}
        ).status_code
        == 403
    )
    assert client.post("/api/v1/services", json=payload).status_code == 201


def test_expired_session_cannot_read_management_data(client, app):
    with app.state.database.connect() as connection:
        connection.execute("UPDATE sessions SET expires_at=?", (time.time() - 1,))
    assert client.get("/api/v1/services").status_code == 401
    assert client.get("/api/auth/session").status_code == 401


def test_failed_sign_in_attempts_are_persisted_and_rate_limited(app):
    with TestClient(app) as browser:
        for _ in range(5):
            response = browser.post(
                "/api/auth/login", json={**CREDENTIALS, "password": "incorrect"}
            )
            assert response.status_code == 401
            assert "incorrect" not in response.text
        assert browser.post("/api/auth/login", json=CREDENTIALS).status_code == 429
        with app.state.database.connect() as connection:
            connection.execute("UPDATE administrators SET locked_until=?", (time.time() - 1,))
        assert browser.post("/api/auth/login", json=CREDENTIALS).status_code == 200


def test_initial_password_does_not_overwrite_an_existing_account(settings):
    with TestClient(create_app(settings)) as first:
        assert first.post("/api/auth/login", json=CREDENTIALS).status_code == 200
    changed = settings.model_copy(update={"admin_password": None})
    with TestClient(create_app(changed)) as restarted:
        assert restarted.post("/api/auth/login", json=CREDENTIALS).status_code == 200


def test_secure_cookie_flag_and_public_interface_security_headers(settings):
    application = create_app(settings.model_copy(update={"secure_cookies": True}))
    with TestClient(application, base_url="https://testserver") as browser:
        login = browser.post("/api/auth/login", json=CREDENTIALS)
        assert "Secure" in login.headers["set-cookie"]
        response = browser.get("/")
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "no-store"
        assert browser.get("/api/v1/services").status_code == 200


def test_unconfigured_administrator_has_no_default_credentials(settings):
    with TestClient(create_app(settings.model_copy(update={"admin_password": None}))) as browser:
        assert browser.post("/api/auth/login", json=CREDENTIALS).status_code == 503
        assert browser.get("/api/v1/services").status_code == 401


def test_password_recovery_revokes_sessions_and_updates_the_account(
    client, app, settings, monkeypatch
):
    import sys

    from system_monitoring.admin import main

    monkeypatch.setenv("MONITOR_DATABASE_PATH", str(settings.database_path))
    monkeypatch.setattr(sys, "argv", ["admin", "--reset-password"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: "replacement-password-for-testing")
    main()
    assert client.get("/api/v1/services").status_code == 401
    assert client.post("/api/auth/login", json=CREDENTIALS).status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={**CREDENTIALS, "password": "replacement-password-for-testing"}
        ).status_code
        == 200
    )


def test_session_remains_valid_after_application_restart(settings):
    with TestClient(create_app(settings)) as first:
        assert first.post("/api/auth/login", json=CREDENTIALS).status_code == 200
        token = first.cookies[COOKIE]
    with TestClient(create_app(settings.model_copy(update={"admin_password": None}))) as restarted:
        restarted.cookies.set(COOKIE, token)
        assert restarted.get("/api/auth/session").json()["username"] == "admin"
        assert restarted.get("/api/v1/services").status_code == 200
