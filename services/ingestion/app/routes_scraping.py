"""Scraper routes: state registry adaptors and FSMA regulation sources."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from shared.auth import APIKey, require_api_key, verify_jurisdiction_access

from .config import get_settings
from .pipeline import ScraperPipeline
from .scraper_job import run_state_scrape_job, run_generic_scrape_job
from .scrapers.state_adaptors.base import StateRegistryScraper as AdaptorRegistryScraper
from .scrapers.state_adaptors.cppa import CPPAScraper
from .scrapers.state_adaptors.fl_rss import FloridaRSSScraper
from .scrapers.state_adaptors.tx_rss import TexasRegistryScraper
from .scrapers.state_adaptors.google_discovery import GoogleDiscoveryScraper
from .scrapers.state_adaptors.fda_enforcement import FDAEnforcementScraper
from kernel.discovery import discovery
from plugins.fsma.sources import FSMA_SOURCES

logger = structlog.get_logger("ingestion.scrapers")
router = APIRouter()

_PIPELINE = ScraperPipeline()

ADAPTORS: dict[str, AdaptorRegistryScraper] = {
    "cppa": CPPAScraper(),
    "tx_rss": TexasRegistryScraper(),
    "fl_rss": FloridaRSSScraper(),
    "google_discovery": GoogleDiscoveryScraper(),
    "fda_warnings": FDAEnforcementScraper(),
}


@router.post("/v1/scrape/cppa", status_code=202)
async def scrape_cppa(
    url: str,
    background_tasks: BackgroundTasks,
    api_key=Depends(require_api_key),
):
    verify_jurisdiction_access(api_key, "US-CA")
    adaptor = ADAPTORS.get("cppa")
    if adaptor:
        background_tasks.add_task(
            run_state_scrape_job, adaptor_name="cppa", adaptor_instance=adaptor,
            url=url, jurisdiction_code="US-CA", tenant_id=api_key.tenant_id,
        )
        return {"status": "accepted", "message": "CPPA scrape job started"}
    background_tasks.add_task(
        run_generic_scrape_job, url=url, jurisdiction_code="US-CA", tenant_id=api_key.tenant_id,
    )
    return {"status": "accepted", "message": "Generic scrape job started"}


@router.post("/scrape/{adaptor}")
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
                content=fetched.content_bytes, content_type=fetched.content_type,
                jurisdiction_code=src.jurisdiction_code, source_url=src.url,
                tenant_id=api_key.tenant_id,
            )
            if event:
                results.append(event)
        except Exception as e:
            logger.error("scrape_source_failed", url=src.url, error=str(e))
            continue

    return {"adaptor": adaptor, "count": len(results), "sources": results}


@router.post("/v1/ingest/all-regulations")
async def ingest_all_regulations(
    background_tasks: BackgroundTasks,
    api_key: APIKey = Depends(require_api_key),
):
    """Trigger an FDA-scoped, idempotent regulatory ingestion run."""
    job_id = str(uuid.uuid4())
    started_at = time.time()

    logger.info(
        "fsma_ingestion_triggered",
        job_id=job_id, sources=len(FSMA_SOURCES), tenant_id=api_key.tenant_id,
    )

    tasks = [
        discovery.scrape(
            body=source["name"], source_url=source["url"],
            source_type=source["type"], jurisdiction=source["jurisdiction"],
        )
        for source in FSMA_SOURCES
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    summary: dict[str, int] = {
        "sources_attempted": len(FSMA_SOURCES),
        "queued_manual": 0, "unchanged": 0, "ingested": 0, "failed": 0,
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
        "job_id": job_id, "status": "complete", "jurisdiction": "FDA",
        "duration_ms": duration_ms, **summary,
    }
