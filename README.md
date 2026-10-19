# System Monitoring

A service monitoring project being rebuilt around a practical workflow: register a
service, detect a sustained failure, follow the incident, and verify recovery.
FastAPI provides the application API; Prometheus and Grafana provide metrics and
operational dashboards.

**Current milestone: Day 1 foundation.** The API, persistent database, structured
logs, reproducible build, and automated checks are implemented. Service management,
active checks, alerts, a customer dashboard, and the public website are upcoming.
This version is for local development, not an authenticated public deployment.

## Start the development stack

Requires Docker Engine and Docker Compose v2. From the repository root:

```bash
cp .env.example .env
# Edit .env and set GRAFANA_ADMIN_PASSWORD to a password you choose.
docker compose up --build -d
docker compose ps
```

First startup requires registry and package downloads. Compose refuses to start
without a Grafana administrator password. Ports bind to the local machine only.

| Component | Local address | Purpose |
| --- | --- | --- |
| API | `http://localhost:8000` | Application information |
| API documentation | `http://localhost:8000/docs` | OpenAPI explorer |
| Liveness | `http://localhost:8000/health` | Process responds |
| Readiness | `http://localhost:8000/ready` | Persistent schema is accessible |
| Metrics | `http://localhost:8000/metrics` | HTTP and Python process metrics |
| Prometheus | `http://localhost:9090` | Metrics queries and scrape targets |
| Grafana | `http://localhost:3000` | Operational dashboards |

Sign in to Grafana using the username and password configured in `.env`.
Credentials initialize a **new** Grafana volume; changing `.env` does not reset an
existing administrator password. Follow Grafana's password reset procedure for an
existing installation rather than deleting its volume.

```bash
curl --fail http://localhost:8000/ready
curl --fail http://localhost:8000/health
curl --fail http://localhost:8000/metrics
docker compose logs --tail 50 fastapi
docker compose stop
docker compose start
```

Prometheus scrapes every 15 seconds. After the first interval, its `up` query should
report `1` for both `fastapi` and `prometheus`. Existing dashboard panels are being
reworked in Day 2: some still reference historical labels and should not yet be used
to assess latency or availability.

## Develop with Python

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/) (CI uses uv 0.12.23).
Dependencies, including optional examples and development tools, are resolved in
`uv.lock`. From the repository root:

```bash
uv sync --locked
uv run --locked uvicorn system_monitoring.main:create_app --factory --reload --no-access-log
```

Use either this process or the Compose API on port 8000, or choose a different
port. Local runs load `.env` and use `var/monitoring.sqlite3`; containers use a
named volume. The old `uvicorn apps:app` entry point remains available.

```bash
uv run --locked pytest -q
uv run --locked ruff check system_monitoring apps.py tests
uv run --locked ruff format --check system_monitoring apps.py tests
```

`req.txt` is a compatibility entry point for pip, not a second lockfile. Use the uv
commands above for reproducible installs. To intentionally update dependencies, run
`uv lock --upgrade`, inspect the changes, and repeat the checks.

## Configuration

Copy `.env.example`; never commit credentials. Process environment variables take
precedence over `.env`. Invalid application configuration prevents startup.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MONITOR_ENVIRONMENT` | `development` | `development`, `demo`, or `production`; a label, not a security mode |
| `MONITOR_DATABASE_PATH` | `var/monitoring.sqlite3` | Local SQLite file; Compose fixes this inside its data volume |
| `MONITOR_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `GRAFANA_ADMIN_USER` | `admin` | Initial Grafana administrator |
| `GRAFANA_ADMIN_PASSWORD` | required | Initial Grafana administrator password |
| `API_PORT` / `PROMETHEUS_PORT` / `GRAFANA_PORT` | `8000` / `9090` / `3000` | Local Compose port mappings |

`/health` checks liveness. `/ready` returns 503 if the database or required schema
becomes unavailable. Startup initializes versioned storage without dropping existing
data and refuses databases created by a newer schema version.

Application request logs are JSON with generated request IDs, route templates,
status codes, and duration. Responses include `X-Request-ID`; errors return
`error.code`, `error.message`, `error.details`, and `request_id`. Request bodies,
query strings, and authentication headers are not logged by the request logger.
HTTP duration metrics measure time to response headers. Metrics use route templates
and group unknown paths and methods to keep labels bounded.

## Storage and container checks

SQLite stores the service definitions and incidents needed by subsequent
milestones. The database uses foreign keys, transactional initialization, WAL mode,
and a constraint preventing two open incidents for the same service. Day 1 has no
service-management API yet.

Compose keeps application, Prometheus, and Grafana data in separate named volumes.
`docker compose down` retains them. **`docker compose down -v` deletes them.**
The API image runs as an unprivileged user; only its data directory needs write access.

```bash
docker build -t system-monitoring:day1 .
bash scripts/check-container.sh system-monitoring:day1
```

If an enterprise or cloud HTTPS proxy uses a custom CA, pass its trusted PEM
bundle as an optional build secret; certificate and lockfile hash verification stay
enabled, and the bundle is not copied into the runtime image:

```bash
docker build --build-arg HTTPS_PROXY --build-arg HTTP_PROXY --build-arg NO_PROXY \
  --secret id=ca-certificates,src=/path/to/trusted-ca-bundle.pem \
  -t system-monitoring:day1 .
```

The check creates its own temporary container and volume, verifies readiness and
metrics, inserts sample records, restarts the container, verifies persistence, and
cleans up its own resources. It does not modify your development data.

CI runs the Python checks, validates Compose configuration, builds the image, and
runs this container check on pushes and pull requests. Docker Hub publication is a
separate manual workflow using `DOCKER_USERNAME` and `DOCKER_PASSWORD`; published
images receive the commit SHA as their tag.

## Repository layout

```text
system_monitoring/        Application factory, settings, storage, logs and metrics
system_monitoring/api/    Health routes and consistent API errors
tests/                    Application and storage behavior checks
scripts/                  Container validation
provisioning/             Grafana datasource and dashboard configuration
examples/retail/           Original retail recommendation experiment and dataset
docs/                     Review notes and the four-day roadmap
```

The retail example is optional and does not provide monitoring intelligence. See
[its instructions](examples/retail/README.md). Historical screenshots in `assets/`
show the previous version and are not screenshots of the upcoming product UI.

See [the Day 1 review notes](docs/day-1.md) and [the remaining roadmap](docs/roadmap.md).
