# Administrator workspace

The application serves its own HTML/CSS/JavaScript and SVG assets at `/` and `/assets`.
It does not require a Node runtime, CDN, analytics script or separate frontend server.
The responsive workspace provides an overview, searchable/filterable service table,
service details and response-time samples, incident history and webhook delivery status.
The separate [project website](https://aryansharma9917.github.io/SystemMonitoring/)
introduces the product and links back to the operational guides.
The workspace follows the browser or operating-system color preference on first use.
Its appearance button switches between light and dark modes and stores that choice in
the current browser. The preference contains no account or monitoring data.

## Accounts and sessions

Create the administrator using `python -m system_monitoring.admin` in the application
container or activated Python environment. The command reads the password from a
terminal and stores a PBKDF2-HMAC-SHA256 hash with a random salt and 600,000 iterations.
There is one administrator account and no public registration or default password.

Optional `MONITOR_ADMIN_PASSWORD` bootstraps an empty installation only. Account
creation and checking that no account exists happen transactionally. Subsequent
starts never replace the stored account, even if the bootstrap environment changes.
Remove bootstrap secrets after provisioning. Account recovery uses the interactive
command's `--reset-password` flag and revokes every existing session.

After sign-in, the browser receives a random session token in an HttpOnly,
SameSite=Strict cookie. Only the token hash is stored in SQLite. Sessions have a fixed
expiry, persist across application restarts, and are revoked on logout or account
recovery. At most 20 active session records are retained. Cookies must be Secure
in production; serve the application over HTTPS and set `MONITOR_SECURE_COOKIES=true`.
Configure your reverse proxy to preserve the intended host and scheme; cross-origin
requests are rejected using the application's base URL.

Mutating management requests also require `X-CSRF-Token`, obtained by sign-in or
`GET /api/auth/session`. The workspace keeps it in memory, not browser local storage.
Login checks the Origin header when supplied. Five failed attempts lock sign-in for
one minute; this account-wide limit is persisted across restarts. Protect access to
the local account-recovery command and the application data volume.

## API access

- `POST /api/auth/login` accepts JSON `username` and `password`, returning the session
  cookie, username, expiry and CSRF token.
- `GET /api/auth/session` restores an existing session without extending its expiry.
- `POST /api/auth/logout` revokes the current session and requires CSRF protection.
- `/api/v1/*`, `/docs`, and `/openapi.json` require the administrator session.
- `/health`, `/ready`, and `/metrics` remain operational endpoints for the local
  deployment and Prometheus. Keep them internal when adding a public reverse proxy.
- `/api/v1/about` returns the application metadata previously served at `/`.

Authentication errors return 401; invalid CSRF/origin returns 403; sign-in throttling
returns 429. An installation without an administrator returns 503 on sign-in and
continues to reject management access. There is no anonymous development bypass.
The outage script signs in using credentials supplied securely through its process
environment and signs out afterwards.

## Reading the overview

Current service state and historical observations are different. “Last check healthy”
means the most recent completed probe succeeded; it is not a guarantee of health
between checks. The interface marks observations overdue relative to their interval.
Unknown, paused and blocked states remain distinct from healthy observations.

Observed success is `successes / (successes + failures)` within the selected 1-hour,
24-hour or 7-day window and the retained sample history. Blocked checks are shown
separately. A service with no valid observations shows an em dash, never 100%.
Coverage displays first/last observations and warns when retention may have removed
older samples. Changing the URL or expected status starts a new availability epoch;
renaming does not discard the previous target's valid observations.

Response-time charts show actual retained samples, measured to response headers.
Blocked checks and long gaps are not connected by lines. These charts are not a
continuous uptime measurement or an SLA calculation. History tables are paginated.

## Validation

`uv run --locked python scripts/check-browser.py` creates an isolated installation,
HTTP target, administrator and webhook receiver. It exercises sign-in, adding and
editing a service, outage/recovery, persisted webhook retries, charts, pause/resume,
restored sessions, persistent dark mode, mobile layout and logout. CI retains desktop,
mobile, detail and sign-in screenshots. The browser data is generated by actual checks,
not fabricated availability statistics.
