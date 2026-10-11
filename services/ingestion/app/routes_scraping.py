"""Scraper routes: state registry adaptors and FSMA regulation sources."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException
from shared.auth import APIKey, require_api_key, verify_jurisdiction_access
from shared.database import SessionLocal
from shared.task_queue import enqueue_task

from plugins.fsma.sources import FSMA_SOURCES, load_fsma_sources

from .discovery import discovery
from .models import IngestAllRegulationsResponse, ScrapeRegistryResponse, ScrapeResponse
from .pipeline import ScraperPipeline
from .scrapers.state_adaptors.base import StateRegistryScraper as AdaptorRegistryScraper
from .scrapers.state_adaptors.cppa import CPPAScraper
from .scrapers.state_adaptors.fda_enforcement import FDAEnforcementScraper
from .scrapers.state_adaptors.fl_rss import FloridaRSSScraper
from .scrapers.state_adaptors.google_discovery import GoogleDiscoveryScraper
from .scrapers.state_adaptors.tx_rss import TexasRegistryScraper

logger = structlog.get_logger("ingestion.scrapers")
router = APIRouter(include_in_schema=False)

_PIPELINE = ScraperPipeline()

ADAPTORS: dict[str, AdaptorRegistryScraper] = {
    "cppa": CPPAScraper(),
    "tx_rss": TexasRegistryScraper(),
    "fl_rss": FloridaRSSScraper(),
    "google_discovery": GoogleDiscoveryScraper(),
    "fda_warnings": FDAEnforcementScraper(),
}


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


@router.post("/v1/scrape/cppa", status_code=202, response_model=ScrapeResponse)
async def scrape_cppa(
    url: str,
    api_key=Depends(require_api_key),
):
    verify_jurisdiction_access(api_key, "US-CA")

    db = SessionLocal()
    try:
        if ADAPTORS.get("cppa"):
            enqueue_task(
                db,
                task_type="state_scrape",
                payload={
                    "adaptor_name": "cppa",
                    "url": url,
                    "jurisdiction_code": "US-CA",
                    "tenant_id": api_key.tenant_id,
                },
                tenant_id=api_key.tenant_id,
                idempotency_key=(f"state_scrape:{api_key.tenant_id}:cppa:US-CA:{_url_hash(url)}"),
            )
            db.commit()
            return {"status": "accepted", "message": "CPPA scrape job started"}

        enqueue_task(
            db,
            task_type="generic_scrape",
            payload={
                "url": url,
                "jurisdiction_code": "US-CA",
                "tenant_id": api_key.tenant_id,
            },
            tenant_id=api_key.tenant_id,
            idempotency_key=f"generic_scrape:{api_key.tenant_id}:US-CA:{_url_hash(url)}",
        )
        db.commit()
        return {"status": "accepted", "message": "Generic scrape job started"}
    finally:
        db.close()


@router.post("/scrape/{adaptor}", response_model=ScrapeRegistryResponse)
def scrape_registry(
    adaptor: str,
    api_key: APIKey = Depends(require_api_key),
) -> dict:
    """Run a state registry adaptor and enqueue normalized events."""
    if adaptor not in ADAPTORS:
        raise HTTPException(status_code=404, detail="Unknown adaptor")

    scraper = ADAPTORS[adaptor]
    allowed = set(api_key.allowed_jurisdictions or [])
    results = []

    for src in scraper.list_sources():
        if src.jurisdiction_code and src.jurisdiction_code not in allowed:
            continue
        try:
            fetched = scraper.fetch(src)
            if not fetched.content_bytes:
                logger.warning("scrape_empty_content", source=src.url)
                continue
            event = _PIPELINE.process_content(
                content=fetched.content_bytes,
                content_type=fetched.content_type,
                jurisdiction_code=src.jurisdiction_code,
                source_url=src.url,
                tenant_id=api_key.tenant_id,
            )
            if event:
                results.append(event)
        except Exception as e:
            logger.error("scrape_source_failed", url=src.url, error=str(e))
            continue

    return {"adaptor": adaptor, "count": len(results), "sources": results}


async def run_all_regulations_ingest(tenant_id: str = "system") -> dict:
    """Run the FDA-scoped, idempotent regulatory ingestion sweep.

    Shared by the HTTP route below and the scheduler's nightly
    ``fsma_nightly_sync`` job, which calls it in-process (see
    ``services/scheduler/service.py``) — the consolidated monolith has no
    internal credential that ``require_api_key`` accepts, so the old
    HTTP-to-self call could never authenticate.

    ``tenant_id`` namespaces the manual-upload queue for robots-denied
    sources. The HTTP route passes the caller's tenant; the scheduler's
    nightly call keeps the shared ``system`` bucket.
    """
    # Refuse a bad catalog before any fetch. A path-like name, an off-scope
    # URL, or an extra scope field must not reach the scraper or the queue.
    sources = load_fsma_sources(FSMA_SOURCES)
    job_id = str(uuid.uuid4())
    started_at = time.time()

    logger.info(
        "fsma_ingestion_triggered",
        job_id=job_id,
        sources=len(sources),
    )

    tasks = [
        discovery.scrape(
            body=source["name"],
            source_url=source["url"],
            source_type=source["type"],
            jurisdiction=source["jurisdiction"],
            tenant_id=tenant_id,
        )
        for source in sources
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    summary: dict[str, int] = {
        "sources_attempted": len(sources),
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
    logger.info("fsma_ingestion_complete", job_id=job_id, duration_ms=duration_ms, **summary)

    return {
        "job_id": job_id,
        "status": "complete",
        "jurisdiction": "FDA",
        "duration_ms": duration_ms,
        **summary,
    }


@router.post("/v1/ingest/all-regulations", response_model=IngestAllRegulationsResponse)
async def ingest_all_regulations(
    api_key: APIKey = Depends(require_api_key),
):
    """Trigger an FDA-scoped, idempotent regulatory ingestion run."""
    logger.info("fsma_ingestion_requested", tenant_id=api_key.tenant_id)
    return await run_all_regulations_ingest(tenant_id=api_key.tenant_id)
