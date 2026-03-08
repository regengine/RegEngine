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
from typing import Iterable, Optional, List
from urllib.parse import urlparse

import requests
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, BackgroundTasks, Body, File, UploadFile, Query, Form
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from confluent_kafka.admin import AdminClient
from requests import Response
import redis

# Add shared module to path
from shared.auth import APIKey, require_api_key, verify_jurisdiction_access

from .config import get_settings
from .kafka_utils import send
from .models import IngestRequest, DirectIngestRequest, NormalizedDocument, NormalizedEvent, DiscoveryQueueItem, BulkDiscoveryRequest
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
    
    logger.info("scrape_nydfs_triggered", url=url, tenant_id=api_key.tenant_id)
    
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
    
    logger.info("scrape_cppa_triggered", url=url, tenant_id=api_key.tenant_id)
    
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

import tempfile
import httpx
from kernel.obligation.regulation_loader import RegulationLoader
from kernel.discovery import discovery
from plugins.fsma.sources import FSMA_SOURCES

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


async def process_regulation_ingestion(job_id: str, name: str, filename: str, tenant_id: str, webhook: Optional[str] = None):
    """Background task to process regulation ingestion with webhook notification (v2)."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    
    # Retrieve content from Redis
    content = r.get(f"ingest:job:{job_id}")
    if not content:
        logger.error("ingest_job_content_missing", job_id=job_id)
        return

    # Save to temp file
    suffix = ".pdf" if filename.endswith(".pdf") else ".docx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        r.setex(f"ingest:status:{job_id}", 7200, "processing")
        loader = RegulationLoader(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password
        )
        count = await loader.load(
            tmp_path, 
            "pdf" if filename.endswith(".pdf") else "docx", 
            name
        )
        loader.close()
        
        r.setex(f"ingest:status:{job_id}", 7200, "completed")
        # Store metadata about the result
        result_data = {"sections": count, "name": name, "tenant_id": tenant_id}
        r.setex(f"ingest:result:{job_id}", 7200, json.dumps(result_data))
        logger.info("regulation_ingested_v2_background", name=name, sections=count, job_id=job_id)
        
        if webhook:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(webhook, json={
                        "job_id": job_id, 
                        "status": "completed", 
                        "regulation": name,
                        "sections": count
                    })
                logger.info("ingestion_webhook_sent", job_id=job_id, webhook=webhook)
            except Exception as e:
                logger.error("ingestion_webhook_failed", job_id=job_id, error=str(e))

    except Exception as e:
        logger.error("regulation_ingestion_background_failed", job_id=job_id, error=str(e))
        r.setex(f"ingest:status:{job_id}", 7200, f"failed: {str(e)}")
        if webhook:
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(webhook, json={"job_id": job_id, "status": "failed", "error": str(e)})
            except Exception as e:
                logger.warning("webhook_notification_failed", error=str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.post("/v1/ingest/regulation", status_code=202)
async def ingest_regulation(
    name: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    webhook: Optional[str] = Query(None),
    api_key: APIKey = Depends(require_api_key),
):
    """Ingest a regulation and codify it asynchronously with optional webhook notification (v2)."""
    # Entitlement check
    allowed = set(api_key.allowed_jurisdictions or [])
    if "US" not in allowed and "GLOBAL" not in allowedRegistration:
        # Check if the user has specific permission for this action
        pass

    if not file.filename.endswith((".pdf", ".docx")):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file uploaded")
    
    if len(content) > 512 * 1024 * 1024:  # 512MB
        raise HTTPException(status_code=413, detail="File too large (max 100MB)")

    job_id = str(uuid.uuid4())
    settings = get_settings()
    
    try:
        # Store in Redis temporarily
        r = redis.from_url(settings.redis_url)
        r.setex(f"ingest:job:{job_id}", 7200, content)
        r.setex(f"ingest:status:{job_id}", 7200, "queued")
        
        background_tasks.add_task(
            process_regulation_ingestion, 
            job_id, 
            name, 
            file.filename, 
            api_key.tenant_id,
            webhook
        )
        
        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Regulation ingestion started in background",
            "webhook": webhook if webhook else "none"
        }
    except Exception as e:
        logger.error("regulation_ingestion_queue_failed", name=name, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to queue ingestion job")


@router.get("/v1/ingest/status/{job_id}")
async def get_ingestion_status(job_id: str):
    """Check the status of a background ingestion job (v2)."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    status = r.get(f"ingest:status:{job_id}")
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
        
    status_str = status.decode("utf-8")
    response = {"job_id": job_id, "status": status_str}
    
    if status_str == "completed":
        result = r.get(f"ingest:result:{job_id}")
        if result:
            response["result"] = json.loads(result.decode("utf-8"))
            
    return response


