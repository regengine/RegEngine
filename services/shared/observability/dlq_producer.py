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

Environment variables
---------------------
``DLQ_BOOTSTRAP_SERVERS``
    Kafka bootstrap server(s), e.g. ``kafka:9092``.  Defaults to ``localhost:9092``.
``DLQ_TOPIC_PREFIX``
    Optional prefix prepended to topic names (e.g. ``staging.``).  Defaults to
    the empty string so existing topic names are used unchanged.
"""

from __future__ import annotations

import os
import threading
from typing import Optional

import structlog

logger = structlog.get_logger("shared.dlq_producer")

# ---------------------------------------------------------------------------
# Module-level env-var defaults
# ---------------------------------------------------------------------------
_DEFAULT_BOOTSTRAP = os.environ.get("DLQ_BOOTSTRAP_SERVERS", "localhost:9092")
_TOPIC_PREFIX = os.environ.get("DLQ_TOPIC_PREFIX", "")

# Module-level singleton registry (keyed by topic so multiple services can
# share the same process without colliding).
_instances: dict[str, "DLQProducer"] = {}
_registry_lock = threading.Lock()


def get_dlq_producer(
    topic: Optional[str] = None,
    bootstrap_servers: Optional[str] = None,
    service_name: str = "unknown-service",
) -> "DLQProducer":
    """Return the singleton ``DLQProducer`` for *topic*, creating it on first call.

    Parameters
    ----------
    topic:
        DLQ Kafka topic name.  Defaults to ``<DLQ_TOPIC_PREFIX>dlq``.
    bootstrap_servers:
        Kafka bootstrap string.  Defaults to the ``DLQ_BOOTSTRAP_SERVERS``
        environment variable (falling back to ``localhost:9092``).
    service_name:
        Attached to every DLQ message header for traceability.
    """
    effective_topic = _TOPIC_PREFIX + (topic or "dlq")
    effective_bootstrap = bootstrap_servers or _DEFAULT_BOOTSTRAP

    with _registry_lock:
        if effective_topic not in _instances:
            _instances[effective_topic] = DLQProducer(
                bootstrap_servers=effective_bootstrap,
                topic=effective_topic,
                service_name=service_name,
            )
        return _instances[effective_topic]


def reset_dlq_producer(topic: Optional[str] = None) -> None:
    """Flush, close, and remove the singleton for *topic*.

    Primarily useful in tests and at process shutdown.
    """
    effective_topic = _TOPIC_PREFIX + (topic or "dlq")
    with _registry_lock:
        producer = _instances.pop(effective_topic, None)
    if producer is not None:
        producer.close()


class DLQProducer:
    """Thread-safe DLQ producer wrapper.

    Wraps a Kafka producer (confluent-kafka or kafka-python) behind a uniform
    interface so callers do not need to know which library is in use.  The
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

        Tries confluent-kafka first (used by graph service); falls back to
        kafka-python (used by admin/nlp) so the shared module works in both
        environments without adding a hard dependency on either library.
        """
        try:
            from confluent_kafka import Producer  # type: ignore[import]

            self._producer = Producer({"bootstrap.servers": self._bootstrap})
            self._confluent = True
            logger.info("dlq_producer_initialized", backend="confluent", topic=self._topic)
        except ImportError:
            pass

        if self._producer is None:
            try:
                import json  # noqa: F401 — side-effect import guard
                from kafka import KafkaProducer  # type: ignore[import]

                self._producer = KafkaProducer(
                    bootstrap_servers=self._bootstrap,
                    value_serializer=lambda v: (
                        v if isinstance(v, bytes) else __import__("json").dumps(v).encode("utf-8")
                    ),
                )
                self._confluent = False
                logger.info(
                    "dlq_producer_initialized", backend="kafka-python", topic=self._topic
                )
            except ImportError:
                logger.error(
                    "dlq_producer_no_kafka_library",
                    detail=(
                        "Neither confluent-kafka nor kafka-python is installed. "
                        "DLQ messages cannot be delivered."
                    ),
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
                if self._confluent:
                    self._producer.produce(  # type: ignore[union-attr]
                        self._topic,
                        value=value,
                        headers=built_headers,
                    )
                    self._producer.poll(0)  # type: ignore[union-attr]
                else:
                    self._producer.send(  # type: ignore[union-attr]
                        self._topic,
                        value=value,
                        headers=[(k, v) for k, v in built_headers],
                    )
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
                if self._confluent:
                    self._producer.flush(timeout)  # type: ignore[union-attr]
                else:
                    self._producer.flush(timeout=timeout)  # type: ignore[union-attr]
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
                if not self._confluent:
                    self._producer.close(timeout=2.0)  # type: ignore[union-attr]
                # confluent-kafka Producer has no explicit close(); GC handles it.
                self._producer = None
            logger.info("dlq_producer_closed", topic=self._topic)
        except Exception as exc:  # pragma: no cover - infra dependent
            logger.warning("dlq_producer_close_failed", error=str(exc))
