# ============================================================
# UNSAFE ZONE: This file is the main ingestion router aggregator.
# Endpoint groups have been progressively extracted into sibling
# routes_*.py files. This module now mostly re-exports a few
# shared helpers for back-compat with existing call sites.
# Refactoring target — see PHASE 3.5 in REGENGINE_CODEBASE_REMEDIATION_PRD.md
# ============================================================
"""API routes for the ingestion service."""

from __future__ import annotations

import structlog
from fastapi import APIRouter

# Add shared module to path
from shared.auth import APIKey, require_api_key, verify_jurisdiction_access  # noqa: F401  (re-exported for back-compat)

from .pipeline import ScraperPipeline

# NOTE: /v1/ingest/* (regulation, direct, file, url) and their helpers
# (_process_and_emit, _fetch, _validate_url, _resolve_and_validate,
# _enforce_size_limit, _detect_extension, _endpoint_rate_limit,
# process_regulation_ingestion, _run_adapter_ingest, get_db_manager,
# SSRF constants, ingestion Prometheus metrics) moved to routes_ingest.py.
# Re-exported below for back-compat with existing call sites.
from .routes_ingest import (  # noqa: F401
    ALLOWED_PORTS,
    ALLOWED_SCHEMES,
    KAFKA_COUNTER,
    MAX_FILE_SIZE,
    MAX_PAYLOAD_BYTES,
    PARSER_REGISTRY,
    PROHIBITED_HOSTS,
    PROHIBITED_NETWORKS,
    REQUEST_COUNTER,
    REQUEST_LATENCY,
    _detect_extension,
    _endpoint_rate_limit,
    _enforce_size_limit,
    _fetch,
    _process_and_emit,
    _resolve_and_validate,
    _run_adapter_ingest,
    _validate_url,
    get_db_manager,
    ingest_direct,
    ingest_file,
    ingest_regulation,
    ingest_url,
    process_regulation_ingestion,
)

# --- State adaptor imports (scaffold) ---
from .scrapers.state_adaptors.base import (  # noqa: F401  (re-exported for back-compat)
    FetchedItem,
    Source,
    StateRegistryScraper as AdaptorRegistryScraper,
)
from .scrapers.state_adaptors.cppa import CPPAScraper
from .scrapers.state_adaptors.fda_enforcement import FDAEnforcementScraper
from .scrapers.state_adaptors.fl_rss import FloridaRSSScraper
from .scrapers.state_adaptors.google_discovery import GoogleDiscoveryScraper
from .scrapers.state_adaptors.tx_rss import TexasRegistryScraper
from .scrapers.state_generic import StateRegistryScraper as GenericStateScraper

logger = structlog.get_logger("ingestion")
router = APIRouter(prefix="/api/v1/regulatory", tags=["regulatory-pipeline"], include_in_schema=False)

GENERIC_STATE_SCRAPER = GenericStateScraper()
_PIPELINE = ScraperPipeline()


# NOTE: /v1/scrape/cppa moved to routes_scraping.py
# NOTE: /v1/ingest/regulation moved to routes_ingest.py
# NOTE: /v1/ingest, /v1/ingest/file, /v1/ingest/url moved to routes_ingest.py
# NOTE: Status/query endpoints moved to routes_status.py
# NOTE: Discovery queue endpoints moved to routes_discovery.py
# NOTE: /health and /metrics endpoints moved to routes_health_metrics.py (Finding #8, Ingestion Debug Audit)
# NOTE: /v1/ingest/all-regulations moved to routes_scraping.py
# NOTE: /scrape/{adaptor} moved to routes_scraping.py
# NOTE: Federal source endpoints moved to routes_sources.py
# NOTE: Audit/status/documents/verify endpoints moved to routes_status.py


ADAPTORS: dict[str, AdaptorRegistryScraper] = {
    "cppa": CPPAScraper(),
    "tx_rss": TexasRegistryScraper(),
    "fl_rss": FloridaRSSScraper(),
    "google_discovery": GoogleDiscoveryScraper(),
    "fda_warnings": FDAEnforcementScraper(),
}
