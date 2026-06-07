"""Dead-letter-queue helpers and FSMA-event detection for the NLP consumer.

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

import structlog

from shared.kafka_compat import (
    KafkaProducerCompat as KafkaProducer,
    KafkaTimeoutError,
)

from ..config import settings

from .constants import TOPIC_DLQ, TOPIC_FSMA_DLQ
from .conversion import _now_iso
from .tenancy import _kafka_key_for, _retry_key_for

logger = structlog.get_logger("nlp-consumer")

# Bounded retry tracker — TTL prevents unbounded growth under partial failures (#994)
try:
    from cachetools import TTLCache
    _retry_counts: dict[str, int] = TTLCache(maxsize=50_000, ttl=3600)  # type: ignore[assignment]
except ImportError:
    _retry_counts: dict[str, int] = {}  # type: ignore[no-redef]


def _send_to_dlq(
    producer: KafkaProducer,
    event: any,
    error: str,
    doc_id: str | None = None,
    headers: list | None = None,
    tenant_id: str | None = None,
) -> None:
    """Send a failed message to the dead letter queue for manual inspection.

    ``tenant_id`` is optional because this path is hit on poison-pill
    and pre-auth failures where tenant resolution has not yet occurred.
    When present it scopes the retry-count lookup (#1122) and the
    Kafka partition key so DLQ'd messages do not collide with healthy
    messages from other tenants.
    """
    try:
        retry_key = _retry_key_for(tenant_id, doc_id or "unknown")
        # If event is already a dict, use it. If it's bytes (poison pill), wrap it.
        if isinstance(event, dict):
            payload = {
                "original_event": event,
                "error": error,
                "failed_at": _now_iso(),
                "source_topic": settings.topic_in if settings else "ingest.normalized",
                "retry_count": _retry_counts.get(retry_key, 0),
            }
        else:
            payload = {
                "raw_payload": str(event),
                "error": error,
                "failed_at": _now_iso(),
                "is_poison_pill": True,
            }

        producer.send(
            TOPIC_DLQ,
            key=_kafka_key_for(tenant_id, doc_id or "unknown"),
            value=payload,
            headers=headers or [],
        )
        producer.flush(timeout=1.0)
        logger.info(
            "message_sent_to_dlq",
            document_id=doc_id,
            tenant_id=tenant_id,
            error=error,
        )
    except (KafkaTimeoutError, ConnectionError, TimeoutError, OSError, RuntimeError) as dlq_exc:
        logger.error(
            "dlq_send_failed",
            document_id=doc_id,
            tenant_id=tenant_id,
            error=str(dlq_exc),
        )


def _is_fsma_event(evt: dict) -> bool:
    """Does this event relate to FSMA traceability?

    Three-layer signal (#1116):

    1. **Explicit FTL classification** — if the extractor stamped
       ``is_ftl_covered`` on any KDE (set by ``_classify_ftl`` against
       the shared FTL catalog), trust that directly. ``True`` means
       the product is on the FTL and the event is in scope; ``False``
       means a verified non-FTL food. This is the reliable signal.
    2. **URL / doc-id substring** — legacy heuristic kept as a
       fallback for events where extraction failed or the extractor
       couldn't classify (``is_ftl_covered`` is ``None``). Good enough
       to route to the FSMA DLQ so operators see the failure.
    3. Otherwise default to non-FSMA.
    """
    ftl_flags = _collect_ftl_flags(evt)
    if True in ftl_flags:
        return True
    # Everything we found was explicitly False — trust that.
    if ftl_flags and False in ftl_flags and True not in ftl_flags:
        return False

    source = str(evt.get("source_url", ""))
    doc_id = str(evt.get("document_id", ""))
    return (
        "fsma" in source.lower()
        or "fsma" in doc_id.lower()
        or "204" in source
    )


def _collect_ftl_flags(evt: dict) -> list:
    """Walk an event payload and collect every ``is_ftl_covered`` flag
    the extractor may have set on KDEs / CTEs. Returns a list of the
    values seen (``True`` / ``False``) — ``None`` entries are skipped
    so they don't tip the caller's tri-state gate to False."""
    flags: list = []
    ctes = evt.get("ctes") or []
    if isinstance(ctes, list):
        for cte in ctes:
            kdes = (cte or {}).get("kdes") if isinstance(cte, dict) else None
            if isinstance(kdes, dict) and kdes.get("is_ftl_covered") is not None:
                flags.append(kdes["is_ftl_covered"])
    top_kdes = evt.get("kdes")
    if isinstance(top_kdes, dict) and top_kdes.get("is_ftl_covered") is not None:
        flags.append(top_kdes["is_ftl_covered"])
    return flags


def _send_to_fsma_dlq(
    producer: KafkaProducer,
    event: any,
    error: str,
    doc_id: str | None = None,
    headers: list | None = None,
    tenant_id: str | None = None,
) -> None:
    """Route failed message to fsma.dead_letter if FSMA-related, else standard DLQ.

    ``tenant_id`` (#1122) is optional — callers hitting this pre-tenant
    (poison pill / auth failure) pass ``None`` and the Kafka key falls
    back to an unambiguous sentinel that cannot shadow any legitimate
    tenant's partition.
    """
    topic = TOPIC_FSMA_DLQ if isinstance(event, dict) and _is_fsma_event(event) else TOPIC_DLQ
    try:
        payload = {
            "original_event": event if isinstance(event, dict) else str(event),
            "error": error,
            "failed_at": _now_iso(),
            "source_topic": settings.topic_in if settings else "ingest.normalized",
            "dlq_topic": topic,
        }
        producer.send(
            topic,
            key=_kafka_key_for(tenant_id, doc_id or "unknown"),
            value=payload,
            headers=headers or [],
        )
        producer.flush(timeout=1.0)
        logger.info(
            "message_routed_to_dlq",
            topic=topic,
            document_id=doc_id,
            tenant_id=tenant_id,
            error=error,
        )
    except (ConnectionError, TimeoutError, OSError, RuntimeError) as dlq_exc:
        logger.error(
            "dlq_routing_failed",
            topic=topic,
            document_id=doc_id,
            tenant_id=tenant_id,
            error=str(dlq_exc),
        )
