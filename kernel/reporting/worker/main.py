
import os
import sys
import logging
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from confluent_kafka import Consumer, KafkaError
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import StringDeserializer, SerializationContext, MessageField

# Service root for imports (prefer PYTHONPATH, fallback to relative)
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))

from worker.models import AuthorityDocument, Base
# Import shared schemas for GraphEvent parsing
try:
    from shared.schemas import GraphEvent, ExtractionPayload
    SHARED_SCHEMAS_AVAILABLE = True
except ImportError:
    GraphEvent = None
    ExtractionPayload = None
    SHARED_SCHEMAS_AVAILABLE = False

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("compliance-worker")

# Config
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
SCHEMA_REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")
TOPIC = os.environ.get("KAFKA_TOPIC_NORMALIZED", "ingest.normalized.v2")
TOPIC_GRAPH_UPDATE = os.environ.get("KAFKA_TOPIC_GRAPH_UPDATE", "graph.update")
GROUP_ID = "compliance-worker-group-phase3a"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://regengine:regengine@postgres:5432/regengine_admin")
SCHEMA_DIR = os.environ.get("SCHEMA_DIR", None)  # Explicit schema directory
HEALTH_FILE = os.environ.get("HEALTH_FILE", "/tmp/compliance-worker-healthy")

# DLQ tracking
_DLQ_ERROR_COUNT = 0
_DLQ_MAX_LOGGED = 100  # Max errors to log before throttling

# DB Setup
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _get_fresh_session():
    """Create a fresh DB session for per-batch processing."""
    return SessionLocal()

def _write_health_file():
    """Write health file for container liveness probes."""
    try:
        Path(HEALTH_FILE).write_text(datetime.now(timezone.utc).isoformat())
    except Exception:
        pass  # Best-effort

def load_schema(schema_name):
    # Prefer SCHEMA_DIR env var
    if SCHEMA_DIR:
        schema_path = os.path.join(SCHEMA_DIR, schema_name)
        if os.path.exists(schema_path):
            with open(schema_path, 'r', encoding='utf-8') as f:
                return f.read()
    # Fallback paths
    paths = [
        f"/app/schemas/{schema_name}",
        str(_SERVICE_ROOT.parent.parent / "schemas" / schema_name),
        f"schemas/{schema_name}"
    ]
    for p in paths:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                return f.read()
    raise FileNotFoundError(f"Schema {schema_name} not found (searched: SCHEMA_DIR={SCHEMA_DIR}, {paths})")

def process_event(event_data, db):
    logger.info(f"Processing event: {event_data.get('event_id')}")
    
    tenant_id = event_data.get("tenant_id")
    if not tenant_id:
        logger.warning("No tenant_id in event, skipping")
        return

    try:
        # Set tenant context for RLS (parameterized to prevent SQL injection)
        db.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)})
    except Exception as e:
        logger.warning(f"Could not set tenant context (might be superuser): {e}")
        db.rollback()

    source_url = event_data.get("source_url", "")
    
    # Check for existing document by HASH (Idempotency)
    doc_hash = event_data.get("document_hash")
    existing_hash_match = db.query(AuthorityDocument).filter_by(document_hash=doc_hash, tenant_id=tenant_id).first()
    
    # Check for existing document by URL (Versioning)
    # We only care about the currently 'active' one to supersede
    existing_url_match = db.query(AuthorityDocument).filter_by(
        original_file_path=source_url, 
        tenant_id=tenant_id, 
        status="active"
    ).first()

    authority_doc = None
    previous_doc = None

    if existing_hash_match:
        logger.info(f"Document {doc_hash} already exists (Hash Match). Using existing ID.")
        authority_doc = existing_hash_match
    else:
        # Determine Supersedes logic
        if existing_url_match and existing_url_match.document_hash != doc_hash:
            logger.info(f"New version detected for {source_url}. Superseding {existing_url_match.id}")
            previous_doc = existing_url_match
            # Mark old doc as superseded
            existing_url_match.status = "superseded"
        
        # Determine Issuer/Type (Simple heuristics)
        issuer = "Unknown"
        doc_type = "regulation"
        if "fda.gov" in source_url:
            issuer = "FDA"
            doc_type = "regulation"
        elif "monitor" in source_url: 
            issuer = "Internal"
            doc_type = "internal_policy"

        # Create Authority Document
        authority_doc = AuthorityDocument(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            document_code=f"DOC-{event_data.get('document_id')[:8]}", # Mock code
            document_name=os.path.basename(source_url) or "Untitled Regulation",
            document_type=doc_type,
            issuer_name=issuer,
            issuer_type="government",
            effective_date=datetime.now().date(), 
            document_hash=doc_hash,
            original_file_path=source_url,
            content_type="text/html",
            status="active",
            supersedes_document_id=previous_doc.id if previous_doc else None
        )
        db.add(authority_doc)
        db.commit()
        logger.info(f"Created AuthorityDocument {authority_doc.id}")

    # --- Phase 3a: Heuristic Fact Extraction ---
    # Always attempt extraction if regex matches
    if "fsma" in source_url.lower() or "traceability" in source_url.lower():
        logger.info("Detected FSMA 204 Content. Running heuristic extraction...")
        extract_fsma_facts(db, authority_doc, tenant_id, previous_doc)
        
