# DEPRECATED: will be removed once EVENT_BACKBONE=pg is default (see #1159 #1240).
# The PostgreSQL task_processor (server/workers/task_processor.py) is the canonical
# replacement for this Kafka consumer. Do not add new logic here.
"""Kafka consumer that ingests low-confidence extractions and records them via HallucinationTracker.

Security hardening:
- tenant_id from a Kafka message body is NOT trusted (#1388). When an
  HMAC signing secret is configured via the ``NLP_REVIEW_HMAC_SECRET``
  env var, we require each message to carry an ``hmac`` envelope
  computed over the canonical payload. Messages without a valid HMAC
  are routed to the DLQ. When no secret is configured (local dev), we
  fall back to the legacy behavior but warn loudly on every message
  so the missing envelope gate is visible in production logs.
- source_text is HTML-escaped before DB store (#1390) so that stored
  XSS via malicious supplier documents cannot propagate into the
  admin UI.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .metrics import HallucinationTracker

import structlog
from confluent_kafka.admin import NewTopic
from opentelemetry import propagate, trace
from prometheus_client import Counter, Histogram
from shared.kafka_compat import (
    KafkaAdminClientCompat as KafkaAdminClient,
    KafkaConsumerCompat as KafkaConsumer,
    TopicAlreadyExistsError,
)
from tenacity import retry, stop_after_attempt, stop_after_delay, wait_exponential

try:
    REVIEW_MESSAGES_COUNTER = Counter("review_messages_total", "Review queue messages processed", ["status"])
    POISON_PILL_COUNTER = Counter("review_poison_pill_total", "Count of malformed review messages")
except ValueError:
    from prometheus_client import REGISTRY

    REVIEW_MESSAGES_COUNTER = REGISTRY._names_to_collectors.get("review_messages_total")
    POISON_PILL_COUNTER = REGISTRY._names_to_collectors.get("review_poison_pill_total")

# Standardized path discovery via shared utility
from shared.paths import ensure_shared_importable

ensure_shared_importable()

from shared.kafka_auth import KafkaAuthError, get_allowed_producers, verify_event
from shared.observability import setup_standalone_observability
from shared.observability.dlq_producer import DLQProducer, get_dlq_producer
from shared.observability.kafka_propagation import (
    bind_correlation_context,
    inject_correlation_headers_tuples,
)

tracer = setup_standalone_observability("admin-review-consumer")

from .config import get_settings
from .metrics import get_hallucination_tracker

logger = structlog.get_logger("review-consumer")


def _get_or_create_review_histogram() -> Histogram:
    """Create the review-latency histogram once, even when this module
    is imported twice under different absolute paths (``app.review_consumer``
    vs ``services.admin.app.review_consumer``) — a configuration that
    happens in the test suite and blows up the default Prometheus
    registry with a ``Duplicated timeseries`` error.
    """
    try:
        return Histogram(
            "review_message_latency_seconds",
            "Time to process review messages",
            ["outcome"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )
    except ValueError:
        # Already registered by an earlier import path. Reuse the
        # existing collector so both imports refer to the same
        # histogram.
        from prometheus_client import REGISTRY

        for collector in list(REGISTRY._collector_to_names.keys()):
            if getattr(collector, "_name", None) == "review_message_latency_seconds":
                return collector  # type: ignore[return-value]
        raise


REVIEW_LATENCY_HISTOGRAM = _get_or_create_review_histogram()

TOPIC_NEEDS_REVIEW = "nlp.needs_review"
TOPIC_DLQ = "nlp.needs_review.dlq"

_shutdown_event = threading.Event()
_last_poll_time: Optional[datetime] = None
_consumer_started_at: Optional[datetime] = None
# DLQ producer — shared singleton (#1228)
_dlq_producer: Optional[DLQProducer] = None


def _ensure_topic(topic: str, bootstrap_servers: str) -> None:
    admin = None
    try:
        admin = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
        admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
        logger.info("topic_created", topic=topic)
    except TopicAlreadyExistsError:
        pass
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:  # pragma: no cover - infra dependent
        logger.warning("topic_creation_failed", topic=topic, error=str(exc))
    finally:
        if admin is not None:
            try:
                admin.close()
            except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as cleanup_exc:  # pragma: no cover
                logger.debug("admin_client_close_failed", error=str(cleanup_exc))


def _init_dlq_producer(bootstrap: str) -> DLQProducer:
    """Get or create the shared DLQ producer singleton (#1228)."""
    global _dlq_producer
    _dlq_producer = get_dlq_producer(
        topic=TOPIC_DLQ,
        bootstrap_servers=bootstrap,
        service_name="admin-review-consumer",
    )
    return _dlq_producer


def _send_to_dlq(bootstrap: str, event: Any, error: str, headers: list | None = None) -> None:
    """Send failed message to dead letter queue."""
    producer = _dlq_producer or _init_dlq_producer(bootstrap)
    try:
        if isinstance(event, dict):
            dlq_payload = json.dumps(
                {
                    "original_event": event,
                    "error": error,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
            ).encode("utf-8")
        else:
            dlq_payload = json.dumps(
                {
                    "raw_payload": str(event),
                    "error": error,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                    "is_poison_pill": True,
                }
            ).encode("utf-8")
        producer.send(dlq_payload, reason=error[:120], headers=headers or [])
        logger.info("message_sent_to_dlq", error=error)
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:  # pragma: no cover - infra dependent
        logger.error("dlq_send_failed", error=str(exc))


from sqlalchemy.exc import InterfaceError, OperationalError
from tenacity import retry_if_exception_type

# Total retry budget, capped well below the Kafka consumer group
# ``max.poll.interval.ms`` (default 300s) so a persistently-failing
# downstream call never blocks a poll long enough to trigger a
# rebalance (#1201). Without a wall-clock cap, an unbounded exponential
# backoff + attempt count can exceed the broker's rebalance timeout and
# cause a death spiral where each kick-out makes the next poll slower.
REVIEW_CONSUMER_RETRY_MAX_WAIT_SECONDS = float(os.getenv("REVIEW_CONSUMER_RETRY_MAX_WAIT_SECONDS", "60"))


@retry(
    stop=(stop_after_attempt(3) | stop_after_delay(REVIEW_CONSUMER_RETRY_MAX_WAIT_SECONDS)),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    retry=retry_if_exception_type((OperationalError, InterfaceError, ConnectionError, TimeoutError)),
    reraise=True,
)
def _record_with_retry(tracker: "HallucinationTracker", **kwargs) -> Dict[str, Any]:
    """Record hallucination with retry logic for transient DB/connection errors only.

    Retries stop at whichever limit fires first: ``stop_after_attempt(3)``
    OR ``stop_after_delay(REVIEW_CONSUMER_RETRY_MAX_WAIT_SECONDS)`` (#1201).
    On exhaustion the last exception is re-raised and ``_process_record``
    routes the message to the DLQ, commits the offset, and continues
    polling -- so a persistent downstream outage cannot starve the
    consumer past the broker's rebalance timeout.
    """
    return tracker.record_hallucination(**kwargs)


def stop_consumer() -> None:
    """Signal the consumer loop to shut down gracefully.

    The consumer loop will finish processing current batch before exiting.
    DLQ producer cleanup happens in the consumer loop itself.
    """
    _shutdown_event.set()


def _cleanup_dlq_producer() -> None:
    """Flush then close the shared DLQ producer on shutdown (#1228).

    Flush is called explicitly before close so shutdown ordering stays visible
    to the tests and mirrors the graph consumer behavior.
    """
    global _dlq_producer
    if _dlq_producer is not None:
        try:
            _dlq_producer.flush(timeout=2.0)
        except Exception as exc:  # pragma: no cover - infra
            logger.exception("dlq_flush_on_shutdown_failed", error=str(exc))
        try:
            _dlq_producer.close()
            logger.info("dlq_producer_flushed_on_shutdown")
        except Exception as exc:  # pragma: no cover - infra
            logger.exception("dlq_close_on_shutdown_failed", error=str(exc))
        _dlq_producer = None


# Configurable staleness threshold (seconds)
CONSUMER_STALE_THRESHOLD_SECONDS = int(os.getenv("CONSUMER_STALE_THRESHOLD_SECONDS", "30"))


def get_consumer_health() -> Dict[str, Any]:
    """Return consumer health status for monitoring endpoints."""
    now = datetime.now(timezone.utc)
    is_alive = not _shutdown_event.is_set()
    last_poll = _last_poll_time.isoformat() if _last_poll_time else None
    started_at = _consumer_started_at.isoformat() if _consumer_started_at else None

    # Consider unhealthy if no poll in threshold period
    poll_stale = False
    seconds_since_poll = None
    if _last_poll_time and is_alive:
        seconds_since_poll = (now - _last_poll_time).total_seconds()
        poll_stale = seconds_since_poll > CONSUMER_STALE_THRESHOLD_SECONDS

    return {
        "alive": is_alive,
        "started_at": started_at,
        "last_poll_at": last_poll,
        "seconds_since_poll": seconds_since_poll,
        "poll_stale": poll_stale,
        "healthy": is_alive and not poll_stale,
    }


def run_consumer() -> None:
    """Main consumer loop that reads from nlp.needs_review and persists via tracker."""
    global _last_poll_time, _consumer_started_at

    settings = get_settings()
    bootstrap = settings.kafka_bootstrap

    _ensure_topic(TOPIC_NEEDS_REVIEW, bootstrap)
    _ensure_topic(TOPIC_DLQ, bootstrap)

    consumer = KafkaConsumer(
        TOPIC_NEEDS_REVIEW,
        bootstrap_servers=bootstrap,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        group_id=settings.consumer_group_id,
    )

    tracker = get_hallucination_tracker()
    _consumer_started_at = datetime.now(timezone.utc)
    logger.info("review_consumer_started", topic=TOPIC_NEEDS_REVIEW)

    try:
        while not _shutdown_event.is_set():
            messages = consumer.poll(timeout_ms=500)
            _last_poll_time = datetime.now(timezone.utc)
            if not messages:
                continue

            for records in messages.values():
                for record in records:
                    # Re-hydrate correlation/tenant contextvars from inbound headers
                    # so every log record during handler execution carries the
                    # originator's trace ID (#1318).
                    with bind_correlation_context(record.headers or []):
                        with tracer.start_as_current_span(
                            "admin_review.process_message",
                            attributes={"kafka.topic": record.topic, "kafka.offset": record.offset},
                        ) as span:
                            # Propagate trace + correlation context to DLQ headers.
                            otel_headers: list = []
                            propagate.inject(otel_headers)
                            merged = [(k, v.encode("utf-8")) for k, v in otel_headers]
                            kafka_headers = inject_correlation_headers_tuples(existing=merged)

                            _process_record(record, tracker, bootstrap, kafka_headers)

            consumer.commit()  # commit once per poll batch
    finally:
        # #1220 — flush DLQ producer before close so buffered DLQ
        # messages (compliance-critical evidence of review failures)
        # are delivered even when the loop exits via SIGTERM or
        # unhandled exception rather than a clean shutdown_event.
        _cleanup_dlq_producer()
        try:
            consumer.close()
        except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as close_exc:  # pragma: no cover
            logger.warning("consumer_close_error", error=str(close_exc))
        logger.info("review_consumer_stopped")


def _process_record(record, tracker: "HallucinationTracker", bootstrap: str, kafka_headers: list) -> None:
    """Process a single Kafka record."""
    raw_value = record.value
    start_time = time.perf_counter()
    topic_name = getattr(record, "topic", TOPIC_NEEDS_REVIEW)
    if callable(topic_name):
        try:
            topic_name = topic_name()
        except Exception:
            topic_name = TOPIC_NEEDS_REVIEW
    raw_headers = getattr(record, "headers", None)
    if callable(raw_headers):
        try:
            raw_headers = raw_headers()
        except Exception:
            raw_headers = None

    # 1. Handle Deserialization (Poison Pill Detection)
    try:
        evt = json.loads(raw_value.decode("utf-8")) if raw_value else {}
    except (AttributeError, TypeError, ValueError, UnicodeDecodeError) as exc:
        logger.error("poison_pill_detected", error=str(exc), offset=record.offset)
        POISON_PILL_COUNTER.inc()
        _send_to_dlq(bootstrap, raw_value, f"Deserialization failed: {str(exc)}", headers=kafka_headers)
        return

    try:
        result = _extract_and_record(
            evt,
            tracker,
            headers=raw_headers if isinstance(raw_headers, list) else None,
            topic=str(topic_name or TOPIC_NEEDS_REVIEW),
        )
        elapsed = time.perf_counter() - start_time
        REVIEW_LATENCY_HISTOGRAM.labels(outcome="success").observe(elapsed)
        REVIEW_MESSAGES_COUNTER.labels(status="success").inc()
        logger.info(
            "hallucination_recorded_from_queue",
            document_id=result.get("document_id"),
            confidence=result.get("confidence_score"),
            extractor=result.get("extractor"),
            latency_ms=round(elapsed * 1000, 2),
        )
    except (
        AttributeError,
        TypeError,
        ValueError,
        RuntimeError,
        OSError,
        KeyError,
        LookupError,
        KafkaAuthError,
        # SQLAlchemy errors surface here when _record_with_retry exhausts
        # its retry budget (#1201). Without this clause, a persistent DB
        # outage would crash the consumer loop instead of DLQ'ing the
        # message and moving on.
        OperationalError,
        InterfaceError,
    ) as exc:  # pragma: no cover - depends on data shape
        elapsed = time.perf_counter() - start_time
        REVIEW_LATENCY_HISTOGRAM.labels(outcome="error").observe(elapsed)
        logger.exception("review_consumer_error", error=str(exc), event=evt)
        REVIEW_MESSAGES_COUNTER.labels(status="error").inc()
        _send_to_dlq(bootstrap, evt, str(exc), headers=kafka_headers)


def _is_dev_kafka_auth_bypass() -> bool:
    """Allow unsigned messages only in local/test envs with no signing key.

    This preserves rollout safety for developer machines while failing
    closed everywhere else. Production/staging should never rely on the
    shared verifier's permissive mode implicitly.
    """
    environment = os.getenv("ENVIRONMENT", "").strip().lower()
    signing_key = os.getenv("KAFKA_EVENT_SIGNING_KEY", "").strip()
    return environment in {"development", "dev", "local", "test"} and not signing_key


def _verify_review_event(
    evt: Dict[str, Any],
    headers: list[tuple[str, Any]] | None,
    *,
    topic: str = TOPIC_NEEDS_REVIEW,
) -> Dict[str, Any]:
    """Verify an inbound review event using the shared Kafka auth contract."""
    strict = not _is_dev_kafka_auth_bypass()
    if not strict:
        logger.warning(
            "review_consumer_kafka_auth_dev_bypass",
            topic=topic,
            environment=os.getenv("ENVIRONMENT"),
            note=(
                "Unsigned review events are accepted only because "
                "ENVIRONMENT is local/test and KAFKA_EVENT_SIGNING_KEY is unset. "
                "Do not rely on this bypass outside developer rollout."
            ),
        )

    allowed_producers = get_allowed_producers(topic)
    if allowed_producers is None and topic == TOPIC_NEEDS_REVIEW:
        allowed_producers = {"nlp-service"}

    verified_evt, _verified_producer = verify_event(
        evt,
        headers,
        topic=topic,
        allowed_producers=allowed_producers,
        strict=strict,
    )
    return verified_evt


def _extract_and_record(
    evt: Dict[str, Any],
    tracker,
    *,
    headers: list[tuple[str, Any]] | None = None,
    topic: str = TOPIC_NEEDS_REVIEW,
) -> Dict[str, Any]:
    """Extract fields from event and record via tracker.

    Hardening (#1388):
    - Inbound messages are verified with ``shared.kafka_auth.verify_event``.
      Unsigned, tampered, or unauthorized messages raise
      ``KafkaAuthError`` so ``_process_record`` routes them to the DLQ.
    - A no-key bypass is retained only for local/test environments to
      preserve rollout safety while developers are not running a signed
      Kafka stack. Production/staging must present the canonical signed
      body + Kafka headers emitted by ``sign_event(...)``.

    Hardening (#1390):
    - Store both: the raw ``source_text`` is kept verbatim in the
      ``text_raw`` column (for analytics / model training / audit
      exports), while ``extraction["source_text"]`` holds the copy
      escaped via ``sanitize_source_text_for_store``. Read paths must
      re-sanitize ``text_raw`` via
      ``sanitize_source_text_for_response`` and never return it
      directly, so stored XSS cannot reach the admin UI.
    """
    payload = _verify_review_event(evt, headers, topic=topic)

    tenant_id = payload.get(
        "tenant_id"
    )  # nosemgrep: tenant-id-from-request-body -- payload was authenticated by _verify_review_event via shared.kafka_auth.verify_event
    document_id = payload.get("document_id")
    extraction = payload.get("extraction") or {}
    doc_hash = payload.get("doc_hash") or extraction.get("attributes", {}).get("doc_hash") or document_id or "unknown"
    extractor = extraction.get("attributes", {}).get("extractor") or "unknown"
    confidence_score = extraction.get("confidence_score", 0.0)
    source_text_raw = extraction.get("source_text")
    provenance = extraction.get("attributes", {})

    # Store both (#1390): keep the raw document text verbatim in
    # text_raw for analytics / training / audit exports, and put the
    # sanitized copy in extraction["source_text"] for display readers.
    from .text_sanitize import sanitize_source_text_for_store

    raw_text = "" if source_text_raw is None else str(source_text_raw)
    sanitized_text = sanitize_source_text_for_store(raw_text)

    # Rewrite the source_text field inside the extraction dict so
    # any downstream consumer that reads extraction["source_text"] sees
    # the sanitized value rather than the raw document bytes.
    if isinstance(extraction, dict) and "source_text" in extraction:
        extraction = dict(extraction)
        extraction["source_text"] = sanitized_text

    return _record_with_retry(
        tracker,
        tenant_id=str(tenant_id) if tenant_id else None,
        document_id=document_id or "unknown",
        doc_hash=doc_hash,
        extractor=extractor,
        confidence_score=confidence_score,
        extraction=extraction,
        provenance=provenance,
        text_raw=raw_text,
    )


if __name__ == "__main__":
    run_consumer()
