"""API routes for the ingestion service."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
import time
import uuid
from datetime import datetime, timezone
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import requests
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, BackgroundTasks, Body
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from confluent_kafka.admin import AdminClient
from requests import Response

# Add shared module to path
# In Docker: shared is at /app/shared/, service is at /app/
# Add shared module to path
# In Docker: shared is at /app/shared/, service is at /app/
# sys.path.insert(0, "/app/shared")
# sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))

from shared.auth import APIKey, require_api_key, verify_jurisdiction_access

from .config import get_settings
from .kafka_utils import send
from .models import IngestRequest, DirectIngestRequest, NormalizedDocument, NormalizedEvent
from .normalization import normalize_document
from .s3_utils import put_bytes, put_json
from .scrapers.state_generic import StateRegistryScraper as GenericStateScraper

# Import advanced ingestion framework components
from regengine_ingestion.parsers import create_default_registry
from regengine_ingestion.storage.database import DatabaseManager
from regengine_ingestion.config import DatabaseConfig, DatabaseConfig as FrameworkDatabaseConfig
from regengine_ingestion.audit import AuditLogger
from regengine_ingestion.models import (
    IngestionJob, JobStatus, Document, DocumentType, 
    DocumentHash as FrameworkDocumentHash, SourceMetadata as FrameworkSourceMetadata
)
import hashlib
from uuid import UUID
import uuid

PARSER_REGISTRY = create_default_registry()

def get_db_manager() -> Optional[DatabaseManager]:
    """Get initialized database manager from environment."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        return None
    
    try:
        # Manual parsing of postgresql+psycopg://regengine:regengine@postgres:5432/regengine_admin
        url = db_url.replace("postgresql+psycopg://", "").replace("postgresql://", "")
        if "@" in url:
            auth, rest = url.split("@")
            user, password = auth.split(":")
            host_port, dbname = rest.split("/")
            if ":" in host_port:
                host, port = host_port.split(":")
            else:
                host = host_port
                port = 5432
        else:
            # Fallback for simple formats if any
            return None
            
        config = FrameworkDatabaseConfig(
            host=host,
            port=int(port),
            database=dbname,
            user=user,
            password=password
        )
        logger.info("db_config_parsed", host=host, dbname=dbname, user=user)
        manager = DatabaseManager(config)
        manager.connect()
        logger.info("db_connected_successfully")
        return manager
    except Exception as e:
        logger.error("db_init_failed", error=str(e), url=db_url)
        return None

from .pipeline import ScraperPipeline
from .scrapers.state_generic import StateRegistryScraper as GenericStateScraper
from .scraper_job import run_state_scrape_job, run_generic_scrape_job

logger = structlog.get_logger("ingestion")
router = APIRouter()

GENERIC_STATE_SCRAPER = GenericStateScraper()
_PIPELINE = ScraperPipeline()


@router.post("/v1/scrape/nydfs", status_code=202)
async def scrape_nydfs(
    url: str,
    background_tasks: BackgroundTasks,
    api_key=Depends(require_api_key)
):
    # Entitlement gating for US-NY
    verify_jurisdiction_access(api_key, "US-NY")

    # Use the specific NYDFS adaptor if available, otherwise fallback to generic
    adaptor = ADAPTORS.get("nydfs")
    if adaptor:
        background_tasks.add_task(
            run_state_scrape_job,
            adaptor_name="nydfs",
            adaptor_instance=adaptor,
            url=url,
            jurisdiction_code="US-NY",
            tenant_id=api_key.tenant_id
        )
        return {"status": "accepted", "message": "NYDFS scrape job started"}

    background_tasks.add_task(
        run_generic_scrape_job,
        url=url,
        jurisdiction_code="US-NY",
        tenant_id=api_key.tenant_id
    )
    return {"status": "accepted", "message": "Generic scrape job started"}


