# Day 1 review guide

Branch: `day-1-foundation`. This milestone prepares the backend; it does not yet
perform availability checks or implement the product UI.

## Review areas

- `pyproject.toml`, `.python-version`, and `uv.lock` replace the old dependency pins
  with a Python 3.12 application and a single lockfile. Retail dependencies are optional.
- `system_monitoring/` holds the factory, validated settings, SQLite schema,
  route-level request logs, metrics, readiness, and error handling. `apps.py` remains
  a compatibility import. The root response now describes the application.
- `tests/` replaces arithmetic placeholders with behavior checks, including real
  SQLite state across app restarts and safe error responses.
- The original retail files and dataset live under `examples/retail/`. No runtime
  monitoring code imports them. The incomplete nested Git entry had no `.gitmodules`
  configuration or checked-out content; it was removed without deleting other work.
- Tracked Python bytecode, the unused root dashboard, and the unused
  `config.monitoring` credential defaults are removed. Grafana has one provisioned
  dashboard source and an explicit datasource UID. Dashboard query repair is Day 2.
- Docker installs the locked runtime dependencies, excludes the retail dataset and
  local secrets, and runs as an unprivileged user. SQLite uses a named volume.
- CI checks every branch and pull requests. Image publication is manual, validated,
  and tagged by commit, so pushing a review branch does not publish an image.

## Verify locally

Follow the README's `uv sync --locked`, lint, formatting, and pytest commands.
Then set up `.env`, start Compose, check `/ready`, and query Prometheus `up`.
Run `scripts/check-container.sh` against the built image to exercise container
restart persistence using its own temporary data volume.

## Boundaries and migration notes

The Python runtime moves from the repository's old 3.11 declaration to 3.12.
The root greeting changes; `/health` retains its previous response. Clients should
use `/ready` when they require usable application storage.

This is a single-instance SQLite foundation. Authentication, monitoring target
validation, background checks, incident APIs, alert delivery, and the customer UI
are subsequent work. Keep this version on a trusted local machine. Setting the
configuration label to `production` does not add those controls.

The monitoring containers use verified image digests. The Python and uv build
images are also pinned; upgrade them deliberately and re-run the image checks.
The legacy dashboards still contain outdated label filters, so importing them is
not evidence that all panels are correct. There are no availability or latency
claims based on those panels in this milestone.

## Validation performed in the cloud workspace

- All 26 application/storage/configuration/logging/metrics checks passed.
- Ruff lint and formatting checks passed.
- Runtime image built from the lockfile using the cloud proxy's trusted CA bundle
  and its DNS host mapping. No certificate or artifact verification was disabled.
- The container check passed with a read-only root filesystem and persisted both
  service and incident records across a restart.
- Full Compose startup passed: API readiness, metrics exposure, both Prometheus
  targets healthy, and Grafana querying `up` through its provisioned datasource.
- Optional retail dependencies import on Python 3.12; the recommendation algorithm
  was not rewritten or validated for recommendation quality.

The cloud instance uses Compose project `systemmonitoring-day1`; its local ignored
`.env` records that project name and a generated Grafana password. Neither is
committed. A fresh local checkout should create its own `.env` following the README.
One upstream Starlette/AnyIO deprecation warning remains in the test runner; no
application checks are skipped or marked as expected failures.
