"""
Shared Kafka consumer utilities for RegEngine services.

Consolidates common patterns across admin, graph, and NLP consumers:
- Topic creation (idempotent)
- Dead Letter Queue (DLQ) producer management
- Graceful shutdown coordination
- Consumer health monitoring
- Prometheus metric patterns

Usage:
    from shared.kafka_consumer_base import (
        kafka_health_check,
        ensure_topic,
        DLQManager,
        ConsumerHealthMonitor,
        graceful_shutdown,
    )

DEPRECATED: This module and all Kafka consumer wiring will be removed once
EVENT_BACKBONE=pg is the default (see #1159 split-brain fix, #1240 cleanup).
The PostgreSQL task_processor (server/workers/task_processor.py) is the
canonical event backbone. Kafka consumers are dead code for MVP traffic.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import structlog

logger = structlog.get_logger("kafka-consumer-base")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def kafka_health_check(
    bootstrap_servers: Optional[str] = None,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Test Kafka/Redpanda connectivity and return status dict.

    Returns a dict suitable for inclusion in HTTP health-check responses::

        {"status": "available", "broker_count": 1}
        {"status": "unavailable", "error": "..."}

    Uses the repo-standard ``confluent-kafka`` client.
    """
    servers = bootstrap_servers or os.environ.get(
        "KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092"
    )

    try:
        from confluent_kafka.admin import AdminClient

        admin = AdminClient({
            "bootstrap.servers": servers,
            "client.id": "health-check",
        })
        metadata = admin.list_topics(timeout=timeout)
        broker_count = len(metadata.brokers)
        logger.info("kafka_health_ok", brokers=broker_count)
        return {"status": "available", "broker_count": broker_count}
    except ImportError:
        logger.warning("confluent_kafka_not_installed")
        return {"status": "unavailable", "error": "confluent-kafka not installed"}
    except Exception as exc:
        logger.warning("kafka_health_unavailable", error=str(exc))
        return {"status": "unavailable", "error": str(exc)}


# ---------------------------------------------------------------------------
# Topic management
# ---------------------------------------------------------------------------

def ensure_topic(
    topic: str,
    bootstrap_servers: str,
    num_partitions: int = 1,
    replication_factor: int = 1,
    *,
    min_insync_replicas: int | None = None,
    kafka_library: str = "confluent-kafka",
) -> None:
    """Create a Kafka topic idempotently.

    Uses the repo-standard ``confluent-kafka`` admin client.
    If the topic already exists, this is a no-op.

    Args:
        min_insync_replicas: Topic-level min.insync.replicas override (#1005).
            Defaults to None (inherits broker default). Set to 2 in production
            with multi-broker clusters so acks=all actually requires 2+ replicas.
    """
    if kafka_library != "confluent-kafka":
        logger.warning("unsupported_kafka_library_ignored", kafka_library=kafka_library)
    _ensure_topic_confluent(
        topic,
        bootstrap_servers,
        num_partitions,
        replication_factor,
        min_insync_replicas,
    )


def _ensure_topic_confluent(
    topic: str, bootstrap: str, partitions: int, replication: int,
    min_isr: int | None = None,
) -> None:
    """confluent-kafka based topic creation."""
    try:
        from confluent_kafka.admin import AdminClient, NewTopic

        topic_config = {}
        if min_isr is not None:
            topic_config["min.insync.replicas"] = str(min_isr)

        admin = AdminClient({"bootstrap.servers": bootstrap})
        futures = admin.create_topics([NewTopic(
            topic, num_partitions=partitions, replication_factor=replication,
            config=topic_config if topic_config else None,
        )])
        for t, f in futures.items():
            try:
                f.result()
                logger.info("topic_created", topic=t)
            except Exception as exc:
                if "TOPIC_ALREADY_EXISTS" in str(exc):
                    pass
                else:
                    logger.warning("topic_creation_failed", topic=t, error=str(exc))
    except ImportError:
        logger.warning("confluent_kafka_not_installed", topic=topic)


# ---------------------------------------------------------------------------
# Dead Letter Queue (DLQ) manager
# ---------------------------------------------------------------------------