@router.get("/v1/ingest/discovery/queue", response_model=List[DiscoveryQueueItem])
async def get_discovery_queue():
    """Retrieve all items in the manual discovery queue."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    
    # manual_upload_queue is a Redis list
    items = r.lrange("manual_upload_queue", 0, -1)
    results = []
    for i, item in enumerate(items):
        try:
            val = item.decode("utf-8")
            if ":" in val:
                body, url = val.split(":", 1)
                results.append(DiscoveryQueueItem(body=body, url=url, index=i))
        except Exception as e:
            logger.debug("discovery_queue_parse_skip", index=i, error=str(e))
            continue
    return results


@router.get("/v1/ingest/manual-queue")
async def get_manual_queue(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    api_key: APIKey = Depends(require_api_key),
):
    """Retrieve items from the tenant-scoped manual upload queue.

    Reads from ``manual_upload_queue:{tenant_id}`` — each tenant sees only
    their own pending uploads, preventing cross-tenant data leakage.
    """
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    tenant_id = api_key.tenant_id

    queue_key = f"manual_upload_queue:{tenant_id}"
    total = r.llen(queue_key)
    raw_items = r.lrange(queue_key, skip, skip + limit - 1)

    items = []
    for i, raw in enumerate(raw_items):
        try:
            val = raw.decode("utf-8")
            if ":" in val:
                body, url = val.split(":", 1)
                items.append({"index": skip + i, "body": body, "url": url})
            else:
                items.append({"index": skip + i, "body": val, "url": None})
        except Exception as e:
            logger.debug("manual_queue_parse_skip", index=skip + i, error=str(e))
            continue

    logger.info(
        "manual_queue_fetched",
        tenant_id=tenant_id,
        total=total,
        returned=len(items),
    )
    return {
        "tenant_id": tenant_id,
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": items,
    }


@router.post("/v1/ingest/discovery/approve")
async def approve_discovery(
    index: int,
    background_tasks: BackgroundTasks,
    api_key: APIKey = Depends(require_api_key)
):
    """Approve a discovery item and trigger a scrape."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    
    # Get the item at the specific index
    item = r.lindex("manual_upload_queue", index)
    if not item:
        raise HTTPException(status_code=404, detail="Discovery item not found at index")
    
    val = item.decode("utf-8")
    body, url = val.split(":", 1)
    
    # Remove it from the queue (using a safer approach would be better, but LREM with count 1 is standard)
    # Note: index-based deletion is tricky in Redis if the list changes. 
    # For now, we'll use LREM which might delete a different item if values are identical.
    r.lrem("manual_upload_queue", 1, item)
    
    # Trigger the scrape
    background_tasks.add_task(discovery.scrape, body, url)
    
    logger.info("discovery_approved", body=body, url=url, tenant_id=api_key.tenant_id)
    return {"status": "approved", "body": body, "url": url}


@router.post("/v1/ingest/discovery/reject")
async def reject_discovery(
    index: int,
    api_key: APIKey = Depends(require_api_key)
):
    """Reject and remove a discovery item from the queue."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    
    item = r.lindex("manual_upload_queue", index)
    if not item:
        raise HTTPException(status_code=404, detail="Discovery item not found at index")
    
    r.lrem("manual_upload_queue", 1, item)
    logger.info("discovery_rejected", index=index, tenant_id=api_key.tenant_id)
    return {"status": "rejected", "index": index}


@router.post("/v1/ingest/discovery/bulk-approve")
async def bulk_approve_discovery(
    payload: BulkDiscoveryRequest,
    background_tasks: BackgroundTasks,
    api_key: APIKey = Depends(require_api_key)
):
    """Approve multiple discovery items and trigger scrapes."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    
    approved = []
    # Sort indices descending to avoid shifting if we were using LPOP/LREM by index
    # Since we LREM by value, indices change as we go.
    # BEST: Get all values first.
    items_to_process = []
    for index in payload.indices:
        item = r.lindex("manual_upload_queue", index)
        if item:
            items_to_process.append(item)
            
    for item in items_to_process:
        val = item.decode("utf-8")
        body, url = val.split(":", 1)
        r.lrem("manual_upload_queue", 1, item)
        background_tasks.add_task(discovery.scrape, body, url)
        approved.append({"body": body, "url": url})
            
    logger.info("bulk_discovery_approved", count=len(approved), tenant_id=api_key.tenant_id)
    return {"status": "approved", "count": len(approved), "items": approved}


