#!/usr/bin/env python3
"""Exercise scheduled checks against the isolated demonstration target."""

import argparse
import contextlib
import json
import time
import urllib.error
import urllib.request

from operator_client import OperatorClient


def request(url, payload=None, method=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        data = response.read()
        return json.loads(data) if data else None


def wait_for(predicate, description, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            print(description, flush=True)
            return result
        time.sleep(1)
    raise RuntimeError(f"Timed out: {description}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--demo-url", default="http://127.0.0.1:8081")
    parser.add_argument("--target-url", default="http://demo-service:8080/health")
    parser.add_argument(
        "--cleanup", action="store_true", help="Remove this run's service and history"
    )
    args = parser.parse_args()
    api, demo = args.api_url.rstrip("/"), args.demo_url.rstrip("/")
    service = None
    administrator = OperatorClient(api)
    try:
        request(demo + "/mode", {"mode": "healthy"})
        service = administrator.request(
            "/api/v1/services",
            {
                "name": "Outage demonstration",
                "url": args.target_url,
                "check_interval_seconds": 10,
                "timeout_seconds": 2,
                "failure_threshold": 2,
            },
        )
        service_url = "/api/v1/services/" + service["id"]
        print("Registered demonstration service: " + service["id"], flush=True)
        wait_for(
            lambda: administrator.request(service_url)["status"] == "healthy",
            "Scheduled check is healthy",
        )
        request(demo + "/mode", {"mode": "failing"})
        wait_for(
            lambda: administrator.request(service_url)["status"] == "down",
            "Sustained failure opened an incident",
        )
        incidents_url = "/api/v1/incidents?service_id=" + service["id"]
        incidents = administrator.request(incidents_url)
        assert len(incidents) == 1 and incidents[0]["resolved_at"] is None
        request(demo + "/mode", {"mode": "healthy"})
        wait_for(
            lambda: administrator.request(service_url)["status"] == "healthy",
            "Recovery check restored healthy status",
        )
        incidents = administrator.request(incidents_url)
        assert len(incidents) == 1 and incidents[0]["resolution"] == "recovered"
        checks = administrator.request(service_url + "/checks")
        assert {check["outcome"] for check in checks} == {"success", "failure"}
        print(
            "Verified automatic outage detection, one incident, history, and recovery.", flush=True
        )
    finally:
        with contextlib.suppress(OSError):
            request(demo + "/mode", {"mode": "healthy"})
        if service and args.cleanup:
            administrator.request("/api/v1/services/" + service["id"], method="DELETE")

        administrator.close()


if __name__ == "__main__":
    main()
