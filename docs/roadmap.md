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

## Product dashboard — implemented

Responsive service overview/details, incident history, administrator authentication,
one generic webhook destination with transactional event deduplication, stable delivery
IDs and recovery notifications,
and clearly defined availability summaries. Acceptance: add-service → outage →
alert → recovery works through the interface. See the [workspace](workspace.md) and
[notification contract](notifications.md).

## Website and demonstration polish — implemented

Companion website inspired by https://aryansharma9917.github.io/Codewise-CLI/,
actual screenshots, installation guidance, architecture, contact/demo action,
deployment guidance, tested backup/recovery practice, and a recorded walkthrough.
The website and its responsive layout are checked in Chromium and published from the
reviewed `main` branch through GitHub Pages.

Initial service offering: isolated installations with setup, dashboard configuration,
alert tuning and maintenance. Multi-tenant accounts, billing, distributed collectors,
and AI diagnosis need later implementation and operational validation.


## Project release — prepared, publish after final review

Version 2.0.0, its changelog, release notes and tagged-release workflow are prepared.
After this final feature branch is reviewed and merged, validate the exact `main`
commit and push the annotated `v2.0.0` tag. The workflow publishes a commit-tagged
container digest and creates the GitHub release from those reviewed notes. See the
[release plan](release.md).
