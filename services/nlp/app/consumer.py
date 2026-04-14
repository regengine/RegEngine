from __future__ import annotations

import json
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
from jsonschema import Draft7Validator, ValidationError
from kafka import KafkaConsumer, KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import KafkaTimeoutError, TopicAlreadyExistsError
from opentelemetry import trace, propagate
from prometheus_client import Counter
from structlog.contextvars import get_contextvars

from pathlib import Path
import sys

# Standardized path discovery via shared utility
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.schemas import (
    ExtractionPayload,
    GraphEvent,
    ObligationType,
    ReviewItem,
    Threshold,
)

from .classification import SignalClassifier
from .config import settings
from .extractor import extract_entities
from .resolution import EntityResolver
from .s3_utils import get_bytes

logger = structlog.get_logger("nlp-consumer")
_audit_logger = structlog.get_logger("nlp-consumer-audit")

try:
    MESSAGES_COUNTER = Counter("nlp_messages_total", "NLP messages processed", ["status"])
    POISON_PILL_COUNTER = Counter("nlp_poison_pill_total", "Count of malformed Kafka messages")
except ValueError:
    # Metric already registered (happens during test re-imports)
    from prometheus_client import REGISTRY
    MESSAGES_COUNTER = REGISTRY._names_to_collectors.get("nlp_messages_total")
    POISON_PILL_COUNTER = REGISTRY._names_to_collectors.get("nlp_poison_pill_total")

_shutdown_event = threading.Event()

# Confidence threshold for automatic approval
# Using settings.extraction_confidence_high (SRP 11-7) with fallback
CONFIDENCE_THRESHOLD = getattr(settings, 'extraction_confidence_high', 0.85) if settings else 0.85

# Topic names for routing
TOPIC_GRAPH_UPDATE = "graph.update"
TOPIC_NEEDS_REVIEW = "nlp.needs_review"
TOPIC_DLQ = "nlp.extracted.dlq"
TOPIC_FSMA_DLQ = "fsma.dead_letter"

# Max retries before sending to DLQ
MAX_RETRIES = 3
# Bounded retry tracker — TTL prevents unbounded growth under partial failures (#994)
try:
    from cachetools import TTLCache
    _retry_counts: dict[str, int] = TTLCache(maxsize=50_000, ttl=3600)  # type: ignore[assignment]
except ImportError:
    _retry_counts: dict[str, int] = {}  # type: ignore[no-redef]