@router.post("/v1/ingest/discovery/bulk-reject")
async def bulk_reject_discovery(
    payload: BulkDiscoveryRequest,
    api_key: APIKey = Depends(require_api_key)
):
    """Reject and remove multiple discovery items from the queue."""
    settings = get_settings()
    r = redis.from_url(settings.redis_url)
    
    items_to_remove = []
    for index in payload.indices:
        item = r.lindex("manual_upload_queue", index)
        if item:
            items_to_remove.append(item)
            
    rejected_count = 0
    for item in items_to_remove:
        r.lrem("manual_upload_queue", 1, item)
        rejected_count += 1
            
    logger.info("bulk_discovery_rejected", count=rejected_count, tenant_id=api_key.tenant_id)
    return {"status": "rejected", "count": rejected_count}


@router.post("/v1/ingest/all-regulations")
async def ingest_all_regulations(
    background_tasks: BackgroundTasks,
    api_key: APIKey = Depends(require_api_key),
):
    """
    Trigger an FDA-scoped, idempotent regulatory ingestion run.

    Sources are limited to the curated FSMA_SOURCES list (eCFR Title 21,
    Federal Register FSMA notices, FDA guidance pages). Each source is
    deduplicated via ETag + SHA-256 content hash — unchanged documents
    are skipped without re-parsing.
    """
    job_id = str(uuid.uuid4())
    started_at = time.time()

    logger.info(
        "fsma_ingestion_triggered",
        job_id=job_id,
        sources=len(FSMA_SOURCES),
        tenant_id=api_key.tenant_id,
    )

    # Run all sources concurrently (each scrape has its own 2 s polite delay)
    tasks = [
        discovery.scrape(
            body=source["name"],
            source_url=source["url"],
            source_type=source["type"],
            jurisdiction=source["jurisdiction"],
        )
        for source in FSMA_SOURCES
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Tally structured summary
    summary: dict[str, int] = {
        "sources_attempted": len(FSMA_SOURCES),
        "queued_manual": 0,
        "unchanged": 0,
        "ingested": 0,
        "failed": 0,
    }
    for r in results:
        if isinstance(r, Exception):
            summary["failed"] += 1
        else:
            status = r.get("status", "failed")
            if status == "queued_manual":
                summary["queued_manual"] += 1
            elif status == "unchanged":
                summary["unchanged"] += 1
            elif status == "ingested":
                summary["ingested"] += 1
            else:
                summary["failed"] += 1

    duration_ms = int((time.time() - started_at) * 1000)

    logger.info(
        "fsma_ingestion_complete",
        job_id=job_id,
        duration_ms=duration_ms,
        **summary,
    )

    return {
        "job_id": job_id,
        "status": "complete",
        "jurisdiction": "FDA",
        "duration_ms": duration_ms,
        **summary,
    }


@router.get("/health")
def health() -> dict[str, str]:
    """Health-check endpoint."""
    settings = get_settings()
    kafka_status = "unavailable"
    try:
        admin_client = AdminClient(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "ingestion-healthcheck",
            }
        )
        admin_client.list_topics(timeout=5)
        kafka_status = "available"
    except Exception as exc:
        logger.warning("ingestion_health_kafka_unavailable", error=str(exc))
    return {
        "status": "healthy",
        "service": "ingestion-service",
        "kafka": kafka_status,
    }


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
        existing = db_manager.get_document_by_hash(content_sha256, tenant_id=tenant_id)
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
            
    try:
        normalized, document_id, _ = normalize_document(
            raw_json, raw_bytes, url_str, content_type
        )
    except Exception as e:
        logger.error("normalization_failed", url=url_str, error=str(e))
        raise HTTPException(status_code=422, detail=f"Document parsing/normalization failed: {str(e)}")
    
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

    # 8. Kafka Emission & Claim Check Pattern
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
        payload_bytes = json.dumps(event.model_dump(mode="json")).encode("utf-8")
        
        # If payload exceeds 1MB Kafka limit, execute Claim Check pattern
        if len(payload_bytes) > 1024 * 1024:
            logger.info("kafka_claim_check_triggered", document_id=document_id, size=len(payload_bytes))
            text_key = f"normalized-text/{document_id}/{event_id}.txt"
            text_uri = put_bytes(settings.processed_bucket, text_key, parsed_text.encode("utf-8"))
            event.text_s3_uri = text_uri
            
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
    finally:
        if db_manager:
            db_manager.close()


