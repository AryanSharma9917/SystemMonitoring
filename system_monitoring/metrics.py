"""Application-owned metrics with stable names and bounded route labels."""

from prometheus_client import (
    CollectorRegistry,
    Counter,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
)


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        ProcessCollector(registry=self.registry)
        GCCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)
        self.requests = Counter(
            "http_requests_total",
            "Completed HTTP requests by route, method and status class.",
            ["handler", "method", "status"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "http_request_duration_seconds",
            "Time to produce response headers in seconds.",
            ["handler", "method"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )

    def observe(self, handler: str, method: str, status: int, duration: float) -> None:
        # Arbitrary HTTP methods and unknown paths must not grow metric cardinality.
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            method = "OTHER"
        self.requests.labels(handler, method, f"{status // 100}xx").inc()
        self.duration.labels(handler, method).observe(duration)
