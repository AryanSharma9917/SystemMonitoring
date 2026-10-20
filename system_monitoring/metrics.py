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


class ServiceCollector:
    """Read current persisted state on scrape; restarts never invent healthy data."""

    def __init__(self, repository) -> None:
        self.repository = repository

    def collect(self):
        from prometheus_client.core import GaugeMetricFamily

        definitions = {
            "monitor_service_enabled": "Whether scheduled monitoring is enabled.",
            "monitor_service_up": "Last probe succeeded; absent if unknown, paused or blocked.",
            "monitor_service_last_check_timestamp_seconds": "Unix time of the last stored check.",
            "monitor_service_probe_duration_seconds": "Last HTTP probe duration in seconds.",
            "monitor_service_consecutive_failures": "Consecutive failed checks.",
            "monitor_service_incident_open": "Whether the service has an unresolved incident.",
        }
        families = {
            name: GaugeMetricFamily(name, description, labels=["service_id", "service_name"])
            for name, description in definitions.items()
        }
        for service in self.repository.list_services(self.repository.service_limit, 0):
            labels = [service["id"], service["name"]]
            families["monitor_service_enabled"].add_metric(labels, int(service["enabled"]))
            families["monitor_service_consecutive_failures"].add_metric(
                labels, service["consecutive_failures"]
            )
            families["monitor_service_incident_open"].add_metric(
                labels, int(service["open_incident_id"] is not None)
            )
            if service["last_check_timestamp"] is not None:
                families["monitor_service_last_check_timestamp_seconds"].add_metric(
                    labels, service["last_check_timestamp"]
                )
            if service["enabled"] and service["last_outcome"] in {"success", "failure"}:
                families["monitor_service_up"].add_metric(
                    labels, int(service["last_outcome"] == "success")
                )
                families["monitor_service_probe_duration_seconds"].add_metric(
                    labels, service["last_duration_seconds"]
                )
        yield from families.values()
