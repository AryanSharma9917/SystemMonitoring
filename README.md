# System Monitoring

Register an HTTP service, detect sustained failures, track the incident, and verify
recovery. FastAPI manages the monitoring workflow, SQLite preserves observations,
and Prometheus/Grafana expose service and application health.

**Available:** service inventory, scheduled HTTP checks, configurable failure
thresholds, persistent incident history, corrected operational dashboards, and an
isolated outage demonstration. Authentication, notifications, the customer-facing
interface, and the public website are upcoming. Keep this version on a trusted
local machine; the management API is not ready for public exposure.

## Start the stack

Requires Docker Engine and Docker Compose v2. From the repository root:

```bash
cp .env.example .env
# Edit .env: choose GRAFANA_ADMIN_PASSWORD and configure approved origins.
docker compose up --build -d
docker compose ps
curl --fail http://localhost:8000/ready
```

All published ports bind to the local machine. The application runs as a non-root
user with a read-only root filesystem and a writable data volume. A fresh Grafana
volume requires the administrator password in `.env`; changing that value does not
reset the password in an existing Grafana database.

| Component | Local address | Purpose |
| --- | --- | --- |
| API documentation | `http://localhost:8000/docs` | Interactive service and incident API |
| Liveness | `http://localhost:8000/health` | Process responds |
| Readiness | `http://localhost:8000/ready` | Database and enabled scheduler are usable |
| Metrics | `http://localhost:8000/metrics` | Application and monitored-service metrics |
| Prometheus | `http://localhost:9090` | Scrape status and metrics queries |
| Grafana | `http://localhost:3000` | Service Monitoring dashboard |

## Monitor a service

Approve destinations **in operator configuration**, not through the API. For example,
add this JSON array to `.env`, then recreate the application container:

```dotenv
MONITOR_APPROVED_ORIGINS=["https://example.com"]
```

```bash
docker compose up -d fastapi
curl --fail http://localhost:8000/api/v1/services \
  -H 'Content-Type: application/json' \
  -d '{"name":"Example service","url":"https://example.com/","check_interval_seconds":60,"timeout_seconds":5,"failure_threshold":3}'
curl --fail http://localhost:8000/api/v1/services
curl --fail 'http://localhost:8000/api/v1/incidents?status=open'
```

Use a real service you operate when evaluating failures. New services are `unknown`
until observed. Checks run automatically, expect HTTP 200 by default, and do not
follow redirects. A failure becomes an incident only after the configured number
of consecutive failures; the first successful check resolves it. Policy-blocked
checks are distinct from service failures and never open or recover an incident.

Private services require their exact origin in **both** approved and private origin
lists. Public origins cannot resolve to private addresses. Metadata, link-local,
multicast, unspecified, and reserved IP addresses remain prohibited. DNS answers
are checked on every connection and the validated numeric IPs are used directly;
TLS still verifies the original hostname. Probe requests bypass environment proxies,
reject URL credentials, use bounded deadlines, and do not consume response bodies.
See [target policy and API details](docs/monitoring.md).

## Demonstrate an outage

An optional Compose file starts a separate sample service whose health you control.
It approves only that sample origin for this isolated demonstration:

```bash
docker compose -f docker-compose.yml -f compose.demo.yml up --build -d
python3 scripts/demonstrate-outage.py
```

The script waits for automatic healthy checks, induces HTTP 503 responses, verifies
one incident opens, restores the target, and verifies recovery and history. It takes
roughly 30–45 seconds and leaves the registered service and incident for inspection.
Use `--cleanup` to remove only that run's service and history afterwards.

Never include the demonstration service in a public deployment. See the
[demonstration guide](docs/demo.md) for manual controls, slow responses, cleanup,
and dashboard verification.

## Develop with Python

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/) (CI uses uv 0.12.23).

```bash
uv sync --locked
uv run --locked uvicorn system_monitoring.main:create_app --factory --reload --no-access-log
uv run --locked pytest -q
uv run --locked ruff check system_monitoring apps.py tests scripts
uv run --locked ruff format --check system_monitoring apps.py tests scripts
```

Use one application process for a SQLite installation. Do not add Uvicorn workers
or run multiple application replicas against the same file. For local Python runs,
`.env` is loaded and the database defaults to `var/monitoring.sqlite3`; Compose
uses its named data volume. Avoid running the local API and Compose API on the same
port. `uvicorn apps:app` remains a compatibility entry point.

