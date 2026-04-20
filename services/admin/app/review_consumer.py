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

import hashlib
import hmac
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
from opentelemetry import trace, propagate
from prometheus_client import Counter, Histogram
from kafka import KafkaConsumer, KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    REVIEW_MESSAGES_COUNTER = Counter(
        "review_messages_total", "Review queue messages processed", ["status"]
    )
    POISON_PILL_COUNTER = Counter(
        "review_poison_pill_total", "Count of malformed review messages"
    )
except ValueError:
    from prometheus_client import REGISTRY

    REVIEW_MESSAGES_COUNTER = REGISTRY._names_to_collectors.get("review_messages_total")
    POISON_PILL_COUNTER = REGISTRY._names_to_collectors.get("review_poison_pill_total")

# Standardized path discovery via shared utility
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.observability import setup_standalone_observability
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
_dlq_producer: Optional[KafkaProducer] = None
_dlq_producer_lock = threading.Lock()


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


def _get_dlq_producer(bootstrap: str) -> KafkaProducer:
    """Get or create DLQ producer (thread-safe singleton)."""
    global _dlq_producer
    if _dlq_producer is None:
        with _dlq_producer_lock:
            if _dlq_producer is None:
                _dlq_producer = KafkaProducer(
                    bootstrap_servers=bootstrap,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                )
    return _dlq_producer


def _send_to_dlq(bootstrap: str, event: any, error: str, headers: list | None = None) -> None:
    """Send failed message to dead letter queue."""
    try:
        producer = _get_dlq_producer(bootstrap)
        if isinstance(event, dict):
            dlq_payload = {
                "original_event": event,
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            dlq_payload = {
                "raw_payload": str(event),
                "error": error,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "is_poison_pill": True,
            }
        producer.send(TOPIC_DLQ, value=dlq_payload, headers=headers or [])
        producer.flush(timeout=5.0)
        logger.info("message_sent_to_dlq", error=error)
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:  # pragma: no cover - infra dependent
        logger.error("dlq_send_failed", error=str(exc))


from sqlalchemy.exc import OperationalError, InterfaceError
from tenacity import retry_if_exception_type


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    retry=retry_if_exception_type((OperationalError, InterfaceError, ConnectionError, TimeoutError)),
    reraise=True,
)
def _record_with_retry(tracker: "HallucinationTracker", **kwargs) -> Dict[str, Any]:
    """Record hallucination with retry logic for transient DB/connection errors only."""
    return tracker.record_hallucination(**kwargs)


def stop_consumer() -> None:
    """Signal the consumer loop to shut down gracefully.
    
    The consumer loop will finish processing current batch before exiting.
    DLQ producer cleanup happens in the consumer loop itself.
    """
    _shutdown_event.set()


def _cleanup_dlq_producer() -> None:
    """Flush then close the DLQ producer on shutdown (#1220).

    librdkafka buffers ``send()`` calls asynchronously, so ``close()``
    alone can drop in-flight DLQ messages on SIGTERM. We flush first to
    drain the buffer (up to 5s) and only then close. Exceptions during
    flush are logged but never re-raised -- we still want close() to
    run and the shutdown path to complete even if the broker is
    unreachable.
    """
    global _dlq_producer
    with _dlq_producer_lock:
        if _dlq_producer is not None:
            try:
                _dlq_producer.flush(timeout=5.0)
                logger.info("dlq_producer_flushed_on_shutdown")
            except Exception as flush_exc:  # pragma: no cover - infra
                logger.exception(
                    "dlq_flush_on_shutdown_failed",
                    error=str(flush_exc),
                )
            try:
                _dlq_producer.close(timeout=2.0)
            except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as cleanup_exc:  # pragma: no cover
                logger.debug("dlq_producer_close_failed", error=str(cleanup_exc))
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
                            attributes={"kafka.topic": record.topic, "kafka.offset": record.offset}
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
    
    # 1. Handle Deserialization (Poison Pill Detection)
    try:
        evt = json.loads(raw_value.decode("utf-8")) if raw_value else {}
    except (AttributeError, TypeError, ValueError, UnicodeDecodeError) as exc:
        logger.error("poison_pill_detected", error=str(exc), offset=record.offset)
        POISON_PILL_COUNTER.inc()
        _send_to_dlq(bootstrap, raw_value, f"Deserialization failed: {str(exc)}", headers=kafka_headers)
        return

    try:
        result = _extract_and_record(evt, tracker)
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
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError, LookupError) as exc:  # pragma: no cover - depends on data shape
        elapsed = time.perf_counter() - start_time
        REVIEW_LATENCY_HISTOGRAM.labels(outcome="error").observe(elapsed)
        logger.exception("review_consumer_error", error=str(exc), event=evt)
        REVIEW_MESSAGES_COUNTER.labels(status="error").inc()
        _send_to_dlq(bootstrap, evt, str(exc), headers=kafka_headers)


