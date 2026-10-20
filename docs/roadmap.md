# Delivery roadmap

Each milestone targets one focused workday, followed by review on its own branch.
Commit messages describe the change in ordinary language. Distinct areas receive
separate coherent commits; the project owner reviews and merges into `main`.

## Application foundation — implemented

Modern Python dependencies and locking, application structure, validated settings,
SQLite persistence, structured logs/errors, readiness, reproducible Docker and CI.
See [foundation notes](foundation.md).

## Monitoring workflow — implemented

Service registration and updates, operator-approved targets, bounded HTTP checks,
consecutive failure thresholds, incident opening/recovery, persistent check history,
corrected dashboards and a controlled outage target. Acceptance: an induced outage
opens one incident and recovery resolves it with verifiable observations.
See the [monitoring guide](monitoring.md) and [demonstration](demo.md).

## Product dashboard — upcoming

Responsive service overview/details, incident history, administrator authentication,
one configured webhook channel with duplicate suppression and recovery notifications,
and clearly defined availability summaries. Acceptance: add-service → outage →
alert → recovery works through the interface.

## Website and demonstration polish — upcoming

Companion website inspired by https://aryansharma9917.github.io/Codewise-CLI/,
actual screenshots, installation guidance, architecture, contact/demo action,
deployment guidance, backup/recovery practice, and a recorded walkthrough.
Acceptance: a fresh installation supports a repeatable demonstration and the
website accurately describes the software.

Initial service offering: isolated installations with setup, dashboard configuration,
alert tuning and maintenance. Multi-tenant accounts, billing, distributed collectors,
and AI diagnosis need later implementation and operational validation.