`uv.lock` is authoritative. `req.txt` supports pip installation but is not a separate
lockfile. To update dependencies intentionally, use `uv lock --upgrade`, review the
changes, and repeat application and container checks. The optional retail example
is separate: see [its instructions](examples/retail/README.md).

## Configuration

Environment variables override `.env`; never commit credentials. Lists use JSON.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MONITOR_ENVIRONMENT` | `development` | Configuration label: `development`, `demo`, or `production`; not a security mode |
| `MONITOR_DATABASE_PATH` | `var/monitoring.sqlite3` | Local SQLite path; Compose uses its internal volume path |
| `MONITOR_LOG_LEVEL` | `INFO` | Application JSON log level |
| `MONITOR_APPROVED_ORIGINS` | `[]` | Exact allowed HTTP(S) origins; no paths or wildcards |
| `MONITOR_PRIVATE_ORIGINS` | `[]` | Subset explicitly permitted to reach internal addresses |
| `MONITOR_SCHEDULER_ENABLED` | `true` | Run scheduled checks; manual checks remain available when disabled |
| `MONITOR_CHECK_CONCURRENCY` | `5` | Maximum concurrent probes, from 1 to 20 |
| `MONITOR_SERVICE_LIMIT` | `100` | Maximum inventory size, from 1 to 1000 |
| `MONITOR_HISTORY_PER_SERVICE` | `1000` | Retained checks per service, from 10 to 10000 |
| `GRAFANA_ADMIN_USER` | `admin` | Initial Grafana administrator |
| `GRAFANA_ADMIN_PASSWORD` | required | Initial Grafana password |
| `API_PORT` / `PROMETHEUS_PORT` / `GRAFANA_PORT` | `8000` / `9090` / `3000` | Local Compose ports |
| `DEMO_PORT` | `8081` | Optional demonstration control port |

Changes to Compose environment values require `docker compose up -d`, not just
`restart`. Background checks honor the same target policy as manually requested
checks. Services that become disallowed are reported as blocked, not healthy.

Application logs include generated request IDs, route templates, statuses, timings,
and probe outcomes. Responses carry `X-Request-ID`. Errors have `error.code`,
`error.message`, `error.details`, and `request_id`; request values are omitted from
validation errors. Request bodies, URL queries and authentication headers are not
included in request logs. Do not put credentials in target URLs.

## Storage and upgrades

Startup migrates the original schema transactionally and preserves service and
incident records. Failed migrations roll back, and newer schemas are rejected.
Back up the database before upgrading; an older application cannot read the new
schema. See [migration, retention and recovery guidance](docs/monitoring.md#storage).

Application, Prometheus and Grafana use separate named volumes. `docker compose
down` retains them. **`docker compose down -v` deletes them.** Pausing a service
preserves its history; deleting it permanently removes its checks and incidents.

```bash
docker build -t system-monitoring:local .
bash scripts/check-container.sh system-monitoring:local
```

This check uses its own temporary container and volume to verify non-root startup,
health, metrics and persistence across restart. CI also runs the real scheduled
outage demonstration and queries every provisioned dashboard panel. Image publication
is a separate manual workflow tagged by commit SHA.

For corporate/cloud HTTPS proxies, pass the trusted CA bundle as a build secret;
TLS and locked artifact verification remain enabled and the bundle is not copied
into the runtime image:

```bash
docker build --build-arg HTTPS_PROXY --build-arg HTTP_PROXY --build-arg NO_PROXY \
  --secret id=ca-certificates,src=/path/to/trusted-ca-bundle.pem \
  -t system-monitoring:local .
```

## Project layout

```text
system_monitoring/        Application, scheduler, HTTP checker, storage and metrics
system_monitoring/api/    Service, incident and health routes
scripts/                 Container checks and scheduled outage demonstration
provisioning/            Grafana datasource and Service Monitoring dashboard
tests/                   Network, API, policy, migration and persistence checks
examples/retail/         Original optional recommendation experiment
docs/                    Architecture, API, demonstration and roadmap
```

Historical screenshots in `assets/` show the original project. See the
[foundation notes](docs/foundation.md), [monitoring guide](docs/monitoring.md), and
[remaining roadmap](docs/roadmap.md) for scope and upcoming work.
