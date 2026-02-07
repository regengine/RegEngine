"""Kafka consumer that ingests low-confidence extractions and records them via HallucinationTracker."""

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
from kafka import KafkaConsumer, KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
from prometheus_client import Counter, Histogram
from tenacity import retry, stop_after_attempt, wait_exponential

# Add shared module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from .config import get_settings
from .metrics import get_hallucination_tracker

logger = structlog.get_logger("review-consumer")

REVIEW_MESSAGES_COUNTER = Counter(
    "review_messages_total",
    "Review queue messages processed",
    ["status"],
)

REVIEW_LATENCY_HISTOGRAM = Histogram(
    "review_message_latency_seconds",
    "Time to process review messages",
    ["outcome"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

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
    except Exception as exc:  # pragma: no cover - infra dependent
        logger.warning("topic_creation_failed", topic=topic, error=str(exc))
    finally:
        if admin is not None:
            try:
                admin.close()
            except Exception as cleanup_exc:  # pragma: no cover
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


def _send_to_dlq(bootstrap: str, event: Dict[str, Any], error: str) -> None:
    """Send failed message to dead letter queue."""
    try:
        producer = _get_dlq_producer(bootstrap)
        dlq_payload = {
            "original_event": event,
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        producer.send(TOPIC_DLQ, value=dlq_payload)
        producer.flush(timeout=5.0)
        logger.info("message_sent_to_dlq", error=error)
    except Exception as exc:  # pragma: no cover - infra dependent
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
    """Clean up DLQ producer (called from consumer loop on shutdown)."""
    global _dlq_producer
    with _dlq_producer_lock:
        if _dlq_producer is not None:
            try:
                _dlq_producer.close(timeout=2.0)
            except Exception as cleanup_exc:  # pragma: no cover
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
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        group_id="admin-review-consumer",
    )

    tracker = get_hallucination_tracker()
    _consumer_started_at = datetime.now(timezone.utc)
    logger.info("review_consumer_started", topic=TOPIC_NEEDS_REVIEW)

    while not _shutdown_event.is_set():
        messages = consumer.poll(timeout_ms=500)
        _last_poll_time = datetime.now(timezone.utc)
        if not messages:
            continue

        for records in messages.values():
            for record in records:
                _process_record(record, tracker, bootstrap)

        consumer.commit()  # commit once per poll batch

    _cleanup_dlq_producer()
    consumer.close()
    logger.info("review_consumer_stopped")


def _process_record(record, tracker: "HallucinationTracker", bootstrap: str) -> None:
    """Process a single Kafka record."""
    evt = record.value
    start_time = time.perf_counter()
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
    except Exception as exc:  # pragma: no cover - depends on data shape
        elapsed = time.perf_counter() - start_time
        REVIEW_LATENCY_HISTOGRAM.labels(outcome="error").observe(elapsed)
        logger.exception("review_consumer_error", error=str(exc), event=evt)
        REVIEW_MESSAGES_COUNTER.labels(status="error").inc()
        _send_to_dlq(bootstrap, evt, str(exc))


def _extract_and_record(evt: Dict[str, Any], tracker) -> Dict[str, Any]:
    """Extract fields from event and record via tracker."""
    tenant_id = evt.get("tenant_id")
    document_id = evt.get("document_id")
    extraction = evt.get("extraction") or {}
    doc_hash = (
        evt.get("doc_hash")
        or extraction.get("attributes", {}).get("doc_hash")
        or document_id
        or "unknown"
    )
    extractor = extraction.get("attributes", {}).get("extractor") or "unknown"
    confidence_score = extraction.get("confidence_score", 0.0)
    source_text = extraction.get("source_text")
    provenance = extraction.get("attributes", {})

    return _record_with_retry(
        tracker,
        tenant_id=str(tenant_id) if tenant_id else None,
        document_id=document_id or "unknown",
        doc_hash=doc_hash,
        extractor=extractor,
        confidence_score=confidence_score,
        extraction=extraction,
        provenance=provenance,
        text_raw=source_text,
    )


if __name__ == "__main__":
    run_consumer()
