#!/usr/bin/env python3
"""Exercise the real interface, authentication and webhook recovery in Chromium."""

import argparse
import contextlib
import json
import os
import secrets
import shutil
import socket
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

from system_monitoring.config import Settings
from system_monitoring.main import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", default="/tmp/system-monitoring-browser")
    parser.add_argument("--record", action="store_true", help="Save a WebM workflow recording")
    args = parser.parse_args()
    artifacts = Path(args.artifacts)
    artifacts.mkdir(parents=True, exist_ok=True)

    class Target(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(self.server.status if self.path == "/payments" else 200)
            self.end_headers()
            self.wfile.write(b"healthy response")

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.events.append((payload, self.headers.get("Idempotency-Key")))
            self.send_response(503 if len(self.server.events) == 1 else 204)
            self.end_headers()

        def log_message(self, *args):
            pass

    target = ThreadingHTTPServer(("127.0.0.1", 0), Target)
    target.status, target.events = 200, []
    thread = threading.Thread(target=target.serve_forever, daemon=True)
    thread.start()
    target_origin = f"http://127.0.0.1:{target.server_port}"
    password = secrets.token_urlsafe(24)
    with tempfile.TemporaryDirectory(prefix="monitoring-browser-") as directory:
        application = create_app(
            Settings(
                _env_file=None,
                database_path=Path(directory) / "monitoring.sqlite3",
                admin_password=password,
                approved_origins=[target_origin],
                private_origins=[target_origin],
                webhook_url=target_origin + "/events",
                webhook_allow_private=True,
                log_level="WARNING",
            )
        )
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        api_origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(application, log_level="warning", access_log=False))
        api_thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        api_thread.start()
        deadline = time.monotonic() + 10
        while not server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("Browser check application did not start")
            time.sleep(0.05)
        try:
            with sync_playwright() as playwright:
                executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which(
                    "chromium"
                )
                browser = playwright.chromium.launch(
                    executable_path=executable, args=["--no-sandbox"]
                )
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1080},
                    color_scheme="light",
                    record_video_dir=str(artifacts) if args.record else None,
                    record_video_size={"width": 1440, "height": 1080},
                )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(api_origin)
                expect(
                    page.get_by_role("heading", name="Sign in to your workspace")
                ).to_be_visible()
                expect(page.locator("html")).to_have_attribute("data-theme", "light")
                assert page.request.get(api_origin + "/api/v1/services").status == 401
                page.screenshot(path=str(artifacts / "sign-in.png"), full_page=True)
                page.get_by_role("button", name="Use dark mode").click()
                expect(page.locator("html")).to_have_attribute("data-theme", "dark")
                page.screenshot(path=str(artifacts / "sign-in-dark.png"), full_page=True)
                page.get_by_label("Username", exact=True).fill("admin")
                page.get_by_label("Password", exact=True).fill(password)
                page.get_by_role("button", name="Sign in", exact=False).click()
                expect(page.get_by_role("heading", name="Service overview")).to_be_visible()
                expect(page.locator("html")).to_have_attribute("data-theme", "dark")
                page.get_by_role("button", name="+ Add service", exact=True).click()
                page.get_by_label("Service name", exact=True).fill("Payments API")
                page.get_by_label("Health check URL", exact=True).fill(target_origin + "/payments")
                page.get_by_label("Check every (seconds)", exact=True).fill("10")
                page.get_by_label("Timeout (seconds)", exact=True).fill("1")
                page.get_by_label("Failures before an incident", exact=True).fill("1")
                page.get_by_role("button", name="Add service", exact=True).click()
                expect(page.get_by_role("button", name="Payments API", exact=True)).to_be_visible()
                csrf = page.request.get(api_origin + "/api/auth/session").json()["csrf_token"]
                for name, path in [("Status website", "/status"), ("Worker API", "/worker")]:
                    result = page.request.post(
                        api_origin + "/api/v1/services",
                        data={
                            "name": name,
                            "url": target_origin + path,
                            "check_interval_seconds": 10,
                            "timeout_seconds": 1,
                            "failure_threshold": 1,
                        },
                        headers={"X-CSRF-Token": csrf},
                    )
                    assert result.status == 201
                page.get_by_role("button", name="Payments API", exact=True).click()
                expect(page.get_by_role("button", name="Check now", exact=True)).to_be_visible()
                page.get_by_role("button", name="Check now", exact=True).click()
                expect(page.locator("#view .badge.healthy").first).to_be_visible(timeout=10000)
                target.status = 503
                page.get_by_role("button", name="Check now", exact=True).click()
                expect(page.locator("#view .badge.down").first).to_be_visible(timeout=10000)
                page.locator('.sidebar [data-nav="incidents"]').click()
                expect(page.get_by_text("Unexpected HTTP status 503", exact=True)).to_be_visible()
                page.get_by_role("button", name="Payments API", exact=True).click()
                target.status = 200
                page.get_by_role("button", name="Check now", exact=True).click()
                expect(page.locator("#view .badge.healthy").first).to_be_visible(timeout=10000)
                expect(page.locator("svg.chart")).to_be_visible()
                page.screenshot(path=str(artifacts / "service-details.png"), full_page=True)
                page.get_by_role("button", name="Pause monitoring", exact=True).click()
                expect(page.locator("#view .badge.paused").first).to_be_visible()
                expect(page.get_by_role("button", name="Check now", exact=True)).to_be_disabled()
                page.get_by_role("button", name="Resume monitoring", exact=True).click()
                expect(
                    page.get_by_role("button", name="Pause monitoring", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Edit service", exact=True).click()
                page.get_by_label("Service name", exact=True).fill("Payments API · Primary")
                page.get_by_role("button", name="Save changes", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Payments API · Primary", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Edit service", exact=True).click()
                page.get_by_label("Service name", exact=True).fill("Payments API")
                page.get_by_role("button", name="Save changes", exact=True).click()
                page.locator('.sidebar [data-nav="notifications"]').click()
                expect(page.locator("#view .badge.delivered")).to_have_count(2, timeout=20000)
                assert len(target.events) == 3
                assert target.events[0][0]["event_id"] == target.events[1][0]["event_id"]
                assert len({event[0]["event_id"] for event in target.events}) == 2
                assert all(event[0]["event_id"] == event[1] for event in target.events)
                page.locator('.sidebar [data-nav="overview"]').click()
                expect(page.get_by_role("button", name="Payments API", exact=True)).to_be_visible()
                hostile_name = '<img src=x onerror="window.__unsafe=1">'
                injected = page.request.post(
                    api_origin + "/api/v1/services",
                    data={
                        "name": hostile_name,
                        "url": target_origin + "/safe",
                        "enabled": False,
                    },
                    headers={"X-CSRF-Token": csrf},
                )
                assert injected.status == 201
                page.get_by_role("button", name="Refresh workspace", exact=True).click()
                expect(page.get_by_role("button", name=hostile_name, exact=True)).to_be_visible()
                assert page.evaluate("window.__unsafe") is None
                assert (
                    page.request.delete(
                        api_origin + "/api/v1/services/" + injected.json()["id"],
                        headers={"X-CSRF-Token": csrf},
                    ).status
                    == 204
                )
                page.get_by_role("button", name="Refresh workspace", exact=True).click()
                expect(page.get_by_role("button", name=hostile_name, exact=True)).to_have_count(0)
                page.mouse.move(800, 80)
                page.screenshot(path=str(artifacts / "workspace-desktop.png"), full_page=True)
                page.reload()
                expect(page.get_by_role("heading", name="Service overview")).to_be_visible()
                expect(page.locator("html")).to_have_attribute("data-theme", "dark")
                if not args.record:
                    page.set_viewport_size({"width": 390, "height": 844})
                    layout = page.evaluate(
                        """() => ({
                          viewport: window.innerWidth,
                          page: document.documentElement.scrollWidth,
                          overflowing: [...document.querySelectorAll('body *')]
                            .filter((element) => {
                              const box = element.getBoundingClientRect();
                              return box.right > window.innerWidth + 1 || box.left < -1;
                            })
                            .slice(0, 10)
                            .map((element) => ({
                              tag: element.tagName,
                              className: element.className,
                              id: element.id,
                              left: element.getBoundingClientRect().left,
                              right: element.getBoundingClientRect().right,
                            })),
                        })"""
                    )
                    assert layout["page"] <= layout["viewport"] + 1, layout
                    page.screenshot(path=str(artifacts / "workspace-mobile.png"), full_page=True)
                page.get_by_role("button", name="Sign out", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Sign in to your workspace")
                ).to_be_visible()
                assert page.request.get(api_origin + "/api/v1/services").status == 401
                assert not errors, errors
                video = page.video
                context.close()
                if video:
                    video.save_as(str(artifacts / "walkthrough.webm"))
                    video.delete()
                browser.close()
            coverage = (
                "sign-in, service creation, outage/recovery, retries, charts, "
                "pause/resume, dark-mode persistence, restored sessions and logout"
            )
            if not args.record:
                coverage += ", including the mobile layout"
            print(f"Browser verified: {coverage}.")
            print(f"Screenshots saved in {artifacts}")
        finally:
            server.should_exit = True
            api_thread.join(timeout=15)
            with contextlib.suppress(OSError):
                sock.close()
            target.shutdown()
            target.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
