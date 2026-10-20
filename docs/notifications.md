# Webhook notifications

Set `MONITOR_WEBHOOK_URL` to a secret HTTPS endpoint accepting JSON, then recreate the
application container. The destination cannot be edited through the management API,
and its URL is never returned by the workspace. With no destination configured,
monitoring continues and future notification events are not queued.

## Event contract

Each transition is written to the outbox in the same SQLite transaction as its
incident change. Repeated failed probes do not create repeated outage events.
Events include `incident.opened`, `incident.recovered`, and `incident.closed` for a
configuration change. Configuration closure is not described as service recovery.

```json
{
  "event_id": "a-stable-unique-event-id",
  "type": "incident.opened",
  "occurred_at": "2026-10-20T12:00:00.000Z",
  "service": {"id": "service-id", "name": "Payments API"},
  "incident": {
    "id": "incident-id",
    "opened_at": "2026-10-20T12:00:00.000Z",
    "resolved_at": null,
    "reason": "Unexpected HTTP status 503",
    "resolution": null
  },
  "text": "Payments API: opened"
}
```

POST requests use `Content-Type: application/json` and `Idempotency-Key: <event_id>`.
The payload is a snapshot and omits the monitored target URL. The `text` field is
human-readable; this is a generic webhook contract, not a claim of native support
for every chat/incident platform. Use a compatible receiver or adapter.

## Delivery semantics

Delivery is **at least once**. A process may crash after the receiver accepts an
event but before SQLite records the acknowledgment. Every retry therefore retains
the same event ID and header. Receivers must store/deduplicate that ID to prevent
repeated downstream messages; exactly-once delivery cannot be guaranteed by an HTTP
sender alone.

The worker sends one event at a time. Earlier pending events for an incident block
later events for that incident, so a recovery does not overtake an outage that is
waiting to retry. Other incidents can still make progress. If an earlier event
exhausts its attempts, later events may proceed and contain their own full context.

- HTTP 2xx means the destination accepted the event and is shown as delivered.
- HTTP 408, 429, 5xx, connection failures and timeouts are retried.
- Other responses, including redirects, are terminal failures.
- Up to six delivery attempts are made, with exponential delays. Claims expire
  after 15 seconds so interrupted attempts can resume after a restart.
- Failed deliveries can be manually retried by an authenticated administrator;
  that resets the attempt budget while retaining the same event ID.

The Notifications page exposes status, attempts, timestamps and sanitized errors.
It never exposes the URL, secret query strings or the full stored payload. Retrying
a delivered/pending/cancelled event is rejected. Deleting a service cancels its pending
outbox entries; an HTTP request already accepted by a receiver cannot be recalled.
Delivered history is retained even after the service is removed.

Pending entries survive restarts and use the currently configured destination.
Changing the destination sends pending entries to the new destination. Removing
configuration stops the worker but retains existing entries; newly occurring events
are not queued while disabled. Existing incidents are not replayed when a webhook
is first configured, though later recovery/closure events can still occur.

## Network policy and credentials

Public destinations require HTTPS. DNS is checked on each connection, and the exact
validated numeric addresses are used while TLS verifies the hostname. Redirects,
URL user-info credentials, metadata/link-local and reserved addresses are blocked.
Environment proxies are not used and response bodies are not consumed/decompressed.
The total timeout is ten seconds.

Internal delivery requires `MONITOR_WEBHOOK_ALLOW_PRIVATE=true`, explicitly granting
access to private/loopback addresses for this configured destination. Plain HTTP is
allowed only to those internal addresses, never public IPs. Keep local demonstration
receivers isolated; production destinations should use HTTPS.

A token in a webhook's path or query remains part of the secret destination URL.
Protect `.env`, process environment and application backups. No credentials should
be entered in chat, committed, or embedded in website examples. Generic authorization
header configuration and per-user/multi-channel routing are outside this milestone.

## Operations

The worker's task/heartbeat participates in readiness when a destination is enabled.
A responsive worker can still have failed deliveries; inspect the Notifications page
rather than treating readiness as evidence that every receiver accepted every event.
Incident and delivery histories currently persist until explicitly managed; monitor
volume growth and implement retention policy before a long-lived deployment.