def _verify_hmac_envelope(evt: Dict[str, Any]) -> bool:
    """Verify HMAC signature on an NLP->review event envelope.

    Expected envelope shape:
        {
          "payload": {... original review event ...},
          "hmac": "<hex digest>"
        }

    The signature is HMAC-SHA256 over the canonical JSON of
    ``payload`` keyed with ``NLP_REVIEW_HMAC_SECRET``. Messages that do
    not match the expected envelope shape, or where the digest does not
    verify, return False -- the caller sends them to the DLQ.

    If ``NLP_REVIEW_HMAC_SECRET`` is unset we return True (legacy
    mode) but log a warning; set this env var in production to enforce
    signing.
    """
    secret = os.getenv("NLP_REVIEW_HMAC_SECRET", "").strip()
    if not secret:
        logger.warning(
            "review_consumer_hmac_secret_unset",
            topic=TOPIC_NEEDS_REVIEW,
            note=(
                "NLP_REVIEW_HMAC_SECRET is not configured; "
                "Kafka message envelopes are not being verified. Unsigned "
                "events can inject cross-tenant review items (#1388)."
            ),
        )
        return True

    if not isinstance(evt, dict):
        return False
    payload = evt.get("payload")
    sig = evt.get("hmac")
    if not isinstance(payload, dict) or not isinstance(sig, str):
        return False

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    expected = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def _extract_and_record(evt: Dict[str, Any], tracker) -> Dict[str, Any]:
    """Extract fields from event and record via tracker.

    Hardening (#1388):
    - When ``NLP_REVIEW_HMAC_SECRET`` is configured, the event must be
      a signed envelope ``{payload, hmac}``. Unsigned or tampered
      messages raise ``ValueError`` so ``_process_record`` routes them
      to the DLQ.
    - tenant_id is read from the inner ``payload`` of the verified
      envelope. If the legacy bare-event path is used (no secret), we
      still accept the event body directly -- but only after emitting
      the ``review_consumer_hmac_secret_unset`` warning above.

    Hardening (#1390):
    - source_text is escaped via ``sanitize_source_text_for_store``
      before insert. The DB stores the sanitized text so a later
      unsanitized read path cannot leak stored XSS into the admin UI.
    """
    # --- Envelope verification ------------------------------------------
    if not _verify_hmac_envelope(evt):
        raise ValueError(
            "review envelope failed HMAC verification -- "
            "message rejected and routed to DLQ"
        )

    # Extract the inner payload if this is a signed envelope; otherwise
    # fall back to treating the whole event as the payload (legacy).
    if isinstance(evt, dict) and "payload" in evt and "hmac" in evt:
        payload = evt["payload"]
    else:
        payload = evt

    tenant_id = payload.get("tenant_id")
    document_id = payload.get("document_id")
    extraction = payload.get("extraction") or {}
    doc_hash = (
        payload.get("doc_hash")
        or extraction.get("attributes", {}).get("doc_hash")
        or document_id
        or "unknown"
    )
    extractor = extraction.get("attributes", {}).get("extractor") or "unknown"
    confidence_score = extraction.get("confidence_score", 0.0)
    source_text_raw = extraction.get("source_text")
    provenance = extraction.get("attributes", {})

    # Sanitize source_text before DB store (#1390).
    from .text_sanitize import sanitize_source_text_for_store

    sanitized_text = sanitize_source_text_for_store(source_text_raw)

    # Also rewrite the source_text field inside the extraction dict so
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
        text_raw=sanitized_text,
    )


if __name__ == "__main__":
    run_consumer()
