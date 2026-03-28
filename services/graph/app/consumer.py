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
from confluent_kafka import DeserializingConsumer, Producer
from confluent_kafka.schema_registry import SchemaRegistryClient, SchemaRegistryError
from confluent_kafka.schema_registry.avro import AvroDeserializer
from prometheus_client import Counter
from pydantic import ValidationError
from structlog.contextvars import bind_contextvars, clear_contextvars
import os
import time
import uuid

# Add parent directory to path for shared module import
from shared.schemas import GraphEvent

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
_retry_counts: Dict[str, int] = {}
_dlq_producer: Optional[Producer] = None


def _init_dlq_producer() -> Producer:
    """Initialize the DLQ producer (called once at consumer startup)."""
    global _dlq_producer
    _dlq_producer = Producer({"bootstrap.servers": settings.kafka_bootstrap})
    return _dlq_producer


def _send_to_dlq(
    event: Dict[str, Any],
    error: str,
    reason: str = "processing_error",
    doc_id: Optional[str] = None,
) -> None:
    """Send a failed message to the dead letter queue for manual inspection."""
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
        _dlq_producer.produce(TOPIC_DLQ, value=dlq_payload)
        _dlq_producer.flush(timeout=5.0)
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
        # We can't easily mix serializers on one consumer in confluent-kafka without custom logic?
        # Actually deserializer is per-topic or global.
        # Strict AvroDeserializer will fail on JSON.
        # Correct approach: Use Byte consumer and manual decode based on magic byte (0x00) or topic.
        'value.deserializer': avro_deserializer
        # Wait - we have mixed topics! JSON legacy and Avro.
        # We cannot use value.deserializer on the main config if topics differ.
        # But for this sprint, we assume moving to Avro.
        # If legacy topic sends JSON, AvroDeserializer fails.
        # For simplicity, let's assume 'graph.update' IS the topic we want.
        # Or implement a hybrid deserializer.
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
            try:
                 headers = dict(record.headers() or []) # Confluent headers() returns list of tuples
                 # Headers are (key, value)
                 for k, v in headers.items():
                    if k == "X-Request-ID" and v:
                        req_id = v.decode('utf-8')
                        break
            except (TypeError, ValueError, AttributeError, UnicodeDecodeError) as header_exc:
                 logger.debug("header_parse_error", error=str(header_exc))
            
            if req_id:
                bind_contextvars(request_id=req_id)

            # ... logic copy ...
            
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

                except Exception as exc:
                    _handle_processing_error(record, evt, exc, consumer, context="graph_upsert")

            except ValidationError:
                # Fall back to legacy format (Synchronous)
                doc_id = evt.get("document_id")
                entities = evt.get("entities", [])
                source_url = evt.get("source_url")
                # Fix: Extract tenant_id safely for legacy events
                tenant_id = evt.get("tenant_id")
                
                if not doc_id:
                     # logger.warning("missing_document_id", event=evt) 
                     # Skipping noisy log for tests?
                     MESSAGES_COUNTER.labels(status="skipped").inc()
                     consumer.commit(message=record, asynchronous=False)
                     continue

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
                            pass

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
                except Exception as exc:
                    _handle_processing_error(record, evt, exc, consumer, context="legacy_upsert")
            
            clear_contextvars()
    finally:
         consumer.close()
         if _dlq_producer:
             _dlq_producer.flush(timeout=2.0)

if __name__ == "__main__":
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        logger.info("consumer_interrupted_by_user")