@router.post("/v1/scrape/cppa", status_code=202)
async def scrape_cppa(
    url: str,
    background_tasks: BackgroundTasks,
    api_key=Depends(require_api_key)
):
    # Entitlement gating for US-CA
    verify_jurisdiction_access(api_key, "US-CA")
    
    # Use CPPA adaptor for specific headers/logic if needed
    adaptor = ADAPTORS.get("cppa")
    if adaptor:
        background_tasks.add_task(
            run_state_scrape_job,
            adaptor_name="cppa",
            adaptor_instance=adaptor,
            url=url,
            jurisdiction_code="US-CA",
            tenant_id=api_key.tenant_id
        )
        return {"status": "accepted", "message": "CPPA scrape job started"}

    background_tasks.add_task(
        run_generic_scrape_job,
        url=url,
        jurisdiction_code="US-CA",
        tenant_id=api_key.tenant_id
    )
    return {"status": "accepted", "message": "Generic scrape job started"}


ALLOWED_SCHEMES = {"https", "http"}
ALLOWED_PORTS = {80, 443, 8080, 8443}
PROHIBITED_HOSTS = {"localhost", "127.0.0.1"}
PROHIBITED_NETWORKS = [
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"),
    ip_network("::1/128"),
    ip_network("fc00::/7"),
]
MAX_PAYLOAD_BYTES = 25 * 1024 * 1024

REQUEST_COUNTER = Counter(
    "ingestion_requests_total", "Total ingestion requests", ["endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "ingestion_request_latency_seconds", "Ingestion request latency", ["endpoint"]
)
KAFKA_COUNTER = Counter(
    "ingestion_kafka_messages_total", "Kafka messages produced", ["topic"]
)

# --- State adaptor imports (scaffold) ---
from .scrapers.state_adaptors.base import (
    FetchedItem,
    Source,
)
from .scrapers.state_adaptors.base import StateRegistryScraper as AdaptorRegistryScraper
from .scrapers.state_adaptors.cppa import CPPAScraper
from .scrapers.state_adaptors.fl_rss import FloridaRSSScraper
from .scrapers.state_adaptors.nj_gaming import NewJerseyGamingScraper
from .scrapers.state_adaptors.nv_gaming import NevadaGamingScraper
from .scrapers.state_adaptors.nydfs import NYDFSScraper
from .scrapers.state_adaptors.tx_rss import TexasRegistryScraper
from .scrapers.state_adaptors.google_discovery import GoogleDiscoveryScraper
from .scrapers.state_adaptors.fda_enforcement import FDAEnforcementScraper

ADAPTORS: dict[str, AdaptorRegistryScraper] = {
    "nydfs": NYDFSScraper(),
    "cppa": CPPAScraper(),
    "nv_gaming": NevadaGamingScraper(),
    "nj_gaming": NewJerseyGamingScraper(),
    "tx_rss": TexasRegistryScraper(),
    "fl_rss": FloridaRSSScraper(),
    "google_discovery": GoogleDiscoveryScraper(),
    "fda_warnings": FDAEnforcementScraper(),
}


@router.get("/health")
def health() -> dict[str, str]:
    """Health-check endpoint."""
    settings = get_settings()
    try:
        admin_client = AdminClient(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "ingestion-healthcheck",
            }
        )
        admin_client.list_topics(timeout=5)
        return {"status": "healthy", "kafka": "available"}
    except Exception as exc:
        logger.error("ingestion_health_kafka_unavailable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="Kafka unavailable or unreachable"
        ) from exc


@router.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _verify_api_key(x_api_key: Optional[str] = Header(None)) -> None:
    """Verify API key if configured."""
    settings = get_settings()
    if settings.api_key is not None:
        if not x_api_key or x_api_key != settings.api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.post("/scrape/{adaptor}")
