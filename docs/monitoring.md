# Service monitoring workflow

The application stores service configuration and observations in SQLite. A single
background scheduler selects due services, reserves each check transactionally,
runs bounded probes, and commits their results with incident state changes.
Prometheus scrapes current database state; Grafana visualizes those observations.

## Target policy

Set `MONITOR_APPROVED_ORIGINS` to a JSON list of exact origins, such as
`["https://api.example.com","https://status.example.com:8443"]`. An origin includes
the scheme, hostname and effective port, not a path or query. No wildcard matching
is performed. An empty list rejects every new target. Configuration is managed
outside the HTTP API and is rechecked for every probe, including after restarts.

For an internal endpoint, also include its origin in `MONITOR_PRIVATE_ORIGINS`.
This list must be a subset of approved origins. It is a deliberate network access
grant for that specific origin, so use it only for services you control.

URLs must be HTTP(S), without embedded credentials or fragments. Public origins
must resolve entirely to public IPs; mixed public/private DNS answers are rejected.
Internal exceptions allow private/loopback addresses, but never metadata/link-local,
multicast, unspecified or reserved addresses. Literal IPs are checked as well.
DNS is resolved for every new connection. The resolver returns validated numeric
addresses directly to the connector, which retains the hostname for HTTP Host and
TLS certificate verification. Redirects are not followed and environment proxy
settings are not used for probes. Bodies are not consumed. The deadline covers DNS,
TCP, TLS and response headers. Do not use token-bearing query strings or endpoints
requiring credentials; authenticated probes are outside this milestone.

Registration validates URL syntax and operator origin approval. DNS is validated
at check time, so registration does not claim that a service is reachable.

## API

Base path: `/api/v1`. The OpenAPI explorer at `/docs` describes request and response
fields. This API requires an administrator session and CSRF protection for mutations.
See [administrator access](workspace.md). Keep operational interfaces local and
require HTTPS before exposing the workspace.

| Method and path | Behavior |
| --- | --- |
| `POST /services` | Register a service; returns 201 and a Location header |
| `GET /services` | List services with latest state |
| `GET /services/{id}` | Read configuration and latest state |
| `PUT /services/{id}` | Replace the complete configuration, including enabled/paused state |
| `DELETE /services/{id}` | Permanently delete the service, checks and incidents |
| `POST /services/{id}/checks` | Run one bounded check immediately; returns its stored result |
| `GET /services/{id}/checks` | Most recent retained observations first |
| `GET /incidents` | Incident history, newest first |

List endpoints accept `limit` (1–100, default 50) and `offset` (default 0).
Incidents additionally accept `service_id` and `status=open` or `status=resolved`.
Missing service IDs return 404. Paused, already-running or invalidated checks return
409. Invalid configuration or unapproved targets return 422. Public error responses
omit exception internals and carry a generated request ID.

A complete service configuration:

```json
{
  "name": "Example API",
  "url": "https://api.example.com/health",
  "enabled": true,
  "check_interval_seconds": 60,
  "timeout_seconds": 5,
  "failure_threshold": 3,
  "expected_status": 200
}
```

Intervals range from 10 seconds to 24 hours; timeouts from 1 to 30 seconds and must
be shorter than the interval. Failure thresholds range from 1 to 20. The expected
HTTP status is exact (200–599), not a generic successful-status range. Unknown
configuration fields are rejected. PUT is a full replacement: copy the current
configuration fields and change the desired ones, including `enabled` to pause.

## State and incidents

- `unknown`: no completed observation for this target/configuration yet.
- `healthy`: the most recent check matched the expected status.
- `failing`: failed observations exist, but the failure threshold has not been met.
- `down`: an unresolved incident exists after sustained failures.
- `blocked`: the checker refused a target under the current network policy.
- `paused`: no scheduled or manual probes are allowed until re-enabled.

Failures increase the consecutive-failure count. At the threshold, one incident
opens. Further failures retain that incident. A success resets the count and closes
the incident with resolution `recovered`. A blocked probe resets the streak but
neither opens nor recovers an incident: refusal to check is not proof of an outage
or recovery. An existing incident remains open even while blocked or paused.

