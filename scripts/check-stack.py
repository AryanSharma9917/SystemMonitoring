#!/usr/bin/env python3
"""Validate scrapes, provisioned dashboards and each dashboard query through Grafana."""

import argparse
import base64
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:9090")
    parser.add_argument("--grafana-url", default="http://127.0.0.1:3000")
    args = parser.parse_args()
    user = os.environ.get("GRAFANA_ADMIN_USER", "admin")
    password = os.environ["GRAFANA_ADMIN_PASSWORD"]
    token = base64.b64encode(f"{user}:{password}".encode()).decode()

    def get(url, auth=False):
        req = urllib.request.Request(
            url, headers={"Authorization": f"Basic {token}"} if auth else {}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    deadline = time.monotonic() + 50
    while True:
        targets = get(args.prometheus_url + "/api/v1/targets")["data"]["activeTargets"]
        if len(targets) == 2 and all(target["health"] == "up" for target in targets):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Both scrape targets did not become healthy")
        time.sleep(1)
    dashboards = get(args.grafana_url + "/api/search?type=dash-db", True)
    assert any(dashboard["uid"] == "system-monitoring" for dashboard in dashboards)
    path = Path(__file__).resolve().parents[1] / "provisioning/dashboards/dashboard.json"
    dashboard = json.loads(path.read_text())
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            query = urllib.parse.urlencode({"query": target["expr"]})
            result = get(
                args.grafana_url + "/api/datasources/proxy/uid/prometheus/api/v1/query?" + query,
                True,
            )
            assert result["status"] == "success", panel["title"]
            assert result["data"]["result"], f"No observations for {panel['title']}"
    print(f"Verified scrape targets, dashboard and {len(dashboard['panels'])} queries.")


if __name__ == "__main__":
    main()