def scrape_registry(
    adaptor: str,
    api_key: APIKey = Depends(require_api_key),
) -> dict:
    """Run a state registry adaptor and enqueue normalized events.

    Placeholder implementation: lists sources and returns their metadata without network fetch.
    """
    if adaptor not in ADAPTORS:
        raise HTTPException(status_code=404, detail="Unknown adaptor")

    scraper = ADAPTORS[adaptor]
    sources: list[dict] = []
    allowed = set(api_key.allowed_jurisdictions or [])
    
    # Run in thread pool to avoid blocking
    # Ideally should use a background task (Celery/Arq) for full batch
    # keeping it simple but functional for now
    
    results = []
    
    for src in scraper.list_sources():
        if src.jurisdiction_code and src.jurisdiction_code not in allowed:
            continue
            
        try:
            # 1. Fetch using adaptor logic (headers, auth, etc)
            fetched = scraper.fetch(src)
            
            if not fetched.content_bytes:
                logger.warning("scrape_empty_content", source=src.url)
                continue

            # 2. Process via Pipeline
            event = _PIPELINE.process_content(
                content=fetched.content_bytes,
                content_type=fetched.content_type,
                jurisdiction_code=src.jurisdiction_code,
                source_url=src.url,
                tenant_id=api_key.tenant_id
            )
            
            if event:
                results.append(event)
            
        except Exception as e:
            logger.error("scrape_source_failed", url=src.url, error=str(e))
            # Continue to next source
            continue

    return {"adaptor": adaptor, "count": len(results), "sources": results}


def _process_and_emit(
    raw_bytes: bytes,
    url_str: str,
    source_system: str,
    tenant_id: str,
    content_type: str,
    doc_metadata: Optional[Dict] = None,
    job_id: Optional[str] = None,
    audit_logger: Optional[AuditLogger] = None,
    db_manager: Optional[DatabaseManager] = None,
    vertical: str = "unknown"
) -> NormalizedEvent:
    """Shared document processing, storage, and emission logic."""
    settings = get_settings()
    
    # 1. Size enforcement
    _enforce_size_limit(raw_bytes)

    # 1.5. Cryptographic Hashing (Early for Deduplication)
    content_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    content_sha512 = hashlib.sha512(raw_bytes).hexdigest()

    # 1.6. Deduplication Check (Phase 4)
    if db_manager:
        existing = db_manager.get_document_by_hash(content_sha256)
        if existing:
            document_id = str(existing['id'])
            normalized_uri = existing['storage_key']
            
            if audit_logger:
                audit_logger.log_skip(document_id, "duplicate")
            
            # Return event with existing paths marked as duplicate
            event = NormalizedEvent(
                event_id=str(uuid.uuid4()),
                document_id=document_id,
                document_hash=content_sha256,
                tenant_id=tenant_id,
                source_system=source_system,
                source_url=url_str,
                raw_s3_path="skipped://duplicate",
                normalized_s3_path=normalized_uri,
                timestamp=datetime.now(timezone.utc),
                content_sha256=content_sha256,
                is_duplicate=True
            )
            
            # Emit deduplication event to Kafka
            try:
                send(
                    get_settings().kafka_topic_normalized,
                    event.model_dump(mode="json"),
                    key=f"{document_id}:{content_sha256}",
                )
            except Exception as e:
                logger.warning("kafka_dedup_emit_failed", error=str(e))
                
            return event

    # 2. Enhanced Parsing
    parsed_text, parser_name = PARSER_REGISTRY.parse(raw_bytes, content_type, metadata=doc_metadata)
    
    text_sha256 = None
    text_sha512 = None
    if parsed_text:
        text_bytes = parsed_text.encode('utf-8')
        text_sha256 = hashlib.sha256(text_bytes).hexdigest()
        text_sha512 = hashlib.sha512(text_bytes).hexdigest()
    
    # 4. Normalization Structure
    raw_json = None
    if "json" in content_type.lower():
        try:
            raw_json = json.loads(raw_bytes)
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug("json_parse_skipped", url=url_str, error=str(e))
            
    normalized, document_id, _ = normalize_document(
        raw_json, raw_bytes, url_str, content_type
    )
    
    # 5. Enrich with metadata
    normalized["parsed_text"] = parsed_text
    normalized["parser_used"] = parser_name
    normalized["parse_metadata"] = {**(doc_metadata or {})}
    normalized["content_sha256"] = content_sha256
    normalized["content_sha512"] = content_sha512
    normalized["text_sha256"] = text_sha256
    normalized["text_sha512"] = text_sha512

    # 6. Storage S3
    timestamp = datetime.now(timezone.utc)
    event_id = str(uuid.uuid4())
    raw_extension = _detect_extension(content_type)
    raw_key = f"raw/{document_id}/{event_id}.{raw_extension}"
    normalized_key = f"normalized/{content_sha256}/current.json"
    normalized_alias_key = f"normalized/by-document-id/{document_id}/current.json"

    raw_uri = put_bytes(settings.raw_bucket, raw_key, raw_bytes)
    normalized_payload = NormalizedDocument(**normalized)
    normalized_uri = put_json(
        settings.processed_bucket,
        normalized_key,
        normalized_payload.model_dump(mode="json"),
    )
    put_json(settings.processed_bucket, normalized_alias_key, normalized_payload.model_dump(mode="json"))

    # 7. Audit Trail (Phase 3)
    if audit_logger:
        audit_logger.log_parse(document_id, "success", parser_name)
        audit_logger.log_store(document_id, "success", normalized_uri)

    # 7.5 Store in Database (Phase 4)
    if db_manager:
        try:
            # Generate a valid UUID from the document_id (which is usually a hash)
            # Use UUID v5 for deterministic UUID from the hash string
            doc_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, document_id))
            
            doc = Document(
                id=doc_uuid,
                tenant_id=tenant_id,
                title=normalized.get("title") or Path(url_str).name or "Untitled",
                source_type="url",
                document_type=DocumentType.REGULATION,
                vertical=vertical,
                hash=FrameworkDocumentHash(
                    content_sha256=content_sha256,
                    content_sha512=content_sha512,
                    text_sha256=text_sha256,
                    text_sha512=text_sha512
                ),
                source_metadata=FrameworkSourceMetadata(
                    source_url=url_str,
                    fetch_timestamp=timestamp
                ),
                text=parsed_text,
                text_length=len(parsed_text) if parsed_text else 0,
                storage_key=normalized_uri,
                content_type=content_type,
                content_length=len(raw_bytes)
            )
            db_manager.insert_document(doc)
        except Exception as db_exc:
            logger.warning("document_db_insert_failed", error=str(db_exc))

    # 8. Kafka Emission
    event = NormalizedEvent(
        event_id=event_id,
        document_id=document_id,
        document_hash=content_sha256,
        tenant_id=tenant_id,
        source_system=source_system,
        source_url=url_str,
        raw_s3_path=raw_uri,
        normalized_s3_path=normalized_uri,
        timestamp=timestamp,
        content_sha256=content_sha256,
    )

    try:
        send(
            settings.kafka_topic_normalized,
            event.model_dump(mode="json"),
            key=f"{document_id}:{content_sha256}",
        )
    except Exception as kafka_exc:
        logger.warning("kafka_publish_failed", document_id=document_id, error=str(kafka_exc))
    
    return event


