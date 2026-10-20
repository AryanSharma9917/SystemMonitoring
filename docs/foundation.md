# Application foundation

The application uses Python 3.12 with dependencies resolved in `uv.lock`.
`system_monitoring/` owns configuration, the FastAPI factory, structured logs,
Prometheus metrics and versioned SQLite storage. The original retail experiment
and its data live separately under `examples/retail/`.

The root endpoint describes the application; `/health` is process liveness and
`/ready` checks storage and the enabled monitoring scheduler. Application errors
use a consistent shape and generated request ID. Database initialization and
schema changes are transactional; a newer schema is never silently downgraded.

Docker uses pinned build/runtime images, locked runtime dependencies, an
unprivileged user and persistent named storage. The image excludes local secrets,
retail data and generated files. The optional build CA secret supports trusted
HTTPS proxies without weakening certificate verification.

The application checks run on all branches and pull requests. Docker Hub
publication is manual and produces commit-tagged images. Follow the README for
local setup, quality checks, and container restart validation.

This foundation now supports the [monitoring workflow](monitoring.md). Authentication,
notifications and the customer-facing interface remain on the [roadmap](roadmap.md).
