"""Prometheus metrics for scheduler observability."""

from __future__ import annotations

from functools import wraps
from typing import Callable, Dict

import structlog

logger = structlog.get_logger("metrics")

# Try to import prometheus_client, gracefully degrade if not available
try:
    from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed, metrics disabled")


if PROMETHEUS_AVAILABLE:
    # Scrape metrics
    SCRAPE_COUNTER = Counter(
        "scheduler_scrapes_total",
        "Total number of scrape operations",
        ["source_type", "status"],
    )

    SCRAPE_DURATION = Histogram(
        "scheduler_scrape_duration_seconds",
        "Duration of scrape operations",
        ["source_type"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
    )

    ITEMS_FOUND = Counter(
        "scheduler_items_found_total",
        "Total items found by scrapers",
        ["source_type"],
    )

    ITEMS_NEW = Counter(
        "scheduler_items_new_total",
        "New items detected (not duplicates)",
        ["source_type"],
    )

    # Notification metrics
    WEBHOOK_COUNTER = Counter(
        "scheduler_webhook_deliveries_total",
        "Total webhook delivery attempts",
        ["url_hash", "status"],
    )

    WEBHOOK_DURATION = Histogram(
        "scheduler_webhook_duration_seconds",
        "Webhook delivery duration",
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
    )

    # Kafka metrics
    KAFKA_EVENTS = Counter(
        "scheduler_kafka_events_total",
        "Total Kafka events emitted",
        ["topic", "status"],
    )

    # #1147 — observability for the Kafka emit failure path. Partial
    # failures (success_count + failure_count in the same batch) are
    # silent in the logs but visible here; alert on sustained nonzero.
    KAFKA_EMIT_FAILURES = Counter(
        "scheduler_kafka_emit_failures_total",
        "Kafka emission failures (hard exceptions or per-item failures)",
        ["source_type", "failure_mode"],
    )

    # Circuit breaker metrics
    CIRCUIT_STATE = Gauge(
        "scheduler_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=half-open, 2=open)",
        ["name"],
    )

    CIRCUIT_FAILURES = Counter(
        "scheduler_circuit_breaker_failures_total",
        "Circuit breaker failures",
        ["name"],
    )

    # State management metrics
    SEEN_ITEMS = Gauge(
        "scheduler_seen_items_total",
        "Total items in seen state",
        ["source_type"],
    )

    # Scheduler info
    SCHEDULER_INFO = Info(
        "scheduler",
        "Scheduler service information",
    )


class MetricsCollector:
    """Collects and exposes Prometheus metrics."""

    def __init__(self):
        self.enabled = PROMETHEUS_AVAILABLE

    def record_scrape(
        self,
        source_type: str,
        success: bool,
        duration_seconds: float,
        items_found: int = 0,
        items_new: int = 0,
    ) -> None:
        """Record scrape operation metrics."""
        if not self.enabled:
            return

        status = "success" if success else "failure"
        SCRAPE_COUNTER.labels(source_type=source_type, status=status).inc()
        SCRAPE_DURATION.labels(source_type=source_type).observe(duration_seconds)

        if items_found > 0:
            ITEMS_FOUND.labels(source_type=source_type).inc(items_found)
        if items_new > 0:
            ITEMS_NEW.labels(source_type=source_type).inc(items_new)

    def record_webhook(
        self,
        url: str,
        success: bool,
        duration_seconds: float,
    ) -> None:
        """Record webhook delivery metrics."""
        if not self.enabled:
            return

        # Hash URL for label (avoid high cardinality)
        import hashlib
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]

        status = "success" if success else "failure"
        WEBHOOK_COUNTER.labels(url_hash=url_hash, status=status).inc()
        WEBHOOK_DURATION.observe(duration_seconds)

    def record_kafka_event(self, topic: str, success: bool) -> None:
        """Record Kafka event emission."""
        if not self.enabled:
            return

        status = "success" if success else "failure"
        KAFKA_EVENTS.labels(topic=topic, status=status).inc()

    def record_kafka_emit_failure(
        self, source_type: str, failure_mode: str, count: int = 1
    ) -> None:
        """Record a Kafka emit failure for alerting (#1147).

        failure_mode values:
          - "hard_exception" — emit_batch raised ConnectionError / Timeout.
          - "partial_batch"  — emit_batch returned failures > 0.

        Downstream alerts should fire on rate > 0 sustained for >5min.
        """
        if not self.enabled:
            return
        if count <= 0:
            return
        KAFKA_EMIT_FAILURES.labels(
            source_type=source_type, failure_mode=failure_mode
        ).inc(count)

    def record_circuit_state(self, name: str, state: str) -> None:
        """Record circuit breaker state.

        Args:
            name: Circuit breaker name
            state: "closed", "half_open", or "open"
        """
        if not self.enabled:
            return

        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(state, 0)
        CIRCUIT_STATE.labels(name=name).set(state_value)

    def record_circuit_failure(self, name: str) -> None:
        """Record circuit breaker failure."""
        if not self.enabled:
            return

        CIRCUIT_FAILURES.labels(name=name).inc()

    def update_seen_items(self, counts: Dict[str, int]) -> None:
        """Update seen items gauge.

        Args:
            counts: Dict of source_type -> count
        """
        if not self.enabled:
            return

        for source_type, count in counts.items():
            SEEN_ITEMS.labels(source_type=source_type).set(count)

    def set_info(self, version: str, environment: str) -> None:
        """Set scheduler info labels."""
        if not self.enabled:
            return

        SCHEDULER_INFO.info({
            "version": version,
            "environment": environment,
        })

    def get_metrics(self) -> bytes:
        """Generate metrics in Prometheus format."""
        if not self.enabled:
            return b""

        return generate_latest()


# Singleton instance
metrics = MetricsCollector()


def timed_scrape(source_type: str) -> Callable:
    """Decorator to time and record scrape operations."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time

            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start

                # Assume result has these attributes (ScrapeResult)
                success = getattr(result, "success", True)
                items_found = getattr(result, "items_found", 0)
                items_new = getattr(result, "items_new", 0)

                metrics.record_scrape(
                    source_type=source_type,
                    success=success,
                    duration_seconds=duration,
                    items_found=items_found,
                    items_new=items_new,
                )

                return result

            except Exception as e:
                duration = time.time() - start
                metrics.record_scrape(
                    source_type=source_type,
                    success=False,
                    duration_seconds=duration,
                )
                raise

        return wrapper

    return decorator