@router.post("/v1/ingest", response_model=NormalizedEvent)
async def ingest_direct(
    payload: DirectIngestRequest = Body(...),
    api_key: APIKey = Depends(require_api_key),
) -> NormalizedEvent:
    """Ingest a single document directly from text/bytes."""
    endpoint = "ingest_direct"
    start_time = time.perf_counter()
    tenant_id = api_key.tenant_id or "00000000-0000-0000-0000-000000000000"
    job_id = str(uuid.uuid4())
    url_str = payload.source_url or "manual://direct"

    logger.info("ingest_direct_request", tenant_id=tenant_id, job_id=job_id)
    
    db_manager = get_db_manager()
    audit_logger = None
    if db_manager:
        db_manager.connect()
        db_manager.set_tenant_context(tenant_id)
        audit_logger = AuditLogger(job_id, db_connection=db_manager)
        job = IngestionJob(
            job_id=job_id,
            vertical=payload.vertical or "unknown",
            source_type="direct",
            status=JobStatus.RUNNING,
            started_at=datetime.utcnow(),
            config={"source_url": url_str}
        )
        try:
            db_manager.insert_job(job)
        except Exception as e:
            logger.error("job_db_init_failed", job_id=job_id, error=str(e))

    try:
        content = payload.text.encode("utf-8") if payload.text else b""
        
        event = _process_and_emit(
            raw_bytes=content,
            url_str=url_str,
            source_system=payload.source_system,
            tenant_id=tenant_id,
            content_type="text/plain",
            job_id=job_id,
            audit_logger=audit_logger,
            db_manager=db_manager,
            vertical=payload.vertical or "unknown"
        )
        
        if db_manager:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.documents_processed = 1
            job.documents_succeeded = 1
            db_manager.update_job(job)

        REQUEST_COUNTER.labels(endpoint=endpoint, status="200").inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.perf_counter() - start_time)
        return event
    except Exception as exc:
        logger.exception("ingest_direct_failed", job_id=job_id, error=str(exc))
        if db_manager:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db_manager.update_job(job)
        logger.exception("ingestion_error", error=str(exc)); raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/v1/ingest/url", response_model=NormalizedEvent)