def extract_fsma_facts(db, authority_doc, tenant_id, previous_doc=None):
    """
    Extracts Key Data Elements (KDEs) and Critical Tracking Events (CTEs) 
    using heuristic patterns for FSMA 204.
    Handles Fact Lineage if previous_doc is provided.
    """
    from worker.models import ExtractedFact 
    
    # 1. Fetch previous facts for lineage mapping
    previous_facts_map = {}
    if previous_doc:
        prev_facts = db.query(ExtractedFact).filter_by(
            authority_document_id=previous_doc.id,
            tenant_id=tenant_id
        ).order_by(ExtractedFact.version.desc()).all()
        for pf in prev_facts:
            # Map by Key if available, or name
            key = pf.fact_key or pf.fact_name
            previous_facts_map[key] = pf

    facts_to_create = [
        {
            "name": "Traceability Lot Code Assignment",
            "key": "FSMA_204_TLC_ASSIGNMENT",
            "description": "Must assign a Traceability Lot Code (TLC) when packing, shipping, or transforming food on the FTL.",
            "value": "Mandatory",
            "category": "obligation"
        },
        {
            "name": "Record Retention Period",
            "key": "FSMA_204_RETENTION_PERIOD",
            "description": "Records must be maintained for 24 hours (electronic sortable spreadsheet) upon request.",
            "value": "24 hours",
            "category": "constraint"
        },
        {
            "name": "Scope: Key Data Elements",
            "key": "FSMA_204_KDE_SCOPE",
            "description": "Records must contain Key Data Elements (KDEs) linked to Critical Tracking Events (CTEs).",
            "value": "KDE/CTE",
            "category": "definition"
        },
        {
             "name": "Critical Tracking Events",
             "key": "FSMA_204_CTE_LIST",
             "description": "Events including growing, receiving, transforming, creating, and shipping.",
             "value": "List",
             "category": "scope"
        },
        {
            "key": "Compliance Date",
            "name": "Compliance Date",
            "description": "The date by which covered entities must be in compliance.",
            "category": "obligation",
            "value_type": "string",
            "value": "January 20, 2026", # V1 Baseline
            "confidence": 0.99
        }
    ]
    
    for fact_data in facts_to_create:
        # Check if exists in Current Doc
        existing_fact = db.query(ExtractedFact).filter_by(
            authority_document_id=authority_doc.id, 
            fact_name=fact_data["name"],
            tenant_id=tenant_id
        ).first()
        
        if existing_fact:
            continue

        # Lineage Logic
        version = 1
        previous_fact_id = None
        
        pkey = fact_data.get("key", fact_data["name"])
        # Determine Global Version
        from sqlalchemy import func
        global_max = db.query(func.max(ExtractedFact.version)).filter_by(
            tenant_id=tenant_id, 
            fact_key=pkey
        ).scalar() or 0
        version = global_max + 1
        
        # Check if exists (idempotency by key/version)
        # Since we just calculated version = max + 1, it won't exist unless race condition
        # But we still check logic
        
        previous_fact_id = None
        if pkey in previous_facts_map:
            prev_fact = previous_facts_map[pkey]
            previous_fact_id = prev_fact.id
          # Supersede old fact
            prev_fact.is_current = False
            # We don't change status to 'inactive', just is_current=False usually implies history

        # Compute Fact Hash
        import hashlib
        import json
        
        # Serialize Value
        val_str = ""
        if fact_data.get("value") is not None:
             val_str = str(fact_data.get("value"))
        
        hash_input = f"{fact_data['key']}|string|{val_str}|{{}}|None|None"
        # Note: logic above assumes validity_conditions={}, source_page/section=None for this heuristic
        fact_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
            
        fact = ExtractedFact(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            authority_document_id=authority_doc.id,
            fact_key=fact_data["key"],
            fact_name=fact_data["name"],
            fact_description=fact_data["description"],
            fact_category=fact_data["category"],
            
            fact_value_type="string",
            fact_value_string=fact_data["value"],
            
            validity_conditions={},
            fact_hash=fact_hash,

            extraction_confidence=0.95, 
            extraction_method="heuristic_v1",
            
            is_current=True,
            version=version,
            previous_fact_id=previous_fact_id
        )
        db.add(fact)
    
    db.commit()
    logger.info(f"Extracted facts for {authority_doc.id}")