class DLQManager:
    """Thread-safe DLQ producer with lazy initialization.

    Example::

        dlq = DLQManager(
            bootstrap_servers="redpanda:9092",
            dlq_topic="nlp.extracted.dlq",
            source_topic="nlp.extracted",
        )
        dlq.send(original_event, error="Validation failed")
        dlq.close()
    """

    def __init__(
        self,
        bootstrap_servers: str,
        dlq_topic: str,
        source_topic: str = "unknown",
    ) -> None:
        self._bootstrap = bootstrap_servers
        self._dlq_topic = dlq_topic
        self._source_topic = source_topic
        self._producer = None
        self._lock = threading.Lock()
        self._retry_counts: Dict[str, int] = {}
        self._consecutive_failures: int = 0
        self._total_dlq_sends: int = 0
        self._total_dlq_failures: int = 0
        self._failure_alert_threshold: int = 3

    def _get_producer(self):
        """Lazy, thread-safe producer initialization."""
        if self._producer is None:
            with self._lock:
                if self._producer is None:
                    from shared.kafka_compat import KafkaProducerCompat
                    self._producer = KafkaProducerCompat(
                        bootstrap_servers=self._bootstrap,
                        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    )
        return self._producer

    def send(
        self,
        event: Dict[str, Any],
        error: str,
        doc_id: Optional[str] = None,
    ) -> None:
        """Send a failed message to the DLQ with error metadata."""
        try:
            producer = self._get_producer()
            retry_key = doc_id or "unknown"
            dlq_payload = {
                "original_event": event,
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "source_topic": self._source_topic,
                "retry_count": self._retry_counts.get(retry_key, 0),
            }
            producer.send(self._dlq_topic, value=dlq_payload)
            producer.flush(timeout=5.0)
            self._total_dlq_sends += 1
            self._consecutive_failures = 0
            logger.info(
                "message_sent_to_dlq",
                topic=self._dlq_topic,
                error=error,
                total_dlq_sends=self._total_dlq_sends,
            )
        except Exception as exc:
            self._consecutive_failures += 1
            self._total_dlq_failures += 1
            logger.error(
                "dlq_send_failed",
                topic=self._dlq_topic,
                error=str(exc),
                consecutive_failures=self._consecutive_failures,
                total_failures=self._total_dlq_failures,
            )
            if self._consecutive_failures >= self._failure_alert_threshold:
                logger.critical(
                    "dlq_alert_dead_letter_unavailable",
                    topic=self._dlq_topic,
                    source_topic=self._source_topic,
                    consecutive_failures=self._consecutive_failures,
                    message="Dead letter queue is unreachable — failed events are being dropped",
                )

    def track_retry(self, doc_id: str) -> int:
        """Increment and return the retry count for a document."""
        self._retry_counts[doc_id] = self._retry_counts.get(doc_id, 0) + 1
        return self._retry_counts[doc_id]

    def clear_retries(self, doc_id: str) -> None:
        """Clear retry count after successful processing or DLQ send."""
        self._retry_counts.pop(doc_id, None)

    def close(self) -> None:
        """Flush and close the DLQ producer."""
        with self._lock:
            if self._producer is not None:
                try:
                    self._producer.close(timeout=2.0)
                except Exception as exc:
                    logger.debug("dlq_producer_close_failed", error=str(exc))
                self._producer = None


# ---------------------------------------------------------------------------
# Consumer health monitor
# ---------------------------------------------------------------------------

class ConsumerHealthMonitor:
    """Tracks consumer liveness for health check endpoints.

    Example::

        health = ConsumerHealthMonitor(stale_threshold_seconds=30)
        health.mark_started()
        # In consumer loop:
        health.mark_poll()
        # From health endpoint:
        return health.get_status()
    """

    def __init__(self, stale_threshold_seconds: int = 30) -> None:
        self._stale_threshold = stale_threshold_seconds
        self._shutdown_event = threading.Event()
        self._last_poll: Optional[datetime] = None
        self._started_at: Optional[datetime] = None

    def mark_started(self) -> None:
        self._started_at = datetime.now(timezone.utc)

    def mark_poll(self) -> None:
        self._last_poll = datetime.now(timezone.utc)

    @property
    def shutdown_event(self) -> threading.Event:
        return self._shutdown_event

    def stop(self) -> None:
        """Signal graceful shutdown."""
        self._shutdown_event.set()

    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()

    def get_status(self) -> Dict[str, Any]:
        """Return health status dict for HTTP endpoints."""
        now = datetime.now(timezone.utc)
        is_alive = not self._shutdown_event.is_set()

        seconds_since_poll = None
        poll_stale = False
        if self._last_poll and is_alive:
            seconds_since_poll = (now - self._last_poll).total_seconds()
            poll_stale = seconds_since_poll > self._stale_threshold

        return {
            "alive": is_alive,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "last_poll_at": self._last_poll.isoformat() if self._last_poll else None,
            "seconds_since_poll": seconds_since_poll,
            "poll_stale": poll_stale,
            "healthy": is_alive and not poll_stale,
        }


# ---------------------------------------------------------------------------
# Graceful shutdown helper
# ---------------------------------------------------------------------------

def graceful_shutdown(
    consumer: Any,
    dlq_manager: Optional[DLQManager] = None,
    health_monitor: Optional[ConsumerHealthMonitor] = None,
    logger_name: str = "consumer",
) -> None:
    """Standard cleanup sequence for consumer shutdown."""
    _logger = structlog.get_logger(logger_name)

    if dlq_manager:
        dlq_manager.close()

    try:
        consumer.close()
    except Exception as exc:
        _logger.warning("consumer_close_error", error=str(exc))

    _logger.info("consumer_stopped")