async def ingest_url(
    payload: IngestRequest,
    api_key: APIKey = Depends(require_api_key),
) -> NormalizedEvent:
    """Ingest a single document from a URL."""
    url_str = str(payload.url)
    endpoint = "ingest_url"
    start_time = time.perf_counter()
    tenant_id = api_key.tenant_id or "00000000-0000-0000-0000-000000000000"
    job_id = str(uuid.uuid4())
    
    # Check entitlement
    allowed_jurisdictions = api_key.allowed_jurisdictions or []
    # Simple check: if it's a gov URL, check entitlement
    if ".gov" in url_str.lower() and "US" not in allowed_jurisdictions:
        raise HTTPException(status_code=403, detail="Access to government URLs requires entitlement")

    logger.info("ingest_url_request", url=url_str, tenant_id=tenant_id, job_id=job_id)
    
    db_manager = get_db_manager()
    audit_logger = None
    if db_manager:
        db_manager.connect()
        db_manager.set_tenant_context(tenant_id)
        audit_logger = AuditLogger(job_id, db_connection=db_manager)
        job = IngestionJob(
            job_id=job_id,
            vertical=payload.vertical or "unknown",
            source_type="url",
            status=JobStatus.RUNNING,
            started_at=datetime.utcnow(),
            config={"url": url_str}
        )
        try:
            db_manager.insert_job(job)
        except Exception as e:
            logger.error("job_db_init_failed", job_id=job_id, error=str(e))

    try:
        response = await asyncio.to_thread(_fetch, url_str)
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        
        if audit_logger:
            audit_logger.log_fetch(url_str, "success", http_status=response.status_code)

        event = _process_and_emit(
            raw_bytes=response.content,
            url_str=url_str,
            source_system=payload.source_system,
            tenant_id=tenant_id,
            content_type=content_type,
            job_id=job_id,
            audit_logger=audit_logger,
            db_manager=db_manager,
            vertical=payload.vertical or "unknown"
        )
        
        if db_manager:
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.documents_processed = 1
            job.documents_succeeded = 1
            db_manager.update_job(job)

        REQUEST_COUNTER.labels(endpoint=endpoint, status="200").inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.perf_counter() - start_time)
        return event
    except HTTPException as exc:
        if audit_logger:
            audit_logger.log_fetch(url_str, "failure", error=str(exc.detail))
        if db_manager:
            job.status = JobStatus.FAILED
            job.error_message = str(exc.detail)
            job.completed_at = datetime.utcnow()
            db_manager.update_job(job)
        REQUEST_COUNTER.labels(endpoint=endpoint, status=str(exc.status_code)).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.perf_counter() - start_time)
        raise
    except Exception as exc:
        if audit_logger:
            audit_logger.log_fetch(url_str, "failure", error=str(exc))
        if db_manager:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db_manager.update_job(job)
        logger.exception("ingest_unexpected_error", error=str(exc))
        REQUEST_COUNTER.labels(endpoint=endpoint, status="500").inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(time.perf_counter() - start_time)
        raise HTTPException(status_code=500, detail="Ingestion failed") from exc
    finally:
        if db_manager:
            db_manager.close()


# === FEDERAL SOURCE ENDPOINTS ===

