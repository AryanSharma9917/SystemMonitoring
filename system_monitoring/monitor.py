"""A bounded scheduler with persisted leases and orderly shutdown."""

import asyncio
import logging
import time
from contextlib import suppress

from system_monitoring.checker import HttpChecker
from system_monitoring.repository import MissingService, Repository, ServiceConflict

logger = logging.getLogger("system_monitoring.monitor")


class Monitor:
    def __init__(self, repository: Repository, checker: HttpChecker, concurrency: int) -> None:
        self.repository = repository
        self.checker = checker
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.tasks: set[asyncio.Task] = set()
        self.task: asyncio.Task | None = None
        self.last_tick: float | None = None
        self.started_at: float | None = None

    def start(self) -> None:
        self.started_at = time.time()
        self.task = asyncio.create_task(self.run(), name="service-monitoring")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def check(self, service_id: str, *, force: bool = True) -> dict:
        async with self.semaphore:
            service = await asyncio.to_thread(self.repository.claim, service_id, force=force)
            result = await self.checker.probe(service)
            stored = await asyncio.to_thread(self.repository.record, service, result)
            logger.info(
                "Service check completed",
                extra={"service_id": service_id, "outcome": result.outcome},
            )
            return stored

    async def scheduled_check(self, service_id: str) -> None:
        try:
            await self.check(service_id, force=False)
        except (MissingService, ServiceConflict):
            # Paused, edited, removed or claimed since selecting due services.
            pass
        except Exception:
            logger.exception("Scheduled service check failed")

    async def run(self) -> None:
        while True:
            try:
                due = await asyncio.to_thread(self.repository.due, time.time())
                self.last_tick = time.time()
                available = self.concurrency - len(self.tasks)
                for service_id in due[: max(0, available)]:
                    task = asyncio.create_task(self.scheduled_check(service_id))
                    self.tasks.add(task)
                    task.add_done_callback(self.tasks.discard)
            except Exception:
                logger.exception("Unable to schedule service checks")
            await asyncio.sleep(1)

    def ready(self) -> bool:
        return bool(
            self.task
            and not self.task.done()
            and (time.time() - (self.last_tick or self.started_at or 0) < 10)
        )
