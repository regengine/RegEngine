"""Kafka producer for emitting enforcement events."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Optional

import structlog
from kafka import KafkaProducer as KafkaProducerLib
from kafka.errors import KafkaError

from shared.observability.kafka_propagation import inject_correlation_headers_tuples

from .config import get_settings
from .models import AlertEvent, EnforcementItem

logger = structlog.get_logger("kafka_producer")


class KafkaEventProducer:
    """Produces enforcement events to Kafka topics.

    Topics:
    - enforcement.changes: All detected enforcement changes
    - alerts.regulatory: High-priority alerts (CRITICAL/HIGH severity)
    """

    def __init__(self, bootstrap_servers: Optional[str] = None):
        settings = get_settings()
        self.bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self.topic_enforcement = settings.kafka_topic_enforcement
        self.topic_alerts = settings.kafka_topic_alerts
        self.topic_fsma = settings.kafka_topic_fsma
        self._producer: Optional[KafkaProducerLib] = None
        self._initialized = False

    def _get_producer(self) -> KafkaProducerLib:
        """Get or create Kafka producer.

        Hardened config (#1147):
        - ``acks="all"``: wait for all in-sync replicas
        - ``retries=10`` (was 3) and ``retry_backoff_ms=500`` for
          exponential-ish backoff on transient broker errors
        - ``max_in_flight_requests_per_connection=5`` (was 1) — with
          retries>0 and acks=all this is still ordered per partition
          via kafka-python's sequence-numbering
        - ``request_timeout_ms=30000``
        """
        if self._producer is None:
            try:
                self._producer = KafkaProducerLib(
                    bootstrap_servers=self.bootstrap_servers.split(","),
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8") if k else None,
                    acks="all",  # Wait for all replicas
                    retries=10,  # #1147 — was 3, too low for transient 5xx
                    retry_backoff_ms=500,  # #1147
                    max_in_flight_requests_per_connection=5,  # #1147
                    request_timeout_ms=30000,
                )
                self._initialized = True
                logger.info(
                    "kafka_producer_initialized",
                    bootstrap_servers=self.bootstrap_servers,
                )
            except KafkaError as e:
                logger.error("kafka_producer_init_failed", error=str(e))
                raise

        return self._producer

    def emit_enforcement_change(self, item: EnforcementItem) -> bool:
        """Emit an enforcement change event.

        Args:
            item: The enforcement item to emit

        Returns:
            True if sent successfully, False otherwise
        """
        event = AlertEvent(
            source_type=item.source_type,
            item=item,
        )

        return self._send(
            topic=self.topic_enforcement,
            key=item.source_id,
            value=event.to_kafka_dict(),
        )

    def emit_high_priority_alert(self, item: EnforcementItem) -> bool:
        """Emit a high-priority alert for CRITICAL/HIGH severity items.

        Args:
            item: The enforcement item (should be CRITICAL or HIGH severity)

        Returns:
            True if sent successfully, False otherwise
        """
        event = AlertEvent(
            event_type="alert.high_priority",
            source_type=item.source_type,
            item=item,
        )

        return self._send(
            topic=self.topic_alerts,
            key=item.source_id,
            value=event.to_kafka_dict(),
        )

    def emit_batch(self, items: list[EnforcementItem]) -> tuple[int, int]:
        """Emit a batch of enforcement items.

        Returns:
            Tuple of (success_count, failure_count)
        """
        success = 0
        failures = 0

        for item in items:
            # Emit to enforcement.changes
            if self.emit_enforcement_change(item):
                success += 1
            else:
                failures += 1

            # Also emit high-priority alerts
            if item.severity.value in ["critical", "high"]:
                self.emit_high_priority_alert(item)

        # Flush to ensure all messages are sent
        self.flush()

        return success, failures

    def emit_fsma_event(self, fsma_event: dict) -> bool:
        """Emit an FSMA trace event for graph ingestion.

        Args:
            fsma_event: FSMA event dict from FDA-to-FSMA transformer

        Returns:
            True if sent successfully, False otherwise
        """
        event_id = fsma_event.get("event_id", "unknown")
        
        return self._send(
            topic=self.topic_fsma,
            key=event_id,
            value=fsma_event,
        )

    def emit_fsma_batch(self, fsma_events: list[dict]) -> tuple[int, int]:
        """Emit a batch of FSMA events.

        Args:
            fsma_events: List of FSMA event dicts

        Returns:
            Tuple of (success_count, failure_count)
        """
        success = 0
        failures = 0

        for event in fsma_events:
            if self.emit_fsma_event(event):
                success += 1
            else:
                failures += 1

        self.flush()

        logger.info(
            "fsma_batch_emitted",
            success=success,
            failures=failures,
            topic=self.topic_fsma,
        )

        return success, failures

    def _send(self, topic: str, key: str, value: dict) -> bool:
        """Send a message to Kafka.

        Args:
            topic: Kafka topic
            key: Message key (used for partitioning)
            value: Message value (dict, will be JSON serialized)

        Returns:
            True if sent successfully
        """
        try:
            producer = self._get_producer()
            # Attach correlation_id / tenant_id as Kafka headers so consumers
            # can stitch spans back to the originating request (#1318).
            headers = inject_correlation_headers_tuples()
            future = producer.send(topic, key=key, value=value, headers=headers)
            # Don't block here - let caller flush if needed
            return True

        except KafkaError as e:
            logger.error(
                "kafka_send_failed",
                topic=topic,
                key=key,
                error=str(e),
            )
            return False

        except Exception as e:
            logger.error(
                "kafka_send_exception",
                topic=topic,
                key=key,
                error=str(e),
            )
            return False

    def flush(self, timeout: int = 30) -> None:
        """Flush all pending messages.

        Args:
            timeout: Maximum time to wait in seconds
        """
        if self._producer:
            try:
                self._producer.flush(timeout=timeout)
            except Exception as e:
                logger.error("kafka_flush_failed", error=str(e))

    def close(self) -> None:
        """Close the producer connection."""
        if self._producer:
            try:
                self._producer.flush(timeout=10)
                self._producer.close(timeout=10)
                self._producer = None
                self._initialized = False
                logger.info("kafka_producer_closed")
            except Exception as e:
                logger.error("kafka_close_failed", error=str(e))

    def is_healthy(self) -> bool:
        """Check if Kafka connection is healthy."""
        try:
            producer = self._get_producer()
            # Check if connected to at least one broker
            return bool(producer.bootstrap_connected())
        except Exception:
            logger.debug("Kafka health check failed", exc_info=True)
            return False


# Singleton instance
_producer_instance: Optional[KafkaEventProducer] = None


def get_kafka_producer() -> KafkaEventProducer:
    """Get the singleton Kafka producer instance."""
    global _producer_instance
    if _producer_instance is None:
        _producer_instance = KafkaEventProducer()
    return _producer_instance
