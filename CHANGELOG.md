# Changelog

## 2.0.0

### Monitoring workspace

- Responsive service overview, details, charts, incident history and delivery activity.
- Administrator sign-in, revocable server-side sessions, CSRF protection, sign-in
  throttling and local account recovery.
- Service inventory, scheduled bounded HTTP checks, persistent observations, failure
  thresholds, incidents and recovery.
- Observed availability with explicit samples, coverage, retention limits and
  target-change epochs.
- Transactional webhook events, stable delivery IDs, bounded retries and recovery
  notifications.
- Prometheus metrics, a provisioned 13-panel Grafana dashboard and controlled outage
  demonstration.

### Operations and presentation

- Python 3.12, locked dependencies, versioned SQLite storage and structured logs.
- Non-root container, persistent volumes, readiness checks and automated validation.
- Consistent live database backup, validated restore, upgrade and rollback practice.
- Optional HTTPS reverse proxy for one isolated production installation.
- Public project website with actual product screenshots and a recorded walkthrough.
- Persistent light and dark modes across the workspace and public project website.
- Browser, container, stack, backup and responsive website validation in CI.

The supported initial production scope is one administrator and one application process
per isolated team or customer installation. Observed success is retained check data,
not continuous uptime or a contractual SLA. Multi-tenant accounts, billing, high
availability and distributed collectors are not included.