Changing the URL or expected status closes any open incident with
`configuration_changed`, clears the last observation, and schedules a fresh check.
This is distinct from recovery. Operational configuration changes reset a failure
streak; renaming alone preserves it. Check history records the configuration revision.
Pausing or editing invalidates in-flight results. A result from before an edit or
delete cannot create a new incident or rewrite the new configuration's state.

## Scheduling and concurrency

New services and enabled updates are immediately eligible. The scheduler polls
once per second and schedules the next check one configured interval after the
previous check completes. Under load a due check may wait for a free slot; this is
not a strict wall-clock or multi-region uptime guarantee.

A semaphore bounds concurrent probes, including manual checks. A transactional lease
prevents overlapping checks for one service; its token/revision must still match
when writing results. A crash may delay the next probe until its timeout plus five
seconds of lease grace expires. State and incidents persist across process restarts.
Shutdown cancels scheduler tasks cleanly. Use one application process and one
SQLite installation; this is not a distributed scheduler.

`MONITOR_SCHEDULER_ENABLED=false` disables automatic scheduling, not manual checks.
Readiness verifies the scheduler task/heartbeat when enabled, alongside usable storage.

## Metrics and dashboards

The Service Monitoring dashboard uses the provisioned `prometheus` datasource and
`job="fastapi"`. Its panels cover scrape health, open incidents, latest probe result,
paused state, probe duration, observation age, failure streak, scheduler heartbeat,
API request/error rates, p95 header latency, memory and CPU cores used.

| Metric | Meaning |
| --- | --- |
| `monitor_service_enabled` | 1 enabled, 0 paused |
| `monitor_service_up` | Latest HTTP probe matched expected status (1) or failed (0) |
| `monitor_service_last_check_timestamp_seconds` | Time of latest completed observation |
| `monitor_service_probe_duration_seconds` | Latest HTTP probe elapsed time |
| `monitor_service_consecutive_failures` | Current failure streak |
| `monitor_service_incident_open` | 1 while an incident remains unresolved |
| `monitor_scheduler_last_tick_timestamp_seconds` | Last successful scheduler scheduling pass |

Service metrics use service ID and name, not URL. Unknown, paused or blocked targets
have no `monitor_service_up` series; absent data must not be interpreted as healthy.
Observation age and API scrape health help identify stale data. SQLite-backed
collection restores the last observation across restart and drops deleted services
from new scrapes. Prometheus may retain older samples until its normal retention
expires. These charts show observed checks, not a contractual uptime calculation.

Prometheus scrapes every 15 seconds, so allow two scrapes for rates to populate.
HTTP latency histograms measure time to response headers; CPU rates are cores used,
not host-wide utilization. The workspace provides durable [webhook delivery](notifications.md) for incident transitions.

## Storage

Schema version 3 preserves inventory, observations, incidents and leases while
adding administrator sessions, an incident notification outbox and availability
epochs.
Migrations and their version update commit together. An incompatible/newer schema
prevents startup. Back up before upgrading and keep the old image for rollback;
rollback requires restoring the matching database backup, not downgrading in place.

For an offline backup, stop the application before copying the full application
volume, then restart it. For an online backup, use the included command rather than
copying a live database file without its WAL:

```bash
docker compose exec -T fastapi python -m system_monitoring.backup backup \
  /var/lib/system-monitoring/monitoring.sqlite3 \
  /var/lib/system-monitoring/monitoring-backup.sqlite3
```

The command creates a consistent snapshot, checks integrity and refuses to overwrite an
existing destination. Copy it to separate encrypted storage and verify restoration in
an isolated instance. Follow the [backup, restore and rollback runbook](backups.md).
Do not treat a backup in the same volume as disaster recovery. Incidents are retained
until the service is deleted; check history keeps the most recent configured number per
service (default 1000). Monitor disk usage and plan retention before a long-lived
customer deployment. Pausing preserves history. Deleting a service is permanent and
invalidates in-flight results; use pause if you want to keep the evidence.

## Verification

The automated suite covers HTTP responses, redirects, timeouts, DNS policy, schema
migration and rollback, concurrency, stale results, authentication, CSRF, account
recovery, observed availability, transactional notifications and actual delivery.
Ruff checks source and operational scripts. Browser checks exercise the complete
interface with real checks and a controlled webhook receiver, including retries.
The container check verifies non-root/read-only startup and restart persistence.
CI also runs the scheduled outage demonstration and all 13 Grafana queries.