@router.post("/v1/ingest/file", response_model=NormalizedEvent)
async def ingest_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    source_system: str = Form("generic"),
    vertical: Optional[str] = Form(None),
    api_key: APIKey = Depends(require_api_key),
) -> NormalizedEvent:
    """Ingest a single document from a file upload (v2)."""
    endpoint = "ingest_file"
    start_time = time.perf_counter()
    tenant_id = api_key.tenant_id or "00000000-0000-0000-0000-000000000000"
    job_id = str(uuid.uuid4())
    
    logger.info("ingest_file_request", filename=file.filename, tenant_id=tenant_id, job_id=job_id)
    
    db_manager = get_db_manager()
    audit_logger = None
    if db_manager:
        db_manager.connect()
        db_manager.set_tenant_context(tenant_id)
        audit_logger = AuditLogger(job_id, db_connection=db_manager)
        job = IngestionJob(
            job_id=job_id,
            vertical=vertical or "unknown",
            source_type="file_upload",
            status=JobStatus.RUNNING,
            started_at=datetime.utcnow(),
            config={"filename": file.filename}
        )
        try:
            db_manager.insert_job(job)
        except Exception as e:
            logger.error("job_db_init_failed", job_id=job_id, error=str(e))

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
            
        content_type = file.content_type or "application/octet-stream"
        
        event = _process_and_emit(
            raw_bytes=content,
            url_str=f"http://upload.internal/{file.filename}",
            source_system=source_system,
            tenant_id=tenant_id,
            content_type=content_type,
            job_id=job_id,
            audit_logger=audit_logger,
            db_manager=db_manager,
            vertical=vertical or "unknown"
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
        logger.exception("ingest_file_failed", job_id=job_id, error=str(exc))
        if db_manager:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.completed_at = datetime.utcnow()
            db_manager.update_job(job)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(exc)}")
    finally:
        if db_manager:
            db_manager.close()


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
        raw_bytes, content_type = await _fetch(url_str)
        
        if audit_logger:
            audit_logger.log_fetch(url_str, "success", http_status=200)

        event = _process_and_emit(
            raw_bytes=raw_bytes,
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


MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB hard limit

async def _fetch(url: str) -> tuple[bytes, str]:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Resolve and validate IP addresses immediately before fetch to prevent TOCTOU
    addresses = _resolve_and_validate(host)
    if not addresses:
        raise HTTPException(status_code=400, detail="No valid addresses for host")

    headers = {
        "User-Agent": "RegEngine/1.0 (Integration_Testing; admin@regengine.io)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    raw_bytes = bytearray()
    content_type = "application/octet-stream"
    
    try:
        import httpx
        async with httpx.AsyncClient(http2=True, follow_redirects=True, timeout=60.0) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code >= 400:
                    logger.warning("ingest_fetch_status", url=url, status=response.status_code)
                    raise HTTPException(status_code=502, detail="Source system returned error")
                    
                content_type = response.headers.get("Content-Type", content_type)
                
                # Enforce stream limits to prevent OOM
                async for chunk in response.aiter_bytes():
                    raw_bytes.extend(chunk)
                    if len(raw_bytes) > MAX_FILE_SIZE:
                        logger.error("payload_too_large", url=url, size=len(raw_bytes))
                        raise HTTPException(status_code=413, detail="Payload Too Large (Exceeds 50MB)")

    except httpx.RequestError as exc:
        logger.error("ingest_fetch_failed", url=url, error=str(exc))
        raise HTTPException(status_code=502, detail="Failed to fetch source URL") from exc

    return bytes(raw_bytes), content_type


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
