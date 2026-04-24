"""Shared DLQ (Dead Letter Queue) producer singleton.

#1228: Previously each service (graph/consumer.py, graph/consumers/fsma_consumer.py,
admin/review_consumer.py) kept its own copy of a DLQ producer singleton.  This
module consolidates that logic in one place.  Services import ``DLQProducer``
from here rather than defining it locally.

Usage example::

    from shared.observability.dlq_producer import DLQProducer

    dlq = DLQProducer(bootstrap_servers="localhost:9092", topic="my.service.dlq")
    dlq.send(original_bytes, reason="deserialization_error", detail="<traceback>")
    dlq.flush()
    dlq.close()
"""

from __future__ import annotations

import threading
from typing import Optional

import structlog

_instances: dict[str, "DLQProducer"] = {}
_instances_lock = threading.Lock()

logger = structlog.get_logger("shared.dlq_producer")


class DLQProducer:
    """Thread-safe DLQ producer wrapper.

    Wraps a Confluent Kafka producer behind a uniform interface so callers do
    not need to know the client details. The
    instance is created once at service startup and shared across threads via
    a lock.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        service_name: str = "unknown-service",
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._topic = topic
        self._service_name = service_name
        self._lock = threading.Lock()
        self._producer: Optional[object] = None
        self._confluent = False
        self._init_producer()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_producer(self) -> None:
        """Create the underlying Kafka producer.

        Creates the repo-standard confluent-kafka producer.
        """
        try:
            from confluent_kafka import Producer  # type: ignore[import]

            self._producer = Producer({"bootstrap.servers": self._bootstrap})
            self._confluent = True
            logger.info("dlq_producer_initialized", backend="confluent", topic=self._topic)
        except ImportError:
            logger.error(
                "dlq_producer_no_kafka_library",
                detail="confluent-kafka is not installed. DLQ messages cannot be delivered.",
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send(
        self,
        value: bytes,
        *,
        reason: str = "unknown",
        detail: str = "",
        original_topic: str = "",
        headers: Optional[list] = None,
    ) -> None:
        """Produce one DLQ message.

        ``value`` is the raw bytes of the failed message.  Metadata (reason,
        detail, original_topic, service_name) are attached as headers where
        the library supports it.
        """
        if self._producer is None:
            logger.error(
                "dlq_producer_not_initialized",
                reason=reason,
                topic=self._topic,
            )
            return

        built_headers = [
            ("error_reason", reason.encode("utf-8")),
            ("error_detail", str(detail)[:1024].encode("utf-8")),
            ("original_topic", original_topic.encode("utf-8")),
            ("service", self._service_name.encode("utf-8")),
        ]
        if headers:
            built_headers.extend(headers)

        try:
            with self._lock:
                self._producer.produce(  # type: ignore[union-attr]
                    self._topic,
                    value=value,
                    headers=built_headers,
                )
                self._producer.poll(0)  # type: ignore[union-attr]
            logger.info(
                "dlq_message_sent",
                topic=self._topic,
                reason=reason,
                service=self._service_name,
            )
        except Exception as exc:  # pragma: no cover - infra dependent
            logger.critical(
                "dlq_emission_failed",
                topic=self._topic,
                reason=reason,
                error=str(exc),
            )

    def flush(self, timeout: float = 5.0) -> None:
        """Flush any buffered messages.  Call before process exit."""
        if self._producer is None:
            return
        try:
            with self._lock:
                self._producer.flush(timeout)  # type: ignore[union-attr]
            logger.info("dlq_producer_flushed", topic=self._topic)
        except Exception as exc:  # pragma: no cover - infra dependent
            logger.error("dlq_producer_flush_failed", error=str(exc))

    def close(self) -> None:
        """Flush then close the producer.  Safe to call multiple times."""
        self.flush()
        if self._producer is None:
            return
        try:
            with self._lock:
                # confluent-kafka Producer has no explicit close(); GC handles it.
                self._producer = None
            logger.info("dlq_producer_closed", topic=self._topic)
        except Exception as exc:  # pragma: no cover - infra dependent
            logger.warning("dlq_producer_close_failed", error=str(exc))


def get_dlq_producer(
    topic: str,
    bootstrap_servers: str,
    service_name: str = "unknown-service",
) -> "DLQProducer":
    """Return a per-(topic, service) singleton DLQProducer, creating it on first call."""
    key = f"{service_name}:{topic}"
    if key not in _instances:
        with _instances_lock:
            if key not in _instances:
                _instances[key] = DLQProducer(
                    bootstrap_servers=bootstrap_servers,
                    topic=topic,
                    service_name=service_name,
                )
    return _instances[key]
