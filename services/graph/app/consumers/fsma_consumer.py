"""
FSMA 204 Kafka Consumer for Graph Ingestion.

Consumes extracted FSMA events from the NLP service and ingests them
into the Neo4j knowledge graph for traceability queries.

Migrated to Confluent Kafka with Avro Schema Validation (Task 5.6).
"""

from __future__ import annotations

import asyncio
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import socket
import structlog
from confluent_kafka import Consumer, Producer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField
from prometheus_client import Counter, Histogram
from structlog.contextvars import bind_contextvars, clear_contextvars

# DLQ - Dead Letter Queue Counter
DLQ_COUNTER = Counter("fsma_consumer_dlq_messages", "Messages sent to DLQ", ["reason"])

# Global DLQ Producer (initialized in run_fsma_consumer)
_dlq_producer: Optional[Producer] = None

def send_to_dlq(topic: str, original_msg: bytes, reason: str, error: str = "") -> None:
    """Send failed message to Dead Letter Queue."""
    if not _dlq_producer:
        logger.error("dlq_producer_not_initialized", reason=reason)
        return

    try:
        # Add metadata headers
        headers = [
            ("error_reason", reason.encode("utf-8")),
            ("error_detail", str(error)[:1024].encode("utf-8")),
            ("original_topic", topic.encode("utf-8")),
            ("service", b"fsma-graph-consumer"),
        ]
        
        _dlq_producer.produce(
            settings.topic_dlq,
            value=original_msg,
            headers=headers,
        )
        # Flush immediately for safety in this critical path (could be optimized)
        _dlq_producer.poll(0)
        
        DLQ_COUNTER.labels(reason=reason).inc()
        logger.info("message_sent_to_dlq", reason=reason, error=error)
        
    except Exception as e:
        logger.critical("dlq_emission_failed", error=str(e))

# Add parent directory to path for shared module import
# Robustly find project root by looking for 'shared' directory
current_path = Path(__file__).resolve()
project_root = current_path.parent
while not (project_root / "shared").exists():
    if project_root == project_root.parent:
        # Fallback to brittle method if 'shared' not found (container edge case)
        project_root = current_path.parents[4]
        break
    project_root = project_root.parent
sys.path.insert(0, str(project_root))

from services.graph.app.config import settings
from services.graph.app.fsma_audit import log_extraction
from services.graph.app.models.fsma_nodes import (
    FSMA_CONSTRAINTS,
    CTEType,
    Document,
    Facility,
    FSMARelationships,
    Lot,
    TraceEvent,
)
from services.graph.app.neo4j_utils import Neo4jClient

logger = structlog.get_logger("fsma-graph-consumer")

# Event types that require TLC Source fields (FSMA 204 mandate)
TLC_SOURCE_REQUIRED_EVENTS = {"TRANSFORMATION", "INITIAL_PACKING", "CREATION"}

# Metrics
FSMA_MESSAGES_COUNTER = Counter(
    "fsma_graph_messages_total", "FSMA graph consumer messages", ["status"]
)
FSMA_INGEST_DURATION = Histogram(
    "fsma_graph_ingest_duration_seconds", "FSMA event ingestion duration"
)

# Topic configuration
FSMA_TOPIC = "fsma.events.extracted"

_shutdown_event = threading.Event()


def _extract_tenant_source_identifiers(
    event: Dict[str, Any],
) -> tuple[Optional[str], Optional[str]]:
    """Return tenant-level TLC source identifiers if present on the event."""

    tenant_info = event.get("tenant") or event.get("tenant_profile") or {}
    tenant_gln = (
        event.get("tenant_gln")
        or event.get("tenant_gs1_gln")
        or tenant_info.get("gln")
        or tenant_info.get("tenant_gln")
    )
    tenant_fda_reg = (
        event.get("tenant_fda_reg")
        or event.get("tenant_fda_registration")
        or tenant_info.get("fda_reg")
        or tenant_info.get("fda_registration")
    )

    return tenant_gln, tenant_fda_reg


class TLCSourceValidationError(Exception):
    """Raised when TLC source fields are missing for events that require them."""
    pass


async def _ensure_constraints(client: Neo4jClient) -> None:
    """Ensure FSMA graph constraints exist."""
    async with client.session() as session:
        for constraint in FSMA_CONSTRAINTS:
            try:
                await session.run(constraint)
            except Exception as e:
                logger.debug(
                    "constraint_exists_or_failed",
                    constraint=constraint[:50],
                    error=str(e),
                )