from .models import FederalRegisterIngestRequest, ECFRIngestRequest, FDAIngestRequest
from regengine_ingestion.sources import FederalRegisterAdapter, ECFRAdapter, FDAAdapter

async def _run_adapter_ingest(adapter, vertical, tenant_id, source_system, job_id, **kwargs):
    """Background task to run a source adapter and process all findings."""
    db_manager = get_db_manager()
    audit_logger = None
    
    # Ensure tenant_id is a valid UUID
    tenant_id = tenant_id or "00000000-0000-0000-0000-000000000000"
    
    if db_manager:
        audit_logger = AuditLogger(job_id, db_connection=db_manager)
        
        # Initialize job record
        job = IngestionJob(
            job_id=job_id,
            vertical=vertical,
            source_type=source_system,
            status=JobStatus.RUNNING,
            started_at=datetime.utcnow(),
            config=kwargs
        )
        try:
            db_manager.insert_job(job)
        except Exception as e:
            logger.error("job_db_init_failed", job_id=job_id, error=str(e))

    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    try:
        for content, source_metadata, doc_metadata in adapter.fetch_documents(vertical=vertical, **kwargs):
            job_id_param = job_id
            count += 1
            if audit_logger:
                audit_logger.log_fetch(source_metadata.source_url, "success")
                
            try:
                event = _process_and_emit(
                    raw_bytes=content,
                    url_str=source_metadata.source_url,
                    source_system=source_system,
                    tenant_id=tenant_id,
                    content_type=source_metadata.http_headers.get("Content-Type", "application/octet-stream"),
                    doc_metadata=doc_metadata,
                    job_id=job_id,
                    audit_logger=audit_logger,
                    db_manager=db_manager,
                    vertical=vertical
                )
                if event.is_duplicate:
                    skipped_count += 1
                else:
                    success_count += 1
            except Exception as e:
                failed_count += 1
                if audit_logger:
                    audit_logger.log("ingest", "document", status="failure", error=str(e), details={"url": source_metadata.source_url})
                logger.error("federal_ingest_item_failed", url=source_metadata.source_url, error=str(e))
        
        logger.info("federal_ingest_completed", source=adapter.get_source_name(), count=count)
        
        if db_manager:
            # Update job status
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.documents_processed = count
            job.documents_succeeded = success_count
            job.documents_failed = failed_count
            job.documents_skipped = skipped_count
            db_manager.update_job(job)
            
    except Exception as e:
        logger.error("federal_ingest_job_failed", source=adapter.get_source_name(), error=str(e))
        if db_manager:
            job = IngestionJob(
                job_id=job_id,
                vertical=vertical,
                source_type=source_system,
                status=JobStatus.FAILED,
                completed_at=datetime.utcnow(),
                error_message=str(e),
                documents_processed=count,
                documents_succeeded=success_count,
                documents_failed=failed_count
            )
            db_manager.update_job(job)
    finally:
        if db_manager:
            db_manager.close()


@router.post("/v1/ingest/federal-register", status_code=202)
async def ingest_federal_register(
    payload: FederalRegisterIngestRequest,
    background_tasks: BackgroundTasks,
    api_key: APIKey = Depends(require_api_key)
):
    """Ingest documents from Federal Register API."""
    # Gating
    allowed = set(api_key.allowed_jurisdictions or [])
    if "US" not in allowed:
        raise HTTPException(status_code=403, detail="Access to federal regulations requires entitlement")

    adapter = FederalRegisterAdapter(user_agent="RegEngine/1.0")
    job_id = str(uuid.uuid4())
    background_tasks.add_task(
        _run_adapter_ingest,
        adapter=adapter,
        vertical=payload.vertical,
        tenant_id=api_key.tenant_id,
        source_system="federal_register_api",
        job_id=job_id,
        max_documents=payload.max_documents,
        date_from=payload.date_from,
        agencies=payload.agencies
    )
    return {"status": "accepted", "job_id": job_id, "message": "Federal Register ingestion started"}


