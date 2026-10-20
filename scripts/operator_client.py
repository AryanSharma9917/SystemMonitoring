"""Cookie-authenticated local API client shared by operational demonstrations."""

import contextlib
import http.cookiejar
import json
import os
import urllib.error
import urllib.request


class OperatorClient:
    def __init__(self, origin):
        self.origin = origin.rstrip("/")
        self.csrf = None
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        password = os.environ.get("MONITOR_ADMIN_PASSWORD")
        if not password:
            raise SystemExit("Set MONITOR_ADMIN_PASSWORD securely in the process environment")
        session = self.request(
            "/api/auth/login",
            {
                "username": os.environ.get("MONITOR_ADMIN_USERNAME", "admin"),
                "password": password,
            },
        )
        self.csrf = session["csrf_token"]

    def request(self, path, payload=None, method=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Only paths on the configured API origin are accepted")
        headers = {"X-CSRF-Token": self.csrf} if self.csrf else {}
        body = None if payload is None else json.dumps(payload).encode()
        if body:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.origin + path, data=body, method=method, headers=headers)
        with self.opener.open(req, timeout=40) as response:
            data = response.read()
            return json.loads(data) if data else None

    def close(self):
        with contextlib.suppress(OSError):
            self.request("/api/auth/logout", method="POST")
