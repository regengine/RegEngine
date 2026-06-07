"""Confidence-tier routing of extractions to graph / review topics.

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

from typing import Optional

import structlog
from structlog.contextvars import get_contextvars

from shared.kafka_auth import sign_event
from shared.kafka_compat import KafkaProducerCompat as KafkaProducer
from shared.schemas import ExtractionPayload, GraphEvent

from .constants import (
    NLP_PRODUCER_SERVICE,
    TOPIC_GRAPH_UPDATE,
    TOPIC_NEEDS_REVIEW,
)
from .tenancy import _kafka_key_for
from .thresholds import _current_thresholds

logger = structlog.get_logger("nlp-consumer")


def _build_review_reasons(extraction: ExtractionPayload, tier: str) -> list[dict]:
    """Build structured review-reason codes for the ReviewItem envelope (#1368).

    Reviewers need to know WHY an item landed in the queue, not just its raw
    confidence. Each reason is a ``{reason_code, description, severity}`` tuple
    that the UI can surface and analytics can aggregate.
    """

    reasons: list[dict] = []
    reasons.append(
        {
            "reason_code": f"confidence_tier_{tier}",
            "description": (
                f"Extraction confidence {extraction.confidence_score:.2f} "
                f"falls in the {tier} tier"
            ),
            "severity": "info" if tier == "medium" else "warning",
        }
    )
    attributes = extraction.attributes or {}
    if attributes.get("hallucination_demoted"):
        reasons.append(
            {
                "reason_code": "hallucination_demoted",
                "description": "LLM output contained text not found in source document",
                "severity": "error",
            }
        )
    if attributes.get("fact_type") == "compliance_date":
        reasons.append(
            {
                "reason_code": "regulatory_date_needs_review",
                "description": (
                    "Regulatory date extractions are high-impact and default to HITL"
                ),
                "severity": "warning",
            }
        )
    if not extraction.source_text:
        reasons.append(
            {
                "reason_code": "missing_source_span",
                "description": "Extraction missing provenance span (source_text empty)",
                "severity": "error",
            }
        )
    return reasons


def _route_extraction(
    extraction: ExtractionPayload,
    doc_id: str,
    doc_hash: str,
    source_url: str,
    producer: KafkaProducer,
    tenant_id: Optional[str],
    reviewer_id: str = "nlp_model_v1",
) -> None:
    """Route extraction using a three-tier confidence model (#1258).

    - ``>= high`` (default 0.95): auto-approve to ``graph.update``.
    - ``>= medium`` (default 0.85) and ``< high``: ``nlp.needs_review``
      with ``priority=low`` — reviewer confirms, no re-extraction.
    - ``< medium``: ``nlp.needs_review`` with ``priority=high`` — treat as
      a possible extractor failure, flag for policy review.

    Provenance contract (#1368): every emitted payload carries
    ``source_document_id``, ``source_offset``, and ``confidence`` so the
    KDE→span link survives through Kafka boundaries.
    """

    # Capture correlation id from structured logging context if present
    ctx = get_contextvars()
    request_id = ctx.get("request_id")

    high_threshold, medium_threshold = _current_thresholds()
    confidence = extraction.confidence_score

    # Determine tier
    if confidence >= high_threshold:
        tier = "high"
        priority = None  # N/A for auto-approved
    elif confidence >= medium_threshold:
        tier = "medium"
        priority = "low"
    else:
        tier = "low"
        priority = "high"

    base_headers = [
        ("X-Request-ID", str(request_id or "").encode("utf-8")),
        ("X-Tenant-ID", str(tenant_id or "").encode("utf-8")),
        ("X-Confidence-Tier", tier.encode("utf-8")),
    ]

    if tier == "high":
        # Auto-approved path: straight to graph
        graph_event = GraphEvent(
            event_type="create_provision",
            tenant_id=tenant_id,
            doc_hash=doc_hash,
            document_id=doc_id,
            text_clean=extraction.source_text,
            extraction=extraction,
            provenance={
                "source_url": source_url,
                "offset": extraction.source_offset,
                "source_document_id": doc_id,
                "confidence": confidence,
                "confidence_tier": tier,
                "request_id": request_id,
            },
            embedding=None,
            status="APPROVED",
            reviewer_id=reviewer_id,
        )
        payload = graph_event.model_dump(mode="json")
        logger.info(
            "producing_graph_event",
            entity_count=len(payload.get("extraction", {}).get("entities", [])),
            document_id=doc_id,
        )
        # Sign the event so the graph consumer can verify it came
        # from a trusted producer before routing by tenant_id (#1078).
        signed_payload, signed_headers = sign_event(
            payload,
            producer_service=NLP_PRODUCER_SERVICE,
            existing_headers=base_headers,
        )
        producer.send(
            TOPIC_GRAPH_UPDATE,
            # #1122 — tenant-scoped Kafka key.
            key=_kafka_key_for(tenant_id, doc_id),
            value=signed_payload,
            headers=signed_headers,
        )
        logger.info(
            "high_confidence_extraction",
            document_id=doc_id,
            confidence=confidence,
            tier=tier,
            routed_to="graph",
        )
        return

    # Medium or low tier → review queue with priority + reason codes (#1368)
    reasons = _build_review_reasons(extraction, tier)
    review_payload = {
        "id": None,  # filled downstream on persist
        "tenant_id": str(tenant_id) if tenant_id else None,
        "document_id": doc_id,
        "extraction": extraction.model_dump(mode="json"),
        "status": "pending",
        "priority": priority,
        "confidence_tier": tier,
        "review_reasons": reasons,
        "provenance": {
            "source_url": source_url,
            "source_document_id": doc_id,
            "source_offset": extraction.source_offset,
            "confidence": confidence,
        },
    }
    review_headers = base_headers + [
        ("X-Review-Priority", priority.encode("utf-8")),
    ]
    signed_review_payload, signed_review_headers = sign_event(
        review_payload,
        producer_service=NLP_PRODUCER_SERVICE,
        existing_headers=review_headers,
    )
    producer.send(
        TOPIC_NEEDS_REVIEW,
        # #1122 — tenant-scoped Kafka key.
        key=_kafka_key_for(tenant_id, doc_id),
        value=signed_review_payload,
        headers=signed_review_headers,
    )
    logger.info(
        "low_or_medium_confidence_extraction",
        document_id=doc_id,
        confidence=confidence,
        tier=tier,
        priority=priority,
        reasons=[r["reason_code"] for r in reasons],
        routed_to="review_queue",
    )