def process_nlp_event(data, db):
    from worker.models import ExtractedFact, AuthorityDocument
    import hashlib
    
    logger.info(f"Processing NLP event for doc {data.get('document_id')}")
    logger.info(f"Full NLP Data: {data}")
    
    extraction_payload = data.get("extraction", {})
    logger.info(f"Extraction Payload Type: {type(extraction_payload)}")
    if isinstance(extraction_payload, dict):
         logger.info(f"Extraction Payload Keys: {extraction_payload.keys()}")
    elif isinstance(extraction_payload, list):
         logger.info(f"Extraction Payload is LIST of length {len(extraction_payload)}")
         
    # Fallback logic to find entities
    if isinstance(extraction_payload, list):
        entities = extraction_payload
    else:
        entities = extraction_payload.get("entities", [])
        # Try finding in attributes if not found
        if not entities:
            entities = extraction_payload.get("attributes", {}).get("entities", [])
            
    logger.info(f"Processing {len(entities)} extracted entities...")

    for entity in entities:
        if entity.get("type") == "REGULATORY_DATE":
            attrs = entity.get("attrs", {})
            # We look for "Compliance Date" key or implied context
            # Log snippet showed 'key': 'Compliance Date'
            if attrs.get("key") == "Compliance Date":
                from sqlalchemy import func
                doc_hash = data.get("doc_hash")
                
                # Find AuthorityDocument
                auth_doc = db.query(AuthorityDocument).filter_by(document_hash=doc_hash).first()
                if not auth_doc:
                    logger.warning(f"No AuthorityDocument found for NLP event {doc_hash}")
                    continue

                date_value = attrs.get("value") or entity.get("text")
                val_str = str(date_value or "")
                
                logger.info(f"Found Compliance Date candidate: {val_str}")

                fact_key = "Compliance Date"
                existing = db.query(ExtractedFact).filter_by(
                    authority_document_id=auth_doc.id,
                    fact_key=fact_key,
                    is_current=True
                ).first()
                
                if existing:
                    if str(date_value or "") != (existing.fact_value_string or ""):
                        logger.info(f"Updating Compliance Date from {existing.fact_value_string} to {val_str}")
                        existing.is_current = False
                    else:
                        logger.info("Compliance Date fact already exists and matches")
                        continue

                # Lineage Logic
                previous_fact_id = None
                if auth_doc.supersedes_document_id:
                     prev_fact = db.query(ExtractedFact).filter_by(
                         authority_document_id=auth_doc.supersedes_document_id,
                         fact_key=fact_key
                     ).order_by(ExtractedFact.version.desc()).first()
                     if prev_fact:
                         previous_fact_id = prev_fact.id
                         # Supersede old fact
                         prev_fact.is_current = False
                         logger.info(f"Linked new fact to previous fact {prev_fact.id}")

                # Determine Global Version to avoid collision
                global_max = db.query(func.max(ExtractedFact.version)).filter_by(
                    tenant_id=auth_doc.tenant_id, 
                    fact_key=fact_key
                ).scalar() or 0
                version = global_max + 1

                # Create Fact
                hash_input = f"{fact_key}|string|{val_str}|{{}}|None|None"
                fact_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
                
                fact = ExtractedFact(
                    id=uuid.uuid4(),
                    tenant_id=auth_doc.tenant_id,
                    authority_document_id=auth_doc.id,
                    fact_key=fact_key,
                    fact_name="Compliance Date",
                    fact_description="The date by which covered entities must be in compliance.",
                    fact_category="obligation",
                    fact_value_type="string",
                    fact_value_string=val_str,
                    validity_conditions={},
                    fact_hash=fact_hash,
                    extraction_confidence=entity.get("confidence_score", 0.99), # entity confidence?
                    extraction_method="nlp_v1",
                    is_current=True,
                    version=version,
                    previous_fact_id=previous_fact_id
                )
                db.add(fact)
                db.commit()
                logger.info(f"Created Compliance Date fact: {val_str}")

