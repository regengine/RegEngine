from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
from cachetools import TTLCache
from confluent_kafka import DeserializingConsumer
from confluent_kafka.schema_registry import SchemaRegistryClient, SchemaRegistryError
from confluent_kafka.schema_registry.avro import AvroDeserializer
from jsonschema import Draft7Validator
from prometheus_client import Counter
from pydantic import ValidationError
from structlog.contextvars import bind_contextvars, clear_contextvars
import os
import time
import uuid

# Add parent directory to path for shared module import
from shared.dlq import DLQProducer  # #1228: consolidated singleton
from shared.schemas import GraphEvent, LegacyGraphEvent
from shared.observability.kafka_propagation import extract_correlation_headers
from shared.kafka_auth import KafkaAuthError, get_allowed_producers, verify_event

from .config import settings
from .neo4j_utils import Neo4jClient, driver, upsert_from_entities

logger = structlog.get_logger("graph-consumer")

MESSAGES_COUNTER = Counter(
    "graph_consumer_messages_total", "Graph consumer messages", ["status"]
)
DLQ_COUNTER = Counter(
    "graph_consumer_dlq_total", "Messages sent to graph DLQ", ["reason"]
)

_shutdown_event = threading.Event()

# Dead Letter Queue configuration
TOPIC_DLQ = "graph.update.dlq"
MAX_RETRIES = 3
# #1166 — bound retry counter with TTLCache so it cannot leak memory on
# a stream of unique doc_ids. 50k entries × 1h TTL matches the pattern
# in services/nlp/app/consumer.py and covers bursts while still letting
# a poison-pill age out if the consumer is long-lived.
_retry_counts: TTLCache[str, int] = TTLCache(maxsize=50_000, ttl=3600)
_dlq_producer: Optional[DLQProducer] = None  # #1228: shared singleton


def _init_dlq_producer() -> DLQProducer:
    """Initialize the shared DLQ producer (called once at consumer startup). #1228"""
    global _dlq_producer
    _dlq_producer = DLQProducer(
        bootstrap_servers=settings.kafka_bootstrap,
        topic=TOPIC_DLQ,
        service_name="graph-consumer",
    )
    return _dlq_producer


def _send_to_dlq(
    event: Dict[str, Any],
    error: str,
    reason: str = "processing_error",
    doc_id: Optional[str] = None,
) -> None:
    """Send a failed message to the dead letter queue via shared DLQProducer. #1228"""
    if not _dlq_producer:
        logger.error("dlq_producer_not_initialized", reason=reason)
        return
    try:
        dlq_payload = json.dumps({
            "original_event": event,
            "error": str(error)[:2048],
            "reason": reason,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "source_topic": "graph.update",
            "document_id": doc_id,
            "retry_count": _retry_counts.get(doc_id or "unknown", 0),
        }).encode("utf-8")
        _dlq_producer.send(dlq_payload, reason=reason, original_topic="graph.update")
        DLQ_COUNTER.labels(reason=reason).inc()
        logger.info("message_sent_to_dlq", topic=TOPIC_DLQ, document_id=doc_id, reason=reason)
    except (ConnectionError, TimeoutError, OSError, RuntimeError) as exc:
        logger.critical("dlq_send_failed", error=str(exc), document_id=doc_id)


def _handle_processing_error(
    record: Any,
    evt: Dict[str, Any],
    exc: Exception,
    consumer: Any,
    context: str = "graph_upsert",
) -> None:
    """Unified error handler: retry tracking → DLQ escalation → offset commit."""
    doc_id = (
        evt.get("document_id")
        or evt.get("doc_id")
        or "unknown"
    )
    retry_key = doc_id
    _retry_counts[retry_key] = _retry_counts.get(retry_key, 0) + 1
    current_retries = _retry_counts[retry_key]

    if current_retries >= MAX_RETRIES:
        logger.error(
            "max_retries_exceeded_sending_to_dlq",
            document_id=doc_id,
            retries=current_retries,
            error=str(exc),
            context=context,
        )
        _send_to_dlq(evt, str(exc), reason=context, doc_id=doc_id)
        _retry_counts.pop(retry_key, None)
    else:
        logger.warning(
            "processing_error_will_skip",
            document_id=doc_id,
            retry=current_retries,
            max_retries=MAX_RETRIES,
            error=str(exc),
            context=context,
        )

    # Always commit to prevent infinite reprocessing (poison pill prevention)
    MESSAGES_COUNTER.labels(status="error").inc()
    try:
        consumer.commit(message=record, asynchronous=False)
    except (RuntimeError, ConnectionError, OSError) as commit_exc:
        logger.error("offset_commit_failed", error=str(commit_exc))