@router.post("/v1/ingest/ecfr", status_code=202)
async def ingest_ecfr(
    payload: ECFRIngestRequest,
    background_tasks: BackgroundTasks,
    api_key: APIKey = Depends(require_api_key)
):
    """Ingest documents from eCFR API."""
    allowed = set(api_key.allowed_jurisdictions or [])
    if "US" not in allowed:
        raise HTTPException(status_code=403, detail="Access to federal regulations requires entitlement")

    adapter = ECFRAdapter(user_agent="RegEngine/1.0")
    job_id = str(uuid.uuid4())
    background_tasks.add_task(
        _run_adapter_ingest,
        adapter=adapter,
        vertical=payload.vertical,
        tenant_id=api_key.tenant_id,
        source_system="ecfr_api",
        job_id=job_id,
        cfr_title=payload.cfr_title,
        cfr_part=payload.cfr_part
    )
    return {"status": "accepted", "job_id": job_id, "message": "eCFR ingestion started"}


@router.post("/v1/ingest/fda", status_code=202)
async def ingest_fda(
    payload: FDAIngestRequest,
    background_tasks: BackgroundTasks,
    api_key: APIKey = Depends(require_api_key)
):
    """Ingest documents from openFDA API."""
    allowed = set(api_key.allowed_jurisdictions or [])
    if "US" not in allowed:
        raise HTTPException(status_code=403, detail="Access to federal regulations requires entitlement")

    adapter = FDAAdapter(api_key=None, user_agent="RegEngine/1.0")
    job_id = str(uuid.uuid4())
    background_tasks.add_task(
        _run_adapter_ingest,
        adapter=adapter,
        vertical=payload.vertical,
        tenant_id=api_key.tenant_id,
        source_system="openfda_api",
        job_id=job_id,
        max_documents=payload.max_documents
    )
    return {"status": "accepted", "job_id": job_id, "message": "FDA ingestion started"}


@router.get("/v1/ingest/sources")
async def list_sources(api_key: APIKey = Depends(require_api_key)):
    """List available source adapters and their capabilities."""
    return {
        "sources": [
            {
                "id": "federal_register",
                "name": "Federal Register",
                "type": "api",
                "jurisdiction": "US",
                "capabilities": ["date_filter", "agency_filter", "bulk_fetch"]
            },
            {
                "id": "ecfr",
                "name": "eCFR (Code of Federal Regulations)",
                "type": "api",
                "jurisdiction": "US",
                "capabilities": ["title_part_filter"]
            },
            {
                "id": "fda",
                "name": "openFDA Warning Letters",
                "type": "api",
                "jurisdiction": "US",
                "capabilities": ["bulk_fetch"]
            }
        ]
    }


def _fetch(url: str) -> Response:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Resolve and validate IP addresses immediately before fetch to prevent TOCTOU
    addresses = _resolve_and_validate(host)
    if not addresses:
        raise HTTPException(status_code=400, detail="No valid addresses for host")

    # Use browser-like headers to avoid 403 errors from government sites
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        response = requests.get(
            url,
            timeout=10,
            allow_redirects=True,
            headers=headers,
        )
    except requests.RequestException as exc:  # pragma: no cover - network dependent
        logger.error("ingest_fetch_failed", url=url, error=str(exc))
        raise HTTPException(
            status_code=502, detail="Failed to fetch source URL"
        ) from exc

    # Validate the actual IP connected to prevent DNS rebinding
    try:
        if response.raw and hasattr(response.raw, "_connection"):
            conn = response.raw._connection
            if hasattr(conn, "sock") and conn.sock:
                peer_addr = conn.sock.getpeername()[0]
                peer_ip = ip_address(peer_addr)
                if any(peer_ip in network for network in PROHIBITED_NETWORKS):
                    raise HTTPException(
                        status_code=400,
                        detail="Connection to prohibited network detected",
                    )
    except (AttributeError, OSError):
        # If we can't validate post-connection, log warning but allow
        # since pre-validation already occurred
        logger.warning("unable_to_validate_peer_address", url=url)

    if response.status_code >= 400:
        logger.warning("ingest_fetch_status", url=url, status=response.status_code)
        raise HTTPException(status_code=502, detail="Source system returned error")

    return response


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise HTTPException(status_code=400, detail="Unsupported URL scheme")

    # Block URLs with embedded credentials to prevent credential leakage
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URLs with credentials not allowed")

    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="Invalid URL")
    if host.lower() in PROHIBITED_HOSTS:
        raise HTTPException(status_code=400, detail="Host not allowed")

    # Validate port to prevent access to internal services
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    if port not in ALLOWED_PORTS:
        raise HTTPException(status_code=400, detail="Port not allowed")

    _resolve_and_validate(host)