def main():
    global _DLQ_ERROR_COUNT
    logger.info("Starting Compliance Worker...")
    
    # Load Schema
    try:
        schema_str = load_schema("normalized_document.avsc")
    except Exception as e:
        logger.error(f"Failed to load schema: {e}")
        sys.exit(1)

    schema_registry_client = SchemaRegistryClient({'url': SCHEMA_REGISTRY_URL})
    avro_deserializer = AvroDeserializer(schema_registry_client, schema_str)
    string_deserializer = StringDeserializer('utf_8')

    consumer = Consumer({
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'group.id': GROUP_ID,
        'auto.offset.reset': 'earliest'
    })

    # Subscribe to all relevant topics including graph.update for NLP outputs
    topics_list = [TOPIC, "nlp.extracted", TOPIC_GRAPH_UPDATE]
    consumer.subscribe(topics_list)
    logger.info(f"Listening on topics: {topics_list}...")

    # Write initial health file
    _write_health_file()
    poll_count = 0

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                poll_count += 1
                # Update health file every 30 polls (~30s)
                if poll_count % 30 == 0:
                    _write_health_file()
                continue
            if msg.error():
                logger.error(f"Consumer error: {msg.error()}")
                continue
            
            # Per-batch DB session for resilience
            db = _get_fresh_session()
            try:
                topic = msg.topic()
                if topic == "nlp.extracted":
                    # NLP events are JSON (legacy format)
                    val = msg.value()
                    if val:
                         data = json.loads(val.decode('utf-8'))
                         process_nlp_event(data, db)
                elif topic == TOPIC_GRAPH_UPDATE:
                    # GraphEvent format from NLP service (new format)
                    val = msg.value()
                    if val:
                        data = json.loads(val.decode('utf-8'))
                        logger.info(f"Received GraphEvent from graph.update: event_type={data.get('event_type')}")
                        # Parse as GraphEvent if shared schema is available
                        if GraphEvent is not None:
                            try:
                                graph_event = GraphEvent.model_validate(data)
                                # Extract entities from ExtractionPayload attributes
                                extraction = graph_event.extraction
                                entities = extraction.attributes.get("entities", [])
                                if entities:
                                    logger.info(f"Processing {len(entities)} entities from GraphEvent")
                                    process_nlp_event({
                                        "document_id": graph_event.document_id,
                                        "doc_hash": graph_event.doc_hash,
                                        "tenant_id": str(graph_event.tenant_id) if graph_event.tenant_id else None,
                                        "extraction": {"entities": entities}
                                    }, db)
                            except Exception as e:
                                logger.warning(f"GraphEvent validation failed (DEBT-023): {e}, using raw dict fallback")
                                process_nlp_event(data, db)
                        else:
                            # Fallback to raw dict parsing
                            process_nlp_event(data, db)
                else:
                    # Ingestion events are JSON now (patched in Step 167)
                    val = msg.value()
                    if val:
                        try:
                            # Try JSON first
                            event = json.loads(val.decode('utf-8'))
                            process_event(event, db)
                        except json.JSONDecodeError:
                             # Fallback to Avro if needed (or log error)
                             logger.warning("Failed to decode as JSON, checking Avro...")
                             event = avro_deserializer(msg.value(), SerializationContext(msg.topic(), MessageField.VALUE))
                             if event:
                                 process_event(event, db)

            except Exception as e:
                _DLQ_ERROR_COUNT += 1
                if _DLQ_ERROR_COUNT <= _DLQ_MAX_LOGGED:
                    logger.error(
                        f"Processing error (DLQ #{_DLQ_ERROR_COUNT}): {e}",
                        exc_info=True,
                        extra={
                            "topic": msg.topic() if msg else "unknown",
                            "partition": msg.partition() if msg else -1,
                            "offset": msg.offset() if msg else -1,
                        },
                    )
                db.rollback()
            finally:
                db.close()
                
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        # Clean up health file
        try:
            Path(HEALTH_FILE).unlink(missing_ok=True)
        except Exception:
            pass

if __name__ == "__main__":
    main()
