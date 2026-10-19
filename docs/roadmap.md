# Four-day delivery plan

## Day 1: Foundation

Modern Python dependencies and locking; application structure; validated settings;
SQLite persistence; structured logs and errors; readiness; reproducible Docker;
meaningful CI and restart validation. See `day-1.md` for the review scope.

## Day 2: Monitoring workflow

Service registration, approved target validation, bounded HTTP checks, failure
thresholds, incident opening/recovery, corrected Prometheus/Grafana queries, and a
controlled sample service. Acceptance: an induced outage opens one incident and
recovery resolves it with accurate metrics.

## Day 3: Product dashboard

Responsive service overview and details, incident history, authentication for
management, one configured webhook channel with duplicate suppression and recovery
notifications, and clearly defined availability summaries. Acceptance: the complete
add-service → outage → alert → recovery journey works through the UI.

## Day 4: Website and demo

Companion website inspired by https://aryansharma9917.github.io/Codewise-CLI/;
actual screenshots, installation guidance, architecture, contact/demo action,
controlled demo, deployment guidance, backup/recovery instructions, and a recorded
walkthrough. Acceptance: a fresh installation supports a repeatable demonstration
and the website accurately describes what the software does.

Initial service offering: isolated installations with setup, dashboard configuration,
alert tuning, and maintenance. Multi-tenant accounts, billing, distributed collectors,
and AI diagnosis require later work and operational validation.

Use descriptive commit messages without conventional prefixes. Keep distinct areas
in separate coherent commits. Work on a review branch and leave merging to `main`
to the project owner after review.
