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
        approved_origins=["https://example.com"],
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
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
