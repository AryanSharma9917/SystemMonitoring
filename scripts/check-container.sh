#!/usr/bin/env bash
# Exercise the built image without depending on host ports or Compose secrets.
set -euo pipefail
image="${1:-system-monitoring:local}"
container="monitoring-check-$$"
volume="monitoring-check-data-$$"
cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker volume create "$volume" >/dev/null
docker run -d --name "$container" \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges \
  -v "$volume:/var/lib/system-monitoring" "$image" >/dev/null

wait_for_health() {
  for ((attempt=0; attempt<45; attempt++)); do
    if [ "$(docker inspect --format '{{.State.Health.Status}}' "$container")" = healthy ]; then
      return 0
    fi
    if [ "$(docker inspect --format '{{.State.Running}}' "$container")" != true ]; then
      break
    fi
    sleep 1
  done
  docker logs "$container"
  return 1
}
wait_for_health

docker exec -i "$container" python - <<'PY'
import json
import os
import sqlite3
import urllib.request

assert os.getuid() != 0
for route in ('health', 'ready'):
    with urllib.request.urlopen(f'http://127.0.0.1:8000/{route}', timeout=3) as response:
        assert response.status == 200
        assert 'status' in json.load(response)
with urllib.request.urlopen('http://127.0.0.1:8000/metrics', timeout=3) as response:
    assert b'http_requests_total' in response.read()
with sqlite3.connect(os.environ['MONITOR_DATABASE_PATH']) as connection:
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute(
        "INSERT INTO services (id, name, url) VALUES ('smoke', 'Example', 'https://example.com')"
    )
    connection.execute(
        "INSERT INTO incidents (id, service_id, reason) VALUES ('smoke', 'smoke', 'Demo timeout')"
    )
PY

docker restart "$container" >/dev/null
wait_for_health
docker exec -i "$container" python - <<'PY'
import os
import sqlite3
with sqlite3.connect(os.environ['MONITOR_DATABASE_PATH']) as connection:
    assert connection.execute("SELECT name FROM services WHERE id='smoke'").fetchone() == ('Example',)
    assert connection.execute("SELECT reason FROM incidents WHERE id='smoke'").fetchone() == ('Demo timeout',)
print('Container runs as non-root; health and metrics work; services and incidents survive restart.')
PY