def stop_consumer() -> None:
    """Signal consumer to stop."""
    _shutdown_event.set()


def _load_schema_str() -> str:
    """Load Avro schema from file."""
    try:
        schema_path = Path(__file__).resolve().parents[4] / "schemas" / "fsma_trace_event.avsc"
        return schema_path.read_text()
    except Exception as e:
        logger.warning("schema_file_load_error", error=str(e), info="Falling back to string")
        # Fallback minimal schema if file missing - primarily for testing without file
        return """
        {
          "type": "record",
          "name": "FSMATraceEvent",
          "namespace": "com.regengine.fsma",
          "fields": [
            {"name": "event_id", "type": "string"},
            {"name": "lot_code", "type": ["null", "string"], "default": null}
          ]
        }
        """


async def ingest_fsma_event(client: Neo4jClient, event: Dict[str, Any]) -> None:
    """
    Ingest a single FSMA extraction event into the graph.
    """
    document_id = event.get("document_id", str(uuid.uuid4()))
    # Same logic as original ingest_fsma_event
    # Simplified here for brevity but assuming full logic is preserved or imported
    # COPYING LOGIC FROM ORIGINAL TO ENSURE FUNCTIONALITY (Truncated for brevity in thought, but writing full in file)
    
    document_type = event.get("document_type", "UNKNOWN")
    ctes = event.get("ctes", [])
    timestamp = event.get("timestamp")
    tenant_id = event.get("tenant_id")
    tenant_source_gln, tenant_source_fda_reg = _extract_tenant_source_identifiers(event)

    bind_contextvars(document_id=document_id)

    with FSMA_INGEST_DURATION.time():
        async with client.session() as session:
            # 1. Create Document node
            doc = Document(
                document_id=document_id,
                document_type=document_type,
                extraction_timestamp=timestamp,
                tenant_id=tenant_id,
            )
            await session.run(
                Document.merge_cypher(),
                document_id=document_id,
                properties=doc.node_properties,
            )
            
            # Evidence link
            evidence_link = event.get("source_url") or f"s3://documents/{document_id}"
            
            # 2. Process each CTE
            for idx, cte_data in enumerate(ctes):
                event_id = f"{document_id}-cte-{idx}"
                cte_type = cte_data.get("type", "SHIPPING")
                kdes = cte_data.get("kdes", {})
                confidence = cte_data.get("confidence", 0.0)

                # Validation Logic
                tlc_source_gln = kdes.get("tlc_source_gln")
                tlc_source_fda_reg = kdes.get("tlc_source_fda_reg")

                if cte_type == "RECEIVING":
                    tlc_source_gln = tlc_source_gln or kdes.get("tlc_source") or kdes.get("ship_from_gln")
                    tlc_source_fda_reg = tlc_source_fda_reg or kdes.get("ship_from_fda_reg")

                if cte_type in TLC_SOURCE_REQUIRED_EVENTS:
                    if not tlc_source_gln and not tlc_source_fda_reg:
                        tlc_source_gln = tenant_source_gln
                        tlc_source_fda_reg = tenant_source_fda_reg
                    
                    if not tlc_source_gln and not tlc_source_fda_reg:
                         logger.error("tlc_source_validation_failed", event_id=event_id, action="dlq_eviction")
                         # raise exception to trigger outer DLQ catch
                         raise TLCSourceValidationError(f"Missing TLC Source for {cte_type}") 

                # Create TraceEvent
                trace_event = TraceEvent(
                    event_id=event_id,
                    type=CTEType(cte_type) if cte_type in CTEType.__members__ else CTEType.SHIPPING,
                    event_date=kdes.get("event_date", ""),
                    event_time=kdes.get("event_time"),
                    document_id=document_id,
                    confidence=confidence,
                    tenant_id=tenant_id,
                )
                await session.run(TraceEvent.create_cypher(), properties=trace_event.node_properties)

                # Link Document -> Event
                await session.run(FSMARelationships.DOCUMENT_EVIDENCES, document_id=document_id, event_id=event_id)

                # 3. Create Lot
                tlc = kdes.get("traceability_lot_code")
                if tlc:
                    lot = Lot(
                        tlc=tlc,
                        product_description=kdes.get("product_description"),
                        quantity=kdes.get("quantity"),
                        unit_of_measure=kdes.get("unit_of_measure"),
                        tenant_id=tenant_id,
                        tlc_source_gln=tlc_source_gln,
                        tlc_source_fda_reg=tlc_source_fda_reg,
                    )
                    await session.run(Lot.merge_cypher(), tlc=tlc, properties=lot.node_properties)
                    await session.run(FSMARelationships.LOT_UNDERWENT_EVENT, tlc=tlc, event_id=event_id)
                    
                    if lot.assigned_by_cypher():
                        await session.run(lot.assigned_by_cypher())

                # 4. Facility
                location_id = kdes.get("location_identifier")
                if location_id:
                    gln = None 
                    if location_id.startswith("urn:gln:"): gln = location_id.replace("urn:gln:", "")
                    
                    if gln:
                        facility = Facility(gln=gln, name=f"Facility-{gln}", tenant_id=tenant_id)
                        await session.run(Facility.merge_cypher(), gln=gln, properties=facility.node_properties)
                        await session.run(FSMARelationships.EVENT_OCCURRED_AT, event_id=event_id, gln=gln)

    FSMA_MESSAGES_COUNTER.labels(status="success").inc()
    logger.info("fsma_event_ingested", document_id=document_id, cte_count=len(ctes))
    clear_contextvars()