RESOLVER = EntityResolver()
CLASSIFIER = SignalClassifier()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _convert_entities_to_extraction(
    entities: list, doc_id: str, source_url: str
) -> list[ExtractionPayload]:
    """Convert legacy entity format to canonical ExtractionPayload format."""
    extractions = []

    # Group entities to form complete extractions
    obligations = [e for e in entities if e.get("type") == "OBLIGATION"]
    thresholds = [e for e in entities if e.get("type") == "THRESHOLD"]
    jurisdictions = [e for e in entities if e.get("type") == "JURISDICTION"]

    for obl in obligations:
        text = obl.get("text", "")
        start_offset = obl.get("start", 0)

        # Simple subject/action parsing from text
        # In production, this would use more sophisticated NLP
        parts = text.split()
        subject = " ".join(parts[: min(3, len(parts))])
        action_words = ["shall", "must", "required to", "has to", "should", "may"]
        action = next((w for w in action_words if w in text.lower()), "must")

        # Determine obligation type
        if (
            "must" in text.lower()
            or "shall" in text.lower()
            or "required" in text.lower()
        ):
            obl_type = ObligationType.MUST
        elif "should" in text.lower():
            obl_type = ObligationType.SHOULD
        elif "may" in text.lower():
            obl_type = ObligationType.MAY
        else:
            obl_type = ObligationType.MUST

        # Find associated thresholds (within proximity)
        associated_thresholds = []
        for thresh in thresholds:
            if abs(thresh.get("start", 0) - start_offset) < 200:
                attrs = thresh.get("attrs", {})
                threshold = Threshold(
                    value=attrs.get("value", 0),
                    unit=attrs.get("unit_normalized", "units"),
                    operator="gte",  # Default operator
                    context=None,
                )
                associated_thresholds.append(threshold)

        # Find jurisdiction
        jurisdiction = None
        for jur in jurisdictions:
            if abs(jur.get("start", 0) - start_offset) < 500:
                jurisdiction = jur.get("attrs", {}).get("name")
                break

        # Calculate simple confidence score
        # In production, this would use ML model confidence
        base_confidence = 0.75
        if associated_thresholds:
            base_confidence += 0.1
        if jurisdiction:
            base_confidence += 0.05
        if len(text) > 50:
            base_confidence += 0.05

        # Check for related Organizations and resolve them
        organizations = [e for e in entities if e.get("type") == "ORGANIZATION"]
        resolved_entities = []
        for org in organizations:
            # Proximity check
            if abs(org.get("start", 0) - start_offset) < 500:
                raw_name = org.get("attrs", {}).get("name")
                resolution = RESOLVER.resolve_organization(raw_name)
                
                entity_info = {
                     "raw_name": raw_name,
                     "type": "ORGANIZATION",
                     "start": org.get("start"),
                     "end": org.get("end")
                }
                
                if resolution:
                    entity_info["entity_id"] = resolution["id"]
                    entity_info["normalized_name"] = resolution["name"]
                    entity_info["entity_type"] = resolution["type"]
                    # Boost confidence if we found a known entity
                    base_confidence += 0.15
                    
                resolved_entities.append(entity_info)

        confidence = min(base_confidence, 0.99)
        
        # Categorize Signal
        category, risk, risk_conf = CLASSIFIER.classify_signal(text)
        
        attributes = {
            "document_id": doc_id, 
            "source_url": source_url,
            "signal_category": category,
            "risk_level": risk
        }
        if resolved_entities:
            attributes["resolved_entities"] = resolved_entities

        extraction = ExtractionPayload(
            subject=subject,
            action=action,
            object=None,
            obligation_type=obl_type,
            thresholds=associated_thresholds,
            jurisdiction=jurisdiction,
            confidence_score=confidence,
            source_text=text,
            source_offset=start_offset,
            attributes=attributes,
        )
        extractions.append(extraction)

    # Handle FSMA Regulatory Dates (User Request)
    reg_dates = [e for e in entities if e.get("type") == "REGULATORY_DATE"]
    for rd in reg_dates:
        attrs = rd.get("attrs", {})
        date_value = attrs.get("value")
        
        extraction = ExtractionPayload(
            subject="covered entities",
            action="must comply by",
            object="FSMA 204 requirements",
            obligation_type=ObligationType.MUST,
            effective_date=date_value,
            confidence_score=0.99, # High confidence for explicit date matches
            source_text=rd.get("text"),
            source_offset=rd.get("start"),
            attributes={
                "document_id": doc_id,
                "source_url": source_url,
                "fact_type": "compliance_date",
                "provenance": attrs.get("provenance"),
                "signal_category": "regulatory_change",
                "risk_level": "high", # Compliance Date changes are high impact
                "entities": [rd],  # DEBT-023 fix: route via attributes dict, not non-existent field
            },
        )
        extractions.append(extraction)

    return extractions


def _load_schema() -> Draft7Validator:
    """Load JSON schema using standardized project path discovery."""
    from shared.paths import project_root
    
    repo_root = project_root()
    schema_path = repo_root / "data-schemas" / "events" / "nlp.extracted.schema.json"
    
    if not schema_path.exists():
        logger.error("schema_not_found", path=str(schema_path))
        raise FileNotFoundError(f"Could not find schema at {schema_path}")

    schema = json.loads(schema_path.read_text())
    return Draft7Validator(schema)


