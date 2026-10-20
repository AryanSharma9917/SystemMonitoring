# Controlled outage demonstration

The optional sample service runs as a separate container. Its control API is bound
to the local machine and is not part of the monitoring application's API. Include
`compose.demo.yml` only for a dedicated demonstration installation; it replaces the
monitor's approved-origin lists with the sample origin.

## Start and verify

```bash
cp .env.example .env
# Set GRAFANA_ADMIN_PASSWORD in .env if you have not already configured it.
docker compose -f docker-compose.yml -f compose.demo.yml up --build -d
# Set MONITOR_ADMIN_PASSWORD securely in the process environment for sign-in.
python3 scripts/demonstrate-outage.py
```

On a new installation, create an administrator first using
`docker compose exec fastapi python -m system_monitoring.admin`. If you started only
the combined demonstration files, include those same `-f` arguments with `exec`.
The workspace is available at the application root after signing in.

The script signs in using MONITOR_ADMIN_USERNAME (default admin) and
MONITOR_ADMIN_PASSWORD from its process environment, then registers a new service,
waits for a scheduled success, changes the sample to return 503, waits for two
consecutive failures and exactly one open incident,
restores HTTP 200, then verifies the same incident is recovered. It does not bypass
the scheduler with manual checks. It normally takes roughly 30–45 seconds, with
bounded waits that fail if monitoring is broken. Every invocation creates a distinct
service; use `--cleanup` when you do not need to keep the demonstration history.

The sample has a separate `/live` container health endpoint that stays available
during simulated failures; Compose startup checks that endpoint.

Application management routes require a session, but the isolated sample control
API deliberately remains unauthenticated and must stay local.

The sample always resets to healthy on process restart. Normal targets, observations
and incidents remain in the monitoring application's persistent volume.

## Manual controls

```bash
curl --fail http://localhost:8081/mode \
  -H 'Content-Type: application/json' -d '{"mode":"failing"}'
curl --fail http://localhost:8081/mode \
  -H 'Content-Type: application/json' -d '{"mode":"healthy"}'
curl --fail http://localhost:8081/mode \
  -H 'Content-Type: application/json' -d '{"mode":"slow"}'
```

Slow mode waits five seconds before responding; the demonstration service's probe
timeout is two seconds, so it records a timeout. Keep failure modes active long
enough for the configured interval and threshold. The sample is not a resource
exhaustion tool and exposes no command execution or arbitrary target selection.

For local Python instead of Docker, run `uv run uvicorn system_monitoring.demo:app
--port 8081`, approve `http://127.0.0.1:8081` in both origin lists, and pass
`--target-url http://127.0.0.1:8081/health` to the demonstration script. The default
Docker hostname is not reachable from a host Python process.

## Verify the dashboard

Open Grafana's **Service Monitoring** dashboard. Inspect probe results, incident
count, failure streak and response time. Unknown/paused/blocked observations remain
missing rather than being shown as successful checks. Allow at least two Prometheus
scrapes for rate panels to populate. With a completed demonstration still registered,
run the stack checker using your existing shell environment:

```bash
# Supply your configured Grafana credentials securely in the process environment.
python3 scripts/check-stack.py
```

The checker reads `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD` from environment
variables, without logging their values. It verifies both scrape targets, dashboard
provisioning and every panel query through Grafana. It expects actual service
observations; run the demonstration before it. Empty-service dashboards correctly
show missing data rather than invented healthy values. Custom local ports can be
passed using each script's `--help` options.

## Record the interface walkthrough

The browser checker uses temporary local targets and a webhook receiver. Its normal run
verifies desktop and mobile layouts. Add `--record` when you want a WebM walkthrough of
sign-in, service creation, a manual outage and recovery, retry delivery, editing and
logout:

```bash
uv run --locked python scripts/check-browser.py --record --artifacts browser-artifacts
```

The recording uses manual checks to keep the interface tour short. The outage script
above separately verifies the real scheduler and failure threshold. Product media in
`website/assets/` was generated through this browser workflow against sample data.

## Stop or return to the normal stack

```bash
docker compose -f docker-compose.yml -f compose.demo.yml down
docker compose up -d
```

Volumes and the demonstration service's history are retained. Pause or delete the
registered sample when returning to your ordinary approved origins. Do not use
`down -v` unless you intend to delete all stack data. The demonstration control API
has no authentication and must never be published publicly.
