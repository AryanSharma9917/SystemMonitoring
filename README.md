# System Monitoring

A monitoring workspace for registering HTTP services, understanding failures, and
following recovery. FastAPI and SQLite power the application; Prometheus and Grafana
provide operational metrics. The responsive administrator interface is served by
the application itself, with no separate frontend build or external runtime assets.

**Implemented:** administrator sign-in, service management, scheduled checks, incident
history, observed availability, response-time charts, and durable webhook delivery.
The companion website and deployment polish are next, followed by a project release.

## Start your workspace

Requires Docker Engine and Docker Compose v2. From the repository root:

```bash
cp .env.example .env
# Set GRAFANA_ADMIN_PASSWORD and approve your monitoring origins in .env.
docker compose up --build -d
docker compose exec fastapi python -m system_monitoring.admin
```

The administrator command prompts for a password (12–1024 characters). It stores a
salted password hash in the application volume, never the plaintext password. Open
`http://localhost:8000` and sign in. There is no default password or public account
registration. To recover access, use the same command with `--reset-password`;
that revokes all existing sessions.

For automated initial setup, `MONITOR_ADMIN_PASSWORD` can bootstrap the first account
at startup. It never overwrites an existing account. Remove the bootstrap value from
your environment after provisioning. The interactive command is preferable for local
setup because it does not leave the password in shell history or configuration.

| Component | Local address | Access |
| --- | --- | --- |
| Workspace | `http://localhost:8000` | Administrator sign-in |
| API explorer | `http://localhost:8000/docs` | Signed-in administrator |
| Liveness | `http://localhost:8000/health` | Local operational endpoint |
| Readiness | `http://localhost:8000/ready` | Database and enabled workers |
| Metrics | `http://localhost:8000/metrics` | Local Prometheus endpoint |
| Prometheus | `http://localhost:9090` | Local operational interface |
| Grafana | `http://localhost:3000` | Separate Grafana credentials |

Published Compose ports bind to the local machine. The API container runs as a
non-root user with a read-only root filesystem and a writable data volume.
Production requires HTTPS and `MONITOR_SECURE_COOKIES=true`; setting
`MONITOR_ENVIRONMENT=production` enforces that cookie setting. Before exposing a
reverse proxy, keep operational routes and Prometheus internal. See the
[administrator guide](docs/workspace.md) for authentication, account recovery and
session behavior.

## Register and monitor services

Approve exact origins in `.env`, then recreate the application container:

```dotenv
MONITOR_APPROVED_ORIGINS=["https://api.example.com"]
```

```bash
docker compose up -d fastapi
```

In the workspace, choose **Add service**, enter an approved health URL, and configure
its interval, timeout, failure threshold and expected HTTP status. Service details
show observations and response times; you can edit, pause, resume, check immediately,
or permanently delete the service. Incidents record sustained failures and recovery.

A new service is `unknown` until checked. Blocked targets do not count as outages or
successful observations. **Observed success** is successful checks divided by valid
retained checks, not continuous uptime or a contractual SLA. The interface exposes
sample counts, observation coverage and retention limits. See
[monitoring and target policy](docs/monitoring.md).

## Connect incident notifications

Set `MONITOR_WEBHOOK_URL` to an HTTPS endpoint that accepts generic JSON events, then
run `docker compose up -d fastapi`. Treat the full destination URL as a secret.
The Notifications page shows queued, delivered, failed and cancelled events, attempt
counts, and manual retry for failed deliveries. It never exposes the destination URL.

Outage, recovery and configuration-closure events are written in the same transaction
as the incident change. Temporary failures are retried; delivery is **at least once**.
Each event has a stable `event_id` and `Idempotency-Key` header so your receiver can
suppress repeats. See the [webhook contract](docs/notifications.md) for payloads,
network safeguards, retry behavior, ordering and limitations.

## Try a controlled outage

An optional Compose file runs an isolated sample target:

```bash
docker compose -f docker-compose.yml -f compose.demo.yml up --build -d
# Enter the existing administrator password securely for this script invocation.
read -r -s -p "Administrator password: " MONITOR_ADMIN_PASSWORD
export MONITOR_ADMIN_PASSWORD
python3 scripts/demonstrate-outage.py
unset MONITOR_ADMIN_PASSWORD
```

The script signs in, waits for scheduled checks, induces a failure, verifies one
incident, restores the target and verifies recovery. It keeps history for inspection;
use `--cleanup` to remove that invocation's service. The sample's control interface
has no authentication and must remain local. See the [demonstration guide](docs/demo.md).

## Develop and validate

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/) (CI pins uv 0.12.23).

```bash
uv sync --locked
uv run --locked python -m system_monitoring.admin
uv run --locked uvicorn system_monitoring.main:create_app --factory --reload --no-access-log
```

Local runs load `.env` and use `var/monitoring.sqlite3`; Compose uses its named volume.
Use one application process per SQLite installation. `uvicorn apps:app` remains
available as a compatibility entry point. Avoid running both APIs on the same port.