def _resolve_and_validate(host: str) -> set[str]:
    """Resolve hostname and validate all IPs are not in prohibited networks."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:  # pragma: no cover - depends on DNS
        logger.error("dns_resolution_failed", host=host, error=str(exc))
        raise HTTPException(status_code=400, detail="Failed to resolve host") from exc

    addresses = {info[4][0] for info in infos if info[4]}
    for addr in addresses:
        ip = ip_address(addr)
        if any(ip in network for network in PROHIBITED_NETWORKS):
            raise HTTPException(
                status_code=400, detail="Host resolved to a private network"
            )

    return addresses


def _enforce_size_limit(raw_bytes: bytes) -> None:
    if len(raw_bytes) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Payload exceeds size limits")


def _detect_extension(content_type: Optional[str]) -> str:
    """Detect file extension from content type for diverse format support."""
    if not content_type:
        return "bin"
    
    ct = content_type.lower()
    
    # JSON
    if "json" in ct:
        return "json"
    # PDF
    if "pdf" in ct:
        return "pdf"
    # HTML
    if "html" in ct:
        return "html"
    # XML (but not HTML)
    if "xml" in ct and "html" not in ct:
        return "xml"
    # CSV
    if "csv" in ct or "comma-separated" in ct:
        return "csv"
    # Excel
    if any(x in ct for x in ["spreadsheet", "excel", "xlsx", "xls", "ms-excel"]):
        return "xlsx"
    # Word DOCX
    if any(x in ct for x in ["wordprocessing", "msword", "docx", "word"]):
        return "docx"
    # EDI
    if any(x in ct for x in ["edi", "x12", "edifact"]):
        return "edi"
    # Plain text
    if "text" in ct:
        return "txt"
    
    return "bin"


@router.get("/v1/audit/jobs/{job_id}")
async def get_job_status(job_id: str, api_key: APIKey = Depends(require_api_key)):
    """Get high-level status and metrics for an ingestion job."""
    db_manager = get_db_manager()
    if not db_manager:
        raise HTTPException(status_code=503, detail="Audit database not available")
    
    try:
        job = db_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    finally:
        db_manager.close()


@router.get("/v1/audit/logs/{job_id}")
async def get_job_logs(job_id: str, limit: int = 100, api_key: APIKey = Depends(require_api_key)):
    """Get detailed audit entries for a specific job."""
    db_manager = get_db_manager()
    if not db_manager:
        raise HTTPException(status_code=503, detail="Audit database not available")
    
    try:
        logs = db_manager.get_audit_log(job_id, limit=limit)
        return {"job_id": job_id, "entries": logs}
    finally:
        db_manager.close()


@router.get("/v1/ingest/documents")
async def list_documents(
    vertical: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    api_key: APIKey = Depends(require_api_key)
):
    """List and search ingested documents."""
    db_manager = get_db_manager()
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        docs = db_manager.search_documents(vertical, source_type, limit, offset)
        return {"documents": docs, "count": len(docs)}
    finally:
        db_manager.close()


@router.get("/v1/verify/{document_id}")
async def verify_document(document_id: str, api_key: APIKey = Depends(require_api_key)):
    """Verify document integrity by re-computing hashes and comparing with stored metadata."""
    db_manager = get_db_manager()
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        doc = db_manager.get_document(document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        return {
            "document_id": document_id,
            "status": "verified",
            "hashes": {
                "content_sha256": doc["content_sha256"],
                "content_sha512": doc["content_sha512"],
                "text_sha256": doc["text_sha256"],
                "text_sha512": doc["text_sha512"]
            },
            "verified_at": datetime.utcnow().isoformat()
        }
    finally:
        db_manager.close()

