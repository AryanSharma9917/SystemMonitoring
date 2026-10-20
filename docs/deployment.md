# HTTPS deployment runbook

The supported initial production shape is one isolated installation for one team or
customer. It uses one application process, SQLite, Prometheus and Grafana. The included
Caddy overlay terminates HTTPS for the administrator workspace. Prometheus and Grafana
remain on the private Compose network.

## Prepare the host

- Use a maintained Linux host with Docker Engine and Compose v2.
- Point an A/AAAA record for the monitoring domain at the host.
- Allow inbound TCP 80 and TCP/UDP 443. Do not expose 8000, 3000, 9090 or the demo port.
- Restrict SSH, enable host security updates and send encrypted backups off the host.
- Clone a reviewed release or exact commit. Do not deploy a moving branch in production.

Create `.env` from the example. Set unique Grafana credentials, your public domain and
ACME contact email. Set only the exact origins this installation needs to probe. Keep
webhook URLs and passwords in deployment secrets rather than source control.

```dotenv
MONITOR_DOMAIN=monitor.example.com
ACME_EMAIL=operations@example.com
MONITOR_APPROVED_ORIGINS=["https://api.example.com"]
GRAFANA_ADMIN_PASSWORD=choose-a-unique-secret
# After the release exists, pin its immutable digest:
# MONITOR_IMAGE=ghcr.io/aryansharma9917/systemmonitoring@sha256:...
```

## Start and verify

Do not combine the production and demonstration overlays. The demo control API has no
authentication and is intended only for a local demonstration.

```bash
docker compose -f docker-compose.yml -f compose.production.yml config --quiet
docker compose -f docker-compose.yml -f compose.production.yml up --build -d
docker compose -f docker-compose.yml -f compose.production.yml exec fastapi \
  python -m system_monitoring.admin
```

Verify from another machine:

```bash
curl --fail --proto '=https' --tlsv1.2 https://monitor.example.com/
curl --fail --proto '=https' --tlsv1.2 https://monitor.example.com/health
```

The workspace request should return HTML. The second request should return 404 because
the proxy keeps operational endpoints private. From the application container,
`python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready')"`
should succeed. Sign in, register a noncritical approved target and confirm an actual
observation. Verify the certificate hostname, expiry and issuer in a browser.

The application validates browser origins against the forwarded public scheme. Caddy
is the trusted proxy in this topology. Do not put an untrusted proxy on the Compose
network or forward client-supplied `X-Forwarded-*` values without replacing them.

## Operate the installation

- Inspect `/ready` within the private network and alert if it fails.
- Review application logs, open incidents, failed notification deliveries and Grafana.
- Keep clocks synchronized: sessions, leases, scheduling and certificate issuance depend
  on accurate time.
- Back up before upgrades and practice restoration. See [backup and rollback](backups.md).
- Rotate the administrator password with `python -m system_monitoring.admin
  --reset-password`; all sessions are revoked.
- Update `.env` with `docker compose up -d`; `restart` alone does not load new values.

Caddy obtains and renews public certificates automatically. Its `caddy-data` volume
contains certificate state and must persist across container replacement. If you use a
cloud load balancer instead, keep `MONITOR_ENVIRONMENT=production` and
`MONITOR_SECURE_COOKIES=true`, preserve the original HTTPS scheme, and implement the
same operational-route restriction there.

## Scope and capacity

SQLite and the in-process workers require one application replica. This deployment has
no built-in failover. Plan a maintenance window for restore and upgrade. Load test with
your intervals, retention and target latency before committing to a service level.
Availability in the interface is successful retained checks divided by valid retained
checks, not continuous or time-weighted uptime.

Use separate installations and credentials for separate customers. Multi-tenant data
isolation, billing, regional collectors and high availability require further product
and operational work.
