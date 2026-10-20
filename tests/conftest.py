import pytest
from fastapi.testclient import TestClient

from system_monitoring.config import Settings
from system_monitoring.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_path=tmp_path / "monitoring.sqlite3",
        _env_file=None,
        scheduler_enabled=False,
        admin_password="test-operator-password",
        approved_origins=["https://example.com"],
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        sign_in(client)
        yield client


@pytest.fixture
def target_server():
    """An actual HTTP endpoint for probe and scheduler integration checks."""
    import contextlib
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.paths.append(self.path)
            if self.path == "/slow":
                time.sleep(1.5)
            self.send_response(302 if self.path == "/redirect" else self.server.status)
            if self.path == "/redirect":
                self.send_header("Location", "/must-not-follow")
            if self.path == "/stream":
                self.send_header("Content-Length", "10000000")
            self.end_headers()
            if self.path == "/stream":
                time.sleep(1.5)
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                self.wfile.write(b"probe response")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.status = 200
    server.paths = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server.url = f"http://127.0.0.1:{server.server_port}"
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def sign_in(client, password="test-operator-password"):
    response = client.post("/api/auth/login", json={"username": "admin", "password": password})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


@pytest.fixture
def webhook_server():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            self.server.events.append(
                (
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                    self.headers.get("Idempotency-Key"),
                )
            )
            self.send_response(self.server.status)
            if self.server.status == 302:
                self.send_header("Location", "http://169.254.169.254/")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    server.status = 204
    server.events = []
    server.url = f"http://127.0.0.1:{server.server_port}/events"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