def generate_provision_hash(doc_hash: str, text: str) -> str:
    """Generate stable provision identity combining document and text."""

    key = f"{doc_hash}::{text}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()



def load_schema(schema_name: str) -> str:
    path = os.path.join(os.path.dirname(__file__), "../../../schemas", schema_name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_inbound_schema() -> Optional[Draft7Validator]:
    """Load JSON schema for inbound ``graph.update`` events (#1216).

    Validating before ``GraphEvent.parse_obj()`` / legacy-entity access turns
    producer bugs into structured DLQ entries instead of ``AttributeError:
    'NoneType' object has no attribute ...`` crashes that burn the retry
    budget on deterministic failures. Mirrors the inbound-validation pattern
    in ``services/nlp/app/consumer.py``.
    """
    try:
        from shared.paths import project_root

        repo_root = project_root()
        schema_path = repo_root / "data-schemas" / "events" / "graph.update.schema.json"

        if not schema_path.exists():
            logger.error("inbound_schema_not_found", path=str(schema_path))
            return None

        schema = json.loads(schema_path.read_text())
        return Draft7Validator(schema)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ImportError) as exc:
        logger.error("inbound_schema_load_failed", error=str(exc))
        return None


# Eagerly load inbound schema at module level so validation is fast per-message.
_INBOUND_VALIDATOR: Optional[Draft7Validator] = _load_inbound_schema()


def _validate_inbound_event(evt: Any) -> Optional[str]:
    """Validate an inbound graph.update payload against the JSON schema (#1216).

    Returns ``None`` on success, or a concatenated error string (joined with
    ``"; "``, max 5 errors) for the DLQ payload on failure. Non-dict payloads
    (e.g. raw bytes that slipped past the deserializer) are rejected before
    any attribute access can crash the record processor.
    """
    if _INBOUND_VALIDATOR is None:
        # Schema file could not be loaded — fail-open with a warning so a
        # broken deploy does not halt the consumer entirely.
        return None

    if not isinstance(evt, dict):
        return f"Payload is not a JSON object (got {type(evt).__name__})"

    errors = list(_INBOUND_VALIDATOR.iter_errors(evt))
    if not errors:
        return None
    return "; ".join(e.message for e in errors[:5])

def _ensure_topic(topic: str) -> None:
    # confluent-kafka AdminClient implementation omitted for brevity/simplicity in this refactor step.
    # Typically infrastructure (Terraform) manages topics.
    pass


def stop_consumer() -> None:
    _shutdown_event.set()


