# Backup, restore and rollback

The SQLite database contains service configuration, observations, incidents,
administrator password hashes, active sessions and notification payloads. Treat every
copy as sensitive. Back it up before an application upgrade and store an encrypted copy
away from the server.

## Create a consistent backup

Do not copy the live `monitoring.sqlite3` file with `cp`: committed data may still be
in SQLite's write-ahead log. The backup command uses SQLite's online backup API, checks
database and reference integrity, and refuses to overwrite an existing destination.

```bash
docker compose exec -T fastapi python -m system_monitoring.backup backup \
  /var/lib/system-monitoring/monitoring.sqlite3 \
  /var/lib/system-monitoring/backup-$(date -u +%Y%m%dT%H%M%SZ).sqlite3
```

Copy the new file from the `application-data` volume to encrypted storage immediately.
Record its application version and checksum beside it. Delete volume-local copies only
after the off-server copy has been verified.

## Practice a restore

Restore to a new path. The restore command retains monitoring history and administrator
credentials, but revokes saved sessions and clears worker leases. It validates the
source and never overwrites a destination.

```bash
docker compose stop fastapi
docker compose run --rm --no-deps fastapi python -m system_monitoring.backup restore \
  /var/lib/system-monitoring/backup.sqlite3 \
  /var/lib/system-monitoring/restored.sqlite3
```

Update `MONITOR_DATABASE_PATH` for a local process, or move the stopped container's
validated restored file into the configured location using a temporary maintenance
container. Preserve the previous database under a different name until validation is
complete. Start the application, sign in again, confirm inventory and incident history,
then perform a controlled check. Keep the old database until the recovery window ends.

Compose fixes the application database path to
`/var/lib/system-monitoring/monitoring.sqlite3`; changing the host `.env` does not alter
that path. Never replace the file while the application is running.

## Upgrade and rollback

1. Record the running Git commit or image digest and create a verified backup.
2. Pull the reviewed release and build or pull its matching image.
3. Run `docker compose up -d` and wait for readiness.
4. Sign in, inspect stored services and run one controlled check.
5. If validation fails, stop the application. Restore the pre-upgrade snapshot to a new
   file, switch back to the previous image and place that matching database at the
   configured path before restarting.

Older application versions cannot open newer schemas. Rolling back the image without
restoring the matching pre-upgrade database is unsupported. Prometheus and Grafana have
their own named volumes; back those up separately if their historical charts matter.

Run restore practice against a separate Compose project or copied volume. A recovery
exercise should never modify the only production database.
