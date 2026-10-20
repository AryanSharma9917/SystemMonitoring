"""Transactional webhook outbox with stable event IDs and bounded retries."""

import asyncio
import ipaddress
import json
import logging
import time
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

import aiohttp

from system_monitoring import __version__
from system_monitoring.targets import ApprovedResolver, TargetBlocked, TargetPolicy

logger = logging.getLogger("system_monitoring.notifications")


def enqueue(connection, service: dict, incident: dict, kind: str) -> None:
    event_id = str(uuid4())
    occurred = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    payload = {
        "event_id": event_id,
        "type": kind,
        "occurred_at": occurred,
        "service": {"id": service["id"], "name": service["name"]},
        "incident": incident,
        "text": f"{service['name']}: {kind.removeprefix('incident.').replace('_', ' ')}",
    }
    connection.execute(
        """INSERT INTO notifications
        (event_id,incident_id,service_id,event_type,payload,created_at) VALUES(?,?,?,?,?,?)
        ON CONFLICT(incident_id,event_type) DO NOTHING""",
        (event_id, incident["id"], service["id"], kind, json.dumps(payload), occurred),
    )


class WebhookPolicy(TargetPolicy):
    def validate_address(self, address, value):
        super().validate_address(address, value)
        if value.startswith("http:") and ipaddress.ip_address(address).is_global:
            raise TargetBlocked("Public webhook destinations require HTTPS")


class WebhookDelivery:
    def __init__(self, database, settings):
        self.database, self.settings = database, settings
        self.task: asyncio.Task | None = None
        self.last_tick: float | None = None
        self.started_at: float | None = None

    def start(self):
        self.started_at = time.time()
        self.task = asyncio.create_task(self.run(), name="webhook-delivery")

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    def ready(self):
        return bool(
            self.task
            and not self.task.done()
            and time.time() - (self.last_tick or self.started_at or 0) < 25
        )

    def claim(self):
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT n.* FROM notifications n WHERE status='pending'
                AND next_attempt_at<=? AND lease_until<=? AND NOT EXISTS (
                  SELECT 1 FROM notifications older WHERE older.incident_id=n.incident_id
                  AND older.id<n.id AND older.status='pending'
                ) ORDER BY n.id LIMIT 1""",
                (time.time(), time.time()),
            ).fetchone()
            if row is None:
                return None
            token = str(uuid4())
            # Count an attempted delivery before sending, including interrupted sends.
            connection.execute(
                "UPDATE notifications SET lease_token=?,lease_until=?,attempts=attempts+1 "
                "WHERE id=?",
                (token, time.time() + 15, row["id"]),
            )
            return {**dict(row), "lease_token": token, "attempts": row["attempts"] + 1}

    def complete(self, event, status, error=None):
        with self.database.connect() as connection:
            connection.execute(
                """UPDATE notifications SET status=?,last_error=?,delivered_at=?,
                next_attempt_at=?,lease_token=NULL,lease_until=0
                WHERE id=? AND lease_token=? AND status='pending'""",
                (
                    status,
                    error,
                    datetime.now(UTC).isoformat() if status == "delivered" else None,
                    time.time() + min(2 ** event["attempts"], 300),
                    event["id"],
                    event["lease_token"],
                ),
            )

    async def send(self, event):
        if event["attempts"] > 6:
            return "failed", "Delivery interrupted too many times"
        url = self.settings.webhook_url.get_secret_value()
        policy = WebhookPolicy([url], [url] if self.settings.webhook_allow_private else [])
        try:
            url = policy.validate(url)
            connector = aiohttp.TCPConnector(
                resolver=ApprovedResolver(policy, url),
                use_dns_cache=False,
                force_close=True,
            )
            async with (
                asyncio.timeout(10),
                aiohttp.ClientSession(
                    connector=connector,
                    trust_env=False,
                    auto_decompress=False,
                    timeout=aiohttp.ClientTimeout(total=10),
                    read_bufsize=1024,
                    max_line_size=4096,
                    max_field_size=4096,
                    cookie_jar=aiohttp.DummyCookieJar(),
                ) as session,
            ):
                async with session.post(
                    url,
                    data=event["payload"].encode(),
                    allow_redirects=False,
                    headers={
                        "Content-Type": "application/json",
                        "Idempotency-Key": event["event_id"],
                        "User-Agent": f"SystemMonitoring-Webhook/{__version__}",
                    },
                ) as response:
                    code = response.status
                    response.close()
            if 200 <= code < 300:
                return "delivered", None
            retryable = code in {408, 429} or code >= 500
            error = f"Webhook returned HTTP {code}"
        except ValueError:
            return "failed", "Webhook destination blocked by network policy"
        except (aiohttp.ClientError, OSError, TimeoutError):
            retryable, error = True, "Webhook connection failed or timed out"
        return ("pending" if retryable and event["attempts"] < 6 else "failed"), error

    async def run(self):
        while True:
            try:
                event = await asyncio.to_thread(self.claim)
                self.last_tick = time.time()
                if event:
                    status, error = await self.send(event)
                    await asyncio.to_thread(self.complete, event, status, error)
            except Exception:
                logger.exception("Webhook delivery worker failed")
            await asyncio.sleep(1)