def json_deserializer(v, ctx):
    """Fallback JSON deserializer"""
    if v is None:
        return None
    try:
        return json.loads(v.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return v

async def run_consumer() -> None:
    topics = [settings.topic_in, "graph.update"]

    # Initialize DLQ producer for error routing
    _init_dlq_producer()
    
    schema_registry = SchemaRegistryClient({'url': 'http://schema-registry:8081'})
    avro_deserializer = AvroDeserializer(
        schema_registry,
        load_schema("fsma_event.avsc"),
        # from_dict not strictly needed if we parse into dict/pydantic later, 
        # but prevents object return.
    )

    consumer_conf = {
        'bootstrap.servers': settings.kafka_bootstrap,
        'group.id': "graph-service",
        'auto.offset.reset': "earliest",
        'enable.auto.commit': False,
        'value.deserializer': avro_deserializer
    }
    
    # Hybrid Deserializer workaround
    def hybrid_deserializer(value, ctx):
        if value is None: return None
        # Check for magic byte 0 (Confluent Schema Registry)
        if len(value) > 5 and value[0] == 0:
             return avro_deserializer(value, ctx)
        return json_deserializer(value, ctx)

    consumer_conf['value.deserializer'] = hybrid_deserializer

    consumer = DeserializingConsumer(consumer_conf)
    consumer.subscribe(topics)
    
    try:
        while not _shutdown_event.is_set():
            # Confluent `poll` is blocking but releases GIL. 
            # To be async friendly, we run in executor or short timeout loop.
            msg = await asyncio.to_thread(consumer.poll, 0.5)
            
            if msg is None:
                await asyncio.sleep(0.1)
                continue
            if msg.error():
                logger.error("consumer_error", error=msg.error())
                continue
                
            record = msg
            evt = record.value() # Deserialized dict
            
            # ... process message ...
            # Code structure adapts:
            
            req_id = None
            correlation_id = None
            tenant_id_hdr = None
            try:
                raw_headers = record.headers() or []  # confluent-kafka: list of tuples
                # Legacy X-Request-ID parsing retained for backward compat.
                for k, v in raw_headers:
                    if k == "X-Request-ID" and v:
                        try:
                            req_id = v.decode('utf-8')
                        except UnicodeDecodeError:
                            req_id = None
                        break
                # Extract correlation / tenant headers via the shared helper so
                # spans emitted by this consumer can be stitched back to the
                # producer's originating request (#1318).
                correlation_id, tenant_id_hdr = extract_correlation_headers(raw_headers)
            except (TypeError, ValueError, AttributeError, UnicodeDecodeError) as header_exc:
                logger.debug("header_parse_error", error=str(header_exc))

            # Re-seed structlog contextvars so every log record emitted below
            # inherits request_id / correlation_id / tenant_id.
            binding: dict = {}
            if req_id:
                binding["request_id"] = req_id
            if correlation_id:
                binding["correlation_id"] = correlation_id
                # Also seed the HTTP-side contextvar used by error handlers.
                try:
                    from shared.observability.correlation import set_correlation_id

                    set_correlation_id(correlation_id)
                except Exception:
                    pass
            if tenant_id_hdr:
                binding["tenant_id"] = tenant_id_hdr
            if binding:
                bind_contextvars(**binding)

            # --- HMAC producer authentication (#1078) ---
            # Refuse to touch ``tenant_id`` unless the message is signed
            # by a service authorized to publish to this topic. The
            # authoritative topic name is ``record.topic()`` so a
            # multi-topic subscriber looks up the correct allowlist.
            # On failure we DLQ the message and commit the offset —
            # retries won't help, the signature will never verify.
            try:
                topic_name = record.topic()
            except Exception:
                topic_name = "graph.update"
            try:
                evt, _verified_producer = verify_event(
                    evt if isinstance(evt, dict) else {},
                    raw_headers if isinstance(raw_headers, list) else None,
                    topic=topic_name,
                    allowed_producers=get_allowed_producers(topic_name),
                )
            except KafkaAuthError as auth_exc:
                logger.error(
                    "kafka_auth_failed",
                    reason=auth_exc.reason,
                    topic=topic_name,
                    **auth_exc.fields,
                )
                MESSAGES_COUNTER.labels(status="unauthorized").inc()
                _send_to_dlq(
                    evt if isinstance(evt, dict) else {"raw": str(evt)[:2048]},
                    str(auth_exc),
                    reason="kafka_auth_failed",
                    doc_id=None,
                )
                try:
                    consumer.commit(message=record, asynchronous=False)
                except Exception as commit_exc:
                    logger.error("offset_commit_failed", error=str(commit_exc))
                continue

            # --- Inbound schema validation (#1216) ---
            # Require the payload to be a dict before any schema parsing so
            # a non-dict payload (bytes, None, list) cannot crash ``.get``.
            if not isinstance(evt, dict):
                logger.error(
                    "graph_update_invalid_payload_type",
                    topic=topic_name,
                    payload_type=type(evt).__name__,
                    tenant_id=tenant_id_hdr,
                )
                MESSAGES_COUNTER.labels(status="invalid_schema").inc()
                _send_to_dlq(
                    {"raw": str(evt)[:2048]},
                    f"non-dict payload: {type(evt).__name__}",
                    reason="invalid_schema",
                    doc_id=None,
                )
                try:
                    consumer.commit(message=record, asynchronous=False)
                except Exception as commit_exc:
                    logger.error("offset_commit_failed", error=str(commit_exc))
                clear_contextvars()
                continue

            # --- Processing Logic (Simplifying for diff) ---
            # Try to parse as GraphEvent first (new format)
            try:
                # Same logic as before
                graph_event = GraphEvent.parse_obj(evt)
                doc_id = graph_event.document_id
                doc_hash = graph_event.doc_hash
                extraction = graph_event.extraction
                tenant_id = graph_event.tenant_id

                # ... (DB routing) ...
                if tenant_id:
                    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
                else:
                    db_name = Neo4jClient.get_global_database_name()

                logger.info("processing_graph_event", event_type=graph_event.event_type, status=graph_event.status)

                provision_hash = generate_provision_hash(doc_hash, graph_event.text_clean)
                provision_data = {
                    "content_hash": provision_hash,
                    "text_clean": graph_event.text_clean,
                    "extraction": extraction.dict(),
                    "provenance": graph_event.provenance,
                    "status": graph_event.status,
                    "reviewer_id": graph_event.reviewer_id,
                    "tenant_id": str(tenant_id) if tenant_id else None,
                }

                try:
                    neo4j_client = Neo4jClient(database=db_name)
                    await neo4j_client.upsert_provision(
                        document_id=doc_id,
                        doc_hash=doc_hash,
                        provision=provision_data,
                        embedding=graph_event.embedding,
                    )
                    await neo4j_client.close()
                    MESSAGES_COUNTER.labels(status="success").inc()
                    consumer.commit(message=record, asynchronous=False)
                    # #1166 — clear any prior retry count so a doc that
                    # succeeded after 1-2 transient failures does not
                    # linger in _retry_counts until the TTL expires.
                    _retry_counts.pop(doc_id, None)

                except Exception as exc:
                    _handle_processing_error(record, evt, exc, consumer, context="graph_upsert")

            except ValidationError:
                # Fall back to legacy format. Validate it too (#1216) so a
                # payload that fails BOTH schemas is routed to the DLQ
                # instead of being used as-is. This is defense-in-depth:
                # we fail closed rather than quietly dropping junk into
                # the graph.
                try:
                    legacy_event = LegacyGraphEvent.model_validate(evt)
                except ValidationError as legacy_exc:
                    logger.error(
                        "graph_update_schema_invalid",
                        topic=topic_name,
                        tenant_id=evt.get("tenant_id") if isinstance(evt, dict) else None,
                        document_id=(
                            evt.get("document_id") if isinstance(evt, dict) else None
                        ),
                        errors=legacy_exc.errors()[:10],
                    )
                    MESSAGES_COUNTER.labels(status="invalid_schema").inc()
                    _send_to_dlq(
                        evt,
                        str(legacy_exc),
                        reason="invalid_schema",
                        doc_id=(
                            evt.get("document_id")
                            if isinstance(evt, dict)
                            else None
                        ),
                    )
                    try:
                        consumer.commit(message=record, asynchronous=False)
                    except Exception as commit_exc:
                        logger.error("offset_commit_failed", error=str(commit_exc))
                    clear_contextvars()
                    continue

                # Use validated object for downstream logic.
                doc_id = legacy_event.document_id
                entities = legacy_event.entities
                source_url = legacy_event.source_url
                tenant_id = legacy_event.tenant_id

                try:
                    # Determine database for legacy upsert
                    db_name_legacy = Neo4jClient.get_global_database_name()
                    if tenant_id:
                        try:
                            # Ensure UUID format
                            tid_obj = uuid.UUID(str(tenant_id))
                            db_name_legacy = Neo4jClient.get_tenant_database_name(tid_obj)
                            # Use string for storage/passing
                            tenant_id = str(tid_obj)
                        except ValueError:
                            logger.error(
                                "invalid_tenant_id_in_message",
                                tenant_id=tenant_id,
                                doc_id=doc_id,
                            )
                            raise ValueError(
                                f"Invalid tenant_id '{tenant_id}' — refusing to fall back to global database"
                            )

                    def _run_legacy_upsert():
                        # Use correct database
                        with driver().session(database=db_name_legacy) as session:
                            with session.begin_transaction() as tx:
                                upsert_from_entities(session, doc_id, source_url, entities, tenant_id=tenant_id)
                                tx.commit()
                    
                    await asyncio.to_thread(_run_legacy_upsert)
                    logger.info("graph_upsert_ok_legacy", doc_id=doc_id)
                    MESSAGES_COUNTER.labels(status="success").inc()
                    consumer.commit(message=record, asynchronous=False)
                    # #1166 — clear any prior retry count so a doc that
                    # succeeded after 1-2 transient failures does not
                    # linger in _retry_counts until the TTL expires.
                    _retry_counts.pop(doc_id, None)
                except Exception as exc:
                    _handle_processing_error(record, evt, exc, consumer, context="legacy_upsert")
            
            clear_contextvars()
    finally:
         consumer.close()
         if _dlq_producer:
             _dlq_producer.flush(timeout=2.0)  # shared DLQProducer.flush() #1228

if __name__ == "__main__":
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        logger.info("consumer_interrupted_by_user")