def _ensure_topic(topic: str) -> None:
    admin = None
    try:
        admin = KafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap)
        admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
    except TopicAlreadyExistsError:
        pass
    except (ConnectionError, TimeoutError, RuntimeError, OSError) as exc:  # pragma: no cover - infra dependent
        logger.warning("topic_creation_failed", topic=topic, error=str(exc))
    finally:
        if admin is not None:
            try:
                admin.close()
            except (RuntimeError, OSError):  # pragma: no cover
                pass


def _route_extraction(
    extraction: ExtractionPayload,
    doc_id: str,
    doc_hash: str,
    source_url: str,
    producer: KafkaProducer,
    tenant_id: Optional[str],
    reviewer_id: str = "nlp_model_v1",
) -> None:
    """Route extraction to appropriate topic based on confidence score."""
    # Capture correlation id from structured logging context if present
    ctx = get_contextvars()
    request_id = ctx.get("request_id")
    
    # Use configurable high confidence threshold for auto-approval
    threshold = CONFIDENCE_THRESHOLD
    
    if extraction.confidence_score >= threshold:
        # High confidence: send directly to graph
        graph_event = GraphEvent(
            event_type="create_provision",
            tenant_id=tenant_id,  # Phase 2 will add tenant routing
            doc_hash=doc_hash,
            document_id=doc_id,
            text_clean=extraction.source_text,
            extraction=extraction,
            provenance={
                "source_url": source_url,
                "offset": extraction.source_offset,
                "request_id": request_id,
            },
            embedding=None,  # Phase 2+ will add embeddings
            status="APPROVED",
            reviewer_id=reviewer_id,
        )
        # Send to graph update topic
        payload = graph_event.model_dump(mode="json")
        logger.info(f"Producing Graph Event with {len(payload.get('extraction', {}).get('entities', []))} entities")
        producer.send(
            TOPIC_GRAPH_UPDATE,
            key=doc_id, # Ensure key is string
            value=payload,
            headers=[("X-Request-ID", str(request_id or "").encode("utf-8"))],
        )
        logger.info(
            "high_confidence_extraction",
            document_id=doc_id,
            confidence=extraction.confidence_score,
            routed_to="graph",
        )
    else:
        # Low confidence: send to review queue
        review_item = ReviewItem(
            tenant_id=tenant_id,
            document_id=doc_id,
            extraction=extraction,
            status="pending",
        )
        producer.send(
            TOPIC_NEEDS_REVIEW,
            key=doc_id,
            value=review_item.model_dump(mode="json"),
            headers=[("X-Request-ID", str(request_id or "").encode("utf-8"))],
        )
        logger.info(
            "low_confidence_extraction",
            document_id=doc_id,
            confidence=extraction.confidence_score,
            routed_to="review_queue",
        )


def _send_to_dlq(
    producer: KafkaProducer,
    event: any,
    error: str,
    doc_id: str | None = None,
    headers: list | None = None,
) -> None:
    """Send a failed message to the dead letter queue for manual inspection."""
    try:
        # If event is already a dict, use it. If it's bytes (poison pill), wrap it.
        if isinstance(event, dict):
            payload = {
                "original_event": event,
                "error": error,
                "failed_at": _now_iso(),
                "source_topic": settings.topic_in if settings else "ingest.normalized",
                "retry_count": _retry_counts.get(doc_id or "unknown", 0),
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
            key=doc_id or "unknown",
            value=payload,
            headers=headers or [],
        )
        producer.flush(timeout=1.0)
        logger.info("message_sent_to_dlq", document_id=doc_id, error=error)
    except (ConnectionError, TimeoutError, OSError, RuntimeError) as dlq_exc:
        logger.error("dlq_send_failed", document_id=doc_id, error=str(dlq_exc))


def _is_fsma_event(evt: dict) -> bool:
    """Heuristic: does this event relate to FSMA traceability?"""
    source = str(evt.get("source_url", ""))
    doc_id = str(evt.get("document_id", ""))
    return "fsma" in source.lower() or "fsma" in doc_id.lower() or "204" in source