```bash
uv run --locked pytest -q
uv run --locked ruff check system_monitoring apps.py tests scripts
uv run --locked ruff format --check system_monitoring apps.py tests scripts
uv run --locked playwright install chromium
uv run --locked python scripts/check-browser.py --artifacts browser-artifacts
```

The browser check uses its own temporary database, administrator, HTTP target and
webhook receiver. It verifies actual navigation, outage/recovery, retry delivery,
charts, editing, pause/resume, session restoration and mobile layout. Screenshots
are saved as artifacts. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` can select a system Chromium;
otherwise the script uses an available `chromium` binary or Playwright's installation.

```bash
docker build -t system-monitoring:local .
bash scripts/check-container.sh system-monitoring:local
```

CI runs backend checks, browser checks, image validation, scheduled outage/recovery,
and all 13 operational dashboard queries. Docker Hub publication remains a separate
manual workflow with commit-tagged images. Corporate/cloud HTTPS proxies can supply
a trusted build-only CA bundle without disabling TLS or artifact verification:

```bash
docker build --build-arg HTTPS_PROXY --build-arg HTTP_PROXY --build-arg NO_PROXY \
  --secret id=ca-certificates,src=/path/to/trusted-ca-bundle.pem \
  -t system-monitoring:local .
```

`uv.lock` is authoritative. `req.txt` is a pip compatibility entry point. Update
intentionally with `uv lock --upgrade`, inspect the diff, and repeat validation.
The original retail experiment remains an [optional example](examples/retail/README.md).

## Configuration

Environment variables override `.env`. Never commit credentials; list values use JSON.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MONITOR_ADMIN_USERNAME` | `admin` | Initial/recovered administrator username |
| `MONITOR_ADMIN_PASSWORD` | unset | Optional initial bootstrap, minimum 12 characters |
| `MONITOR_SECURE_COOKIES` | `false` | Require HTTPS for session cookies; mandatory in production |
| `MONITOR_SESSION_SECONDS` | `28800` | Fixed session lifetime, from 5 minutes to 24 hours |
| `MONITOR_WEBHOOK_URL` | unset | Optional secret generic webhook destination |
| `MONITOR_WEBHOOK_ALLOW_PRIVATE` | `false` | Explicitly permit internal delivery; plain HTTP is restricted to internal IPs |
| `MONITOR_ENVIRONMENT` | `development` | `development`, `demo`, or `production` |
| `MONITOR_DATABASE_PATH` | `var/monitoring.sqlite3` | Local SQLite path; Compose fixes its internal path |
| `MONITOR_LOG_LEVEL` | `INFO` | Application JSON log level |
| `MONITOR_APPROVED_ORIGINS` | `[]` | Exact origins allowed for probes |
| `MONITOR_PRIVATE_ORIGINS` | `[]` | Approved subset permitted to reach private addresses |
| `MONITOR_SCHEDULER_ENABLED` | `true` | Automatic probes; manual probes remain available when false |
| `MONITOR_CHECK_CONCURRENCY` | `5` | Concurrent probes, 1–20 |
| `MONITOR_SERVICE_LIMIT` | `100` | Inventory limit, 1–1000 |
| `MONITOR_HISTORY_PER_SERVICE` | `1000` | Retained observations per service, 10–10000 |
| `GRAFANA_ADMIN_USER` | `admin` | Initial Grafana administrator |
| `GRAFANA_ADMIN_PASSWORD` | required | Initial Grafana password; distinct from application sign-in |
| `API_PORT` / `PROMETHEUS_PORT` / `GRAFANA_PORT` | `8000` / `9090` / `3000` | Local port mappings |
| `DEMO_PORT` | `8081` | Optional sample target's local control port |

Environment changes require `docker compose up -d`, rather than just `restart`.
Changing bootstrap values does not change an existing account. Changing Grafana
bootstrap values also does not reset an existing Grafana account.

## Storage and upgrades

Schema migrations preserve the inventory and incident history and add session and
notification storage transactionally. Back up before upgrading. Older applications
cannot open a newer schema; rollback requires restoring the matching database backup.
Application backups now contain password hashes, sessions and notification payloads:
protect them as sensitive data. See [storage guidance](docs/monitoring.md#storage).

`docker compose down` retains named volumes. **`docker compose down -v` deletes them.**
Pausing preserves history. Deleting a service removes its checks/incidents and cancels
pending notifications; delivered notification history remains available for auditing.

## Project layout

```text
system_monitoring/        Monitoring, authentication, persistence and webhook workers
system_monitoring/api/    Authenticated service, incident and workspace endpoints
system_monitoring/static/ Responsive HTML, CSS, JavaScript and local SVG assets
scripts/                 Operational, container and browser validation
tests/                   API, authentication, policy, persistence and delivery checks
provisioning/            Grafana datasource and operational dashboard
examples/retail/         Original optional recommendation experiment
docs/                   Setup, architecture, demonstration and release planning
```

See [the roadmap](docs/roadmap.md), [release plan](docs/release.md), and
[changelog](CHANGELOG.md). The companion website will follow the visual reference at
[Codewise-CLI](https://aryansharma9917.github.io/Codewise-CLI/). Historical images in
`assets/` show the original version, not the current workspace.
