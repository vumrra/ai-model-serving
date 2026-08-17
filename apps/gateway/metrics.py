from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


class GatewayMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "qwen_http_requests_total",
            "Gateway HTTP requests",
            ["method", "path", "status"],
            registry=self.registry,
        )
        self.active = Gauge(
            "qwen_active_requests",
            "Active inference requests",
            registry=self.registry,
        )
        self.ttft = Histogram(
            "qwen_ttft_seconds",
            "Time to first streamed content token",
            buckets=(0.1, 0.25, 0.5, 1, 2, 3, 5, 10, 30),
            registry=self.registry,
        )
        self.engine_ready = Gauge(
            "qwen_engine_ready",
            "Whether the inference engine readiness check succeeds",
            registry=self.registry,
        )
        self.stream_errors = Counter(
            "qwen_stream_errors_total",
            "Streams interrupted after HTTP 200 was sent",
            registry=self.registry,
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)


def metric_path(path: str) -> str:
    known = {"/livez", "/readyz", "/version", "/metrics", "/v1/chat/completions"}
    return path if path in known else "other"
