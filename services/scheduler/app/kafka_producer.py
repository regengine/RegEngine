"""Kafka producer for emitting enforcement events."""

from __future__ import annotations

import json
import threading
from functools import lru_cache
from typing import Optional

import structlog
from shared.kafka_auth import KafkaAuthError, sign_event
from shared.kafka_compat import KafkaError, KafkaProducerCompat as KafkaProducerLib
from shared.observability.kafka_propagation import inject_correlation_headers_tuples

from .config import get_settings
from .models import AlertEvent, EnforcementItem

logger = structlog.get_logger("kafka_producer")

# Producer identity for HMAC signing. Must be a key of
# shared.kafka_auth._PRODUCER_KEY_ENV_MAP (which resolves the per-service
# signing secret) and must appear in whatever per-topic allowlist a consumer
# configures via KAFKA_ALLOWED_PRODUCERS_<TOPIC> (#2190).
PRODUCER_SERVICE = "scheduler-service"


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
        # #2711: async delivery failures observed via send-future errbacks.
        # Reconciled into (success, failures) after flush() by the batch
        # emitters — local ENQUEUE success is not delivery success.
        # Keyed by topic so a batch spanning two topics (enforcement +
        # alerts) reconciles each topic's failures on its own; an alert
        # delivery failure must not move the enforcement ack gate.
        self._delivery_failures: dict[str, int] = {}
        self._delivery_lock = threading.Lock()

    def _note_delivery_failure(self, topic: str, exc: BaseException) -> None:
        """Errback for send futures: count + log an async delivery failure."""
        with self._delivery_lock:
            self._delivery_failures[topic] = self._delivery_failures.get(topic, 0) + 1
        logger.error(
            "kafka_delivery_failed",
            topic=topic,
            error=str(exc),
        )

    def take_delivery_failures(self, topic: Optional[str] = None) -> int:
        """Return and reset the async delivery-failure count (post-flush).

        With a topic, only that topic's failures are returned and cleared;
        without one, the total across all topics is returned and everything
        is cleared (the pre-existing behavior batch emitters relied on).
        """
        with self._delivery_lock:
            if topic is None:
                count = sum(self._delivery_failures.values())
                self._delivery_failures.clear()
                return count
            return self._delivery_failures.pop(topic, 0)

    def _get_producer(self) -> KafkaProducerLib:
        """Get or create Kafka producer.

        Hardened config (#1147):
        - ``acks="all"``: wait for all in-sync replicas
        - ``retries=10`` (was 3) and ``retry_backoff_ms=500`` for
          exponential-ish backoff on transient broker errors
        - ``max_in_flight_requests_per_connection=5`` (was 1)
        - ``request_timeout_ms=30000``

        Ordering (#2977): librdkafka preserves produce order across retries
        only when ``enable_idempotence`` is on — ``acks=all`` plus
        ``retries>0`` alone does NOT give per-partition ordering, and until
        #2977 the in-flight limit was silently discarded by the compat layer,
        leaving librdkafka's default of 1000000. With idempotence enabled
        librdkafka enforces ``acks=all``, ``max.in.flight<=5`` and
        ``queuing.strategy=fifo``, which is exactly what the values above ask
        for, so each event key stays ordered per partition and retries cannot
        duplicate a record. The cost is a hard cap of 5 in-flight requests per
        connection (peak per-connection throughput) and a mandatory wait for
        all in-sync replicas.
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
                    enable_idempotence=True,  # #2977 — what actually orders
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

        Signed via :func:`shared.kafka_auth.sign_event` to mirror the
        ``emit_fsma_event`` pattern (#2190 / RE-SEC-002). Producer-side
        signing parity pre-empts a DLQ storm if a strict consumer is
        wired up later, and removes the cross-tenant injection vector
        that signing is designed to prevent. Add
        ``KAFKA_ALLOWED_PRODUCERS_ENFORCEMENT_CHANGES`` on the consumer
        side when one is introduced.

        Args:
            item: The enforcement item to emit

        Returns:
            True if sent successfully, False otherwise
        """
        event = AlertEvent(
            source_type=item.source_type,
            item=item,
        )
        event_dict = event.to_kafka_dict()
        base_headers = inject_correlation_headers_tuples()
        try:
            signed_payload, signed_headers = sign_event(
                event_dict,
                producer_service=PRODUCER_SERVICE,
                existing_headers=base_headers,
            )
        except KafkaAuthError as exc:
            logger.error(
                "enforcement_change_sign_failed",
                source_id=item.source_id,
                reason=exc.reason,
                topic=self.topic_enforcement,
            )
            return False

        return self._send(
            topic=self.topic_enforcement,
            key=item.source_id,
            value=signed_payload,
            headers=signed_headers,
        )

    def emit_high_priority_alert(self, item: EnforcementItem) -> bool:
        """Emit a high-priority alert for CRITICAL/HIGH severity items.

        Signed via :func:`shared.kafka_auth.sign_event` for the same
        producer-parity reasons documented on
        :meth:`emit_enforcement_change` (#2190 / RE-SEC-002). Add
        ``KAFKA_ALLOWED_PRODUCERS_ALERTS_HIGH_PRIORITY`` on the consumer
        side when one is introduced.

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
        event_dict = event.to_kafka_dict()
        base_headers = inject_correlation_headers_tuples()
        try:
            signed_payload, signed_headers = sign_event(
                event_dict,
                producer_service=PRODUCER_SERVICE,
                existing_headers=base_headers,
            )
        except KafkaAuthError as exc:
            logger.error(
                "high_priority_alert_sign_failed",
                source_id=item.source_id,
                reason=exc.reason,
                topic=self.topic_alerts,
            )
            return False

        return self._send(
            topic=self.topic_alerts,
            key=item.source_id,
            value=signed_payload,
            headers=signed_headers,
        )

    def emit_batch(self, items: list[EnforcementItem]) -> tuple[int, int]:
        """Emit a batch of enforcement items.

        The returned counts cover the enforcement topic only: alert sends
        share this flush window, but their failures are reconciled against
        the alerts topic and reported via logs, so a failing alert can
        neither withhold the enforcement seen-ack nor pass as an
        enforcement failure.

        Returns:
            Tuple of (success_count, failure_count)
        """
        success = 0
        failures = 0
        alert_enqueue_failures = 0

        for item in items:
            # Emit to enforcement.changes
            if self.emit_enforcement_change(item):
                success += 1
            else:
                failures += 1

            # Also emit high-priority alerts
            if item.severity.value in ["critical", "high"]:
                if not self.emit_high_priority_alert(item):
                    alert_enqueue_failures += 1

        # Flush to ensure all messages are sent
        self.flush()

        # #2711: reconcile async delivery failures surfaced during flush —
        # enqueue success is not delivery success. Reconciled per topic:
        # only enforcement-topic failures (plus a flush-level timeout,
        # which leaves enforcement delivery unknown) move the enforcement
        # counts that gate the seen-ack in services/scheduler/service.py.
        undelivered = self.take_delivery_failures(self.topic_enforcement)
        undelivered += self.take_delivery_failures("<flush>")
        if undelivered:
            failures += undelivered
            success = max(0, success - undelivered)

        # Alert-topic failures belong to the alerts sends, not to the
        # enforcement batch: surface them loudly without touching the
        # counts above.
        alert_undelivered = self.take_delivery_failures(self.topic_alerts)
        if alert_enqueue_failures or alert_undelivered:
            logger.error(
                "alert_batch_delivery_failures",
                enqueue_failures=alert_enqueue_failures,
                delivery_failures=alert_undelivered,
                topic=self.topic_alerts,
            )

        return success, failures

    def emit_fsma_event(self, fsma_event: dict) -> bool:
        """Emit an FSMA trace event for graph ingestion.

        Events are HMAC-signed here via ``shared.kafka_auth.sign_event``
        before publish (#2190).

        No consumer currently subscribes to this topic. The graph-side
        consumer that used to verify these signatures was removed, so
        nothing verifies, DLQ-routes or otherwise acts on what is published
        here today; messages accumulate until Kafka retention drops them.
        Signing is retained so the envelope contract stays valid for a
        future consumer. ``shared.kafka_auth.verify_event`` is the function
        such a consumer would call — its only production caller today is
        services/admin/app/review_consumer.py, on a different topic.
        """
        event_id = fsma_event.get("event_id", "unknown")
        base_headers = inject_correlation_headers_tuples()
        try:
            signed_payload, signed_headers = sign_event(
                fsma_event,
                producer_service=PRODUCER_SERVICE,
                existing_headers=base_headers,
            )
        except KafkaAuthError as exc:
            logger.error(
                "fsma_event_sign_failed",
                event_id=event_id,
                reason=exc.reason,
                topic=self.topic_fsma,
            )
            return False

        return self._send(
            topic=self.topic_fsma,
            key=event_id,
            value=signed_payload,
            headers=signed_headers,
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

        # #2711: reconcile async delivery failures surfaced during flush.
        undelivered = self.take_delivery_failures()
        if undelivered:
            failures += undelivered
            success = max(0, success - undelivered)

        logger.info(
            "fsma_batch_emitted",
            success=success,
            failures=failures,
            topic=self.topic_fsma,
        )

        return success, failures

    def _send(
        self,
        topic: str,
        key: str,
        value: dict,
        headers: Optional[list[tuple[str, bytes]]] = None,
    ) -> bool:
        """Send a message to Kafka.

        ``headers`` may be passed pre-built by callers that already
        attached signing/correlation headers (e.g. emit_fsma_event). When
        None, correlation headers are attached by default.

        KNOWN GAP (#2697, deferred): True here means locally ENQUEUED, not
        delivered — async delivery failures surface only via flush() logs,
        and callers ack on this return value. The kafka backbone is
        non-default in prod (pg mode is the default seen-ack path); fixing
        the ack semantics means checking the send future per message and is
        deferred until the kafka path is production-default.
        """
        try:
            producer = self._get_producer()
            if headers is None:
                # Attach correlation_id / tenant_id as Kafka headers so
                # consumers can stitch spans back to the originating
                # request (#1318).
                headers = inject_correlation_headers_tuples()
            future = producer.send(topic, key=key, value=value, headers=headers)
            # Don't block here - let caller flush if needed. Async delivery
            # failures surface via the errback and are reconciled by the
            # batch emitters after flush() (#2711).
            #
            # #2969: this used to sit inside `except Exception: pass`, which
            # swallowed the AttributeError raised on every send while
            # KafkaProducerCompat.send() returned None — the whole #2711 fix
            # was dead code for the life of the fix. A producer that yields no
            # delivery handle is now a FAILED send (caught below), never a
            # silent success.
            future.add_errback(lambda exc, t=topic: self._note_delivery_failure(t, exc))
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

        A flush that times out means messages are still buffered and
        UNACKNOWLEDGED. #2969: that used to be logged and discarded, so the
        batch emitters reconciled against a zero failure count and reported a
        broker-side loss as complete success. It now counts as a delivery
        failure, which is what ``services/scheduler/service.py`` reads when it
        decides whether items are safe to mark seen.

        Args:
            timeout: Maximum time to wait in seconds
        """
        if self._producer:
            try:
                self._producer.flush(timeout=timeout)
            except Exception as e:
                self._note_delivery_failure("<flush>", e)
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
