#!/usr/bin/env python3
"""Check the static project website links, content and responsive browser layout."""

import argparse
import os
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def local_links_exist(root: Path) -> None:
    from html.parser import HTMLParser

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = []

        def handle_starttag(self, tag, attributes):
            values = dict(attributes)
            for name in ("href", "src"):
                if values.get(name):
                    self.links.append(values[name])

    for page in root.glob("*.html"):
        parser = Links()
        parser.feed(page.read_text())
        for raw_link in parser.links:
            link = urlsplit(raw_link)
            if link.scheme or link.netloc or raw_link.startswith(("#", "mailto:")):
                continue
            destination = root / link.path if link.path else page
            if not destination.exists():
                raise AssertionError(f"{page.name} links to missing {link.path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=Path("website"))
    parser.add_argument("--artifacts", type=Path, default=Path("/tmp/system-monitoring-site"))
    args = parser.parse_args()
    site, artifacts = args.site.resolve(), args.artifacts.resolve()
    local_links_exist(site)
    artifacts.mkdir(parents=True, exist_ok=True)

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    class Server(ThreadingHTTPServer):
        allow_reuse_address = True

    handler = lambda *handler_args, **kwargs: QuietHandler(  # noqa: E731
        *handler_args, directory=str(site), **kwargs
    )
    server = Server(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as playwright:
            executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or shutil.which(
                "chromium"
            )
            browser = playwright.chromium.launch(executable_path=executable, args=["--no-sandbox"])
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(origin)
            expect(
                page.get_by_role("heading", name="Follow every failure through recovery.")
            ).to_be_visible()
            screenshot_description = (
                "Administrator workspace showing three monitored services, "
                "observed success, response times and recent incidents"
            )
            expect(page.get_by_alt_text(screenshot_description)).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth+1")
            page.screenshot(path=str(artifacts / "website-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth+1")
            expect(page.get_by_role("link", name="Start monitoring")).to_be_visible()
            page.screenshot(path=str(artifacts / "website-mobile.png"), full_page=True)
            page.goto(origin + "/guide.html")
            expect(page.get_by_role("heading", name="A workspace you can run.")).to_be_visible()
            expect(
                page.get_by_role("heading", name="Prepare an HTTPS installation")
            ).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth+1")
            assert not errors, errors
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    print("Website verified: links, desktop and mobile layout, guide content and assets.")


if __name__ == "__main__":
    main()