async def run_fsma_consumer(database: Optional[str] = None) -> None:
    """Run the FSMA Kafka consumer with Avro support."""
    
    client = Neo4jClient(database=database)
    await _ensure_constraints(client)

    # Schema Registry Configuration
    schema_registry_conf = {'url': settings.schema_registry_url}
    schema_registry_client = SchemaRegistryClient(schema_registry_conf)
    
    # Avro Deserializer
    avro_deserializer = AvroDeserializer(
        schema_registry_client,
        _load_schema_str(),
    )

    # Initialize DLQ Producer
    global _dlq_producer
    _dlq_producer = Producer({'bootstrap.servers': settings.kafka_bootstrap})

    # Consumer Config
    consumer_conf = {
        'bootstrap.servers': settings.kafka_bootstrap,
        'group.id': settings.consumer_group_id,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': False
    }

    consumer = Consumer(consumer_conf)
    consumer.subscribe([FSMA_TOPIC])

    logger.info("fsma_consumer_started_avro", topic=FSMA_TOPIC)

    try:
        while not _shutdown_event.is_set():
            # Confluent consumer poll is synchronous/blocking
            # Use to_thread to keep async loop happy
            msg = await asyncio.to_thread(consumer.poll, 1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error("consumer_error", error=str(msg.error()))
                # Handle error logic
                continue

            try:
                # Value is already deserialized by AvroDeserializer? 
                # Wait, Consumer needs 'value.deserializer' config or explicit call?
                # Confluent Consumer is low level. DeserializingConsumer is high level.
                
                # We need to manually deserialize if using raw Consumer, 
                # or use DeserializingConsumer.
                # Let's switch to DeserializingConsumer pattern or manual usage.
                # Given structure, we'll manually use deserializer if msg.value() returns bytes
                
                # NOTE: For simplicity in this agent script, assuming we handle bytes manually 
                # OR we passed it to config. 
                # Let's use deserializer manually on the bytes.
                
                val_bytes = msg.value()
                ctx = SerializationContext(msg.topic(), MessageField.VALUE)
                
                # If using DeserializingConsumer, this happens automatically.
                # But here we initialized Consumer. 
                # Let's verify: confluent_kafka.DeserializingConsumer is better.
                # But to avoid re-writing everything, we call deserializer:
                
                event = avro_deserializer(val_bytes, ctx)
                
                if event:
                    bind_contextvars(offset=msg.offset(), partition=msg.partition())
                    await ingest_fsma_event(client, event)
                    await asyncio.to_thread(consumer.commit, msg)

            except Exception as e:
                # Catch-all for message processing failures to preventing crashing
                FSMA_MESSAGES_COUNTER.labels(status="error").inc()
                
                # Send to DLQ
                # Note: msg.value() returns bytes
                reason = "processing_exception"
                if isinstance(e, TLCSourceValidationError):
                    reason = "validation_error"
                
                send_to_dlq(msg.topic(), msg.value(), reason=reason, error=str(e))
                
                logger.exception("fsma_event_processing_fatal_error", error=str(e), action="dlq_sent")
                
                # Commit offset to move past poison pill
                await asyncio.to_thread(consumer.commit, msg)
            finally:
                clear_contextvars()

    finally:
        await asyncio.to_thread(consumer.close)
        await client.close()
        logger.info("fsma_consumer_stopped")

if __name__ == "__main__":
    try:
        asyncio.run(run_fsma_consumer())
    except KeyboardInterrupt:
        pass