def _send_to_fsma_dlq(
    producer: KafkaProducer,
    event: any,
    error: str,
    doc_id: str | None = None,
    headers: list | None = None,
) -> None:
    """Route failed message to fsma.dead_letter if FSMA-related, else standard DLQ."""
    topic = TOPIC_FSMA_DLQ if isinstance(event, dict) and _is_fsma_event(event) else TOPIC_DLQ
    try:
        payload = {
            "original_event": event if isinstance(event, dict) else str(event),
            "error": error,
            "failed_at": _now_iso(),
            "source_topic": settings.topic_in if settings else "ingest.normalized",
            "dlq_topic": topic,
        }
        producer.send(topic, key=doc_id or "unknown", value=payload, headers=headers or [])
        producer.flush(timeout=1.0)
        logger.info("message_routed_to_dlq", topic=topic, document_id=doc_id, error=error)
    except (ConnectionError, TimeoutError, OSError, RuntimeError) as dlq_exc:
        logger.error("dlq_routing_failed", topic=topic, document_id=doc_id, error=str(dlq_exc))


def stop_consumer() -> None:
    _shutdown_event.set()


from shared.observability import setup_standalone_observability
tracer = setup_standalone_observability("nlp-consumer")

def run_consumer() -> None:
    # Ensure topics exist
    _ensure_topic(TOPIC_GRAPH_UPDATE)
    _ensure_topic(TOPIC_NEEDS_REVIEW)
    _ensure_topic(TOPIC_FSMA_DLQ)
    _ensure_topic(TOPIC_DLQ)

    # Use raw consumer to handle poison pills manually
    consumer = KafkaConsumer(
        settings.topic_in,
        bootstrap_servers=settings.kafka_bootstrap,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        group_id="nlp-service",
    )
    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap,
        key_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        acks="all",
    )

    while not _shutdown_event.is_set():
        messages = consumer.poll(timeout_ms=500)
        if not messages:
            continue
        for records in messages.values():
            for record in records:
                # Standardized Trace Injection
                with tracer.start_as_current_span(
                    "nlp.process_message", 
                    attributes={"kafka.topic": record.topic, "kafka.offset": record.offset}
                ) as span:
                    # Capture trace context for DLQ headers
                    headers = []
                    propagate.inject(headers)
                    # Convert OTel list of tuples to Kafka list of tuples (headers)
                    kafka_headers = [(k, v.encode("utf-8")) for k, v in headers]

                    raw_value = record.value
                    try:
                        evt = json.loads(raw_value.decode("utf-8")) if raw_value else {}
                    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                        logger.error("poison_pill_detected", error=str(exc), offset=record.offset)
                        POISON_PILL_COUNTER.inc()
                        _send_to_dlq(producer, raw_value, f"Deserialization failed: {str(exc)}", headers=kafka_headers)
                        consumer.commit()
                        continue

                    if not evt: continue

                    doc_id = evt.get("document_id") or evt.get("doc_id") or "unknown"
                    span.set_attribute("document_id", doc_id)

                    try:
                        doc_hash = evt.get("document_hash") or evt.get("content_hash") or doc_id
                        norm_path = evt.get("normalized_s3_path")
                        inline_text = evt.get("text_clean")
                        tenant_id = evt.get("tenant_id")
                        provenance = evt.get("provenance") or {}
                    except (KeyError, TypeError, ValueError, AttributeError) as field_exc:
                        logger.error(
                            "malformed_event_fields",
                            error=str(field_exc),
                            offset=record.offset,
                        )
                        _send_to_fsma_dlq(
                            producer, evt, f"Field extraction failed: {field_exc}",
                            doc_id, kafka_headers,
                        )
                        MESSAGES_COUNTER.labels(status="error").inc()
                        consumer.commit()
                        continue

                    if not doc_id or (not norm_path and not inline_text):
                        logger.warning("skipping_event_missing_keys", event=evt)
                        MESSAGES_COUNTER.labels(status="skipped").inc()
                        consumer.commit()
                        continue

                    try:
                        if inline_text:
                            text = str(inline_text)[:2_000_000]
                            source_url = provenance.get(
                                "source_url", evt.get("source_url", "unknown")
                            )
                        else:
                            _, _, bucket_key = norm_path.partition("s3://")
                            bucket, _, key = bucket_key.partition("/")
                            payload = json.loads(get_bytes(bucket, key))
                            text = payload.get("text", "")[:2_000_000]
                            source_url = payload.get("source_url", "unknown")

                        # Extract entities using existing extractor
                        entities = extract_entities(text)

                        # Convert to canonical ExtractionPayload format
                        extractions = _convert_entities_to_extraction(
                            entities, doc_id, source_url
                        )

                        # Route each extraction based on confidence
                        for extraction in extractions:
                            _route_extraction(
                                extraction,
                                doc_id,
                                doc_hash,
                                source_url,
                                producer,
                                tenant_id,
                            )

                        # Also send to legacy topic for backward compatibility
                        legacy_out = {
                            "event_id": str(uuid.uuid4()),
                            "document_id": doc_id,
                            "tenant_id": tenant_id,
                            "source_url": source_url,
                            "timestamp": _now_iso(),
                            "entities": entities,
                        }
                        _load_schema().validate(legacy_out)
                        producer.send(settings.topic_out, key=doc_id, value=legacy_out)

                        producer.flush(timeout=1.0)

                        logger.info(
                            "nlp_extraction_complete",
                            document_id=doc_id,
                            extraction_count=len(extractions),
                            high_confidence=sum(
                                1
                                for e in extractions
                                if e.confidence_score >= settings.extraction_confidence_high
                            ),
                            needs_review=sum(
                                1
                                for e in extractions
                                if e.confidence_score < settings.extraction_confidence_high
                            ),
                        )
                        MESSAGES_COUNTER.labels(status="success").inc()

                        # Synchronous audit logging for FSMA compliance (#982)
                        try:
                            _audit_logger.info(
                                "nlp_extraction_audited",
                                extra={
                                    "document_id": doc_id,
                                    "tenant_id": tenant_id,
                                    "source_url": source_url,
                                    "extraction_count": len(extractions),
                                    "timestamp": _now_iso(),
                                },
                            )
                        except Exception as _audit_exc:
                            logger.error("nlp_audit_logging_failed", document_id=doc_id, error=str(_audit_exc))

                        consumer.commit()
                    except (ValidationError, KafkaTimeoutError) as exc:
                        # Track retries per document
                        retry_key = doc_id or "unknown"
                        _retry_counts[retry_key] = _retry_counts.get(retry_key, 0) + 1

                        if _retry_counts[retry_key] >= MAX_RETRIES:
                            logger.error(
                                "nlp_max_retries_exceeded_sending_to_dlq",
                                document_id=doc_id,
                                retries=_retry_counts[retry_key],
                                error=str(exc),
                            )
                            _send_to_fsma_dlq(producer, evt, str(exc), doc_id, headers=kafka_headers)
                            _retry_counts.pop(retry_key, None)
                            consumer.commit()  # Don't re-process
                        else:
                            logger.warning(
                                "nlp_validation_or_kafka_error_will_retry",
                                document_id=doc_id,
                                retry=_retry_counts[retry_key],
                                error=str(exc),
                            )
                        MESSAGES_COUNTER.labels(status="error").inc()
                    except Exception as exc:  # pragma: no cover - requires infra
                        logger.exception(
                            "nlp_processing_error_sending_to_dlq",
                            document_id=doc_id,
                            error=str(exc),
                        )
                        _send_to_fsma_dlq(producer, evt, str(exc), doc_id, headers=kafka_headers)
                        consumer.commit()  # Don't re-process unexpected failures
                        MESSAGES_COUNTER.labels(status="error").inc()
    consumer.close()
    producer.close()
