from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shared.auth import require_api_key
from shared.resilient_http import resilient_client
from shared.circuit_breaker import CircuitOpenError
from .config import settings
from .fsma_spreadsheet import generate_fda_csv

_logger = logging.getLogger(__name__)
_audit_logger = logging.getLogger("compliance-audit")

router = APIRouter(tags=["fsma-compliance"])


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ComplianceRequirement(BaseModel):
    id: str
    title: str
    description: str
    category: str | None = None
    priority: str | None = None  # LOW | MEDIUM | HIGH | CRITICAL
    status: str | None = None    # NOT_STARTED | IN_PROGRESS | COMPLIANT | NON_COMPLIANT


class ComplianceChecklist(BaseModel):
    id: str
    name: str
    description: str | None = None
    industry: str
    framework: str | None = None
    version: str | None = None
    requirements: list[ComplianceRequirement] = []
    items: list[ComplianceRequirement] = []


class Industry(BaseModel):
    id: str
    name: str
    description: str | None = None
    checklist_count: int = 0


class IndustriesResponse(BaseModel):
    industries: list[dict[str, Any]]
    total: int


class ChecklistsResponse(BaseModel):
    checklists: list[dict[str, Any]]
    total: int


# ---------------------------------------------------------------------------
# FSMA 204 rules — loaded from fsma_rules.json at startup (#546)
# ---------------------------------------------------------------------------

_RULES_PATH = Path(__file__).parent / "fsma_rules.json"


def _load_fsma_rules() -> dict:
    """Load and return the FSMA rules config from JSON.

    Raises RuntimeError on missing file or malformed JSON so startup fails
    loudly rather than serving empty compliance data.
    """
    try:
        with _RULES_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise RuntimeError(
            f"FSMA rules config not found at {_RULES_PATH}. "
            "Ensure fsma_rules.json is present in the compliance app directory."
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed fsma_rules.json: {exc}") from exc

    _logger.info("Loaded FSMA rules from %s", _RULES_PATH)
    return data


_rules = _load_fsma_rules()

_INDUSTRIES: list[Industry] = [Industry(**i) for i in _rules["industries"]]

_CHECKLISTS: list[ComplianceChecklist] = []
for _cl_data in _rules["checklists"]:
    _reqs = [ComplianceRequirement(**r) for r in _cl_data.get("requirements", [])]
    _CHECKLISTS.append(
        ComplianceChecklist(
            **{k: v for k, v in _cl_data.items() if k != "requirements"},
            requirements=_reqs,
            items=_reqs,
        )
    )

_CHECKLIST_INDEX: dict[str, ComplianceChecklist] = {c.id: c for c in _CHECKLISTS}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
#
# NOTE (#1203): The POST /validate endpoint was removed on 2026-04-17.
#
# It was orphaned — no backend caller and no React consumer actually invoked
# it in production. EPCIS ingestion validates via its own Pydantic check
# (see services/ingestion/app/epcis/validation.py), and the real compliance
# logic lives in the versioned RulesEngine (services/shared/rules/engine.py)
# which is wired through services/ingestion/app/rules_router.py.
#
# Keeping a dead validator advertised as "POST /validate" overstated product
# functionality and risked accidental future callers relying on fail-open
# behavior. If re-wiring is ever needed, do it by calling RulesEngine
# directly from ingestion, not by resurrecting this endpoint.

@router.get("/industries", dependencies=[Depends(require_api_key)], response_model=IndustriesResponse)
async def list_industries() -> IndustriesResponse:
    return {"industries": [i.model_dump() for i in _INDUSTRIES], "total": len(_INDUSTRIES)}


@router.get("/checklists", dependencies=[Depends(require_api_key)], response_model=ChecklistsResponse)
async def list_checklists(industry: str | None = None) -> ChecklistsResponse:
    results = _CHECKLISTS
    if industry:
        results = [c for c in results if c.industry.lower() == industry.lower()]
    return {"checklists": [c.model_dump() for c in results], "total": len(results)}


@router.get("/checklists/{checklist_id}", dependencies=[Depends(require_api_key)], response_model=ComplianceChecklist)
async def get_checklist(checklist_id: str) -> ComplianceChecklist:
    checklist = _CHECKLIST_INDEX.get(checklist_id)
    if not checklist:
        raise HTTPException(status_code=404, detail=f"Checklist '{checklist_id}' not found")
    return checklist


# ---------------------------------------------------------------------------
# FDA Audit Spreadsheet Export
# ---------------------------------------------------------------------------

_GRAPH_SERVICE_URL = settings.graph_service_url


@router.get("/v1/fsma/audit/spreadsheet", dependencies=[Depends(require_api_key)])
async def fsma_audit_spreadsheet(
    request: Request,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    tlc: str | None = Query(None, description="Filter by Traceability Lot Code"),
    requesting_entity: str | None = Query(None, description="Name of requesting entity"),
) -> StreamingResponse:
    """Generate an FDA 204 Sortable Spreadsheet CSV for the given date range."""

    params: dict[str, str] = {
        "start_date": start_date,
        "end_date": end_date,
    }
    if tlc:
        params["tlc"] = tlc

    # Forward auth, tenant, and correlation headers to downstream graph service
    headers: dict[str, str] = {}
    api_key = request.headers.get("X-RegEngine-API-Key")
    if api_key:
        headers["X-RegEngine-API-Key"] = api_key
    tenant_id = request.headers.get("X-Tenant-ID") or request.headers.get("X-RegEngine-Tenant-ID")
    if tenant_id:
        headers["X-RegEngine-Tenant-ID"] = tenant_id
    request_id = request.headers.get("X-Request-ID")
    if request_id:
        headers["X-Request-ID"] = request_id

    try:
        async with resilient_client(timeout=30.0, circuit_name="graph-service") as client:
            resp = await client.get(
                f"{_GRAPH_SERVICE_URL}/v1/fsma/traceability/search/events",
                params=params,
                headers=headers,
            )
    except CircuitOpenError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Graph service circuit open — retry after {exc.retry_after:.0f}s",
        ) from exc

    if resp.status_code >= 500:
        correlation_id = str(uuid.uuid4())
        _logger.error("graph_service_5xx", extra={"status": resp.status_code, "body": resp.text[:200], "correlation_id": correlation_id})
        raise HTTPException(
            status_code=502,
            detail=f"Upstream service temporarily unavailable (ref: {correlation_id})",
        )
    if resp.status_code >= 400:
        correlation_id = str(uuid.uuid4())
        _logger.warning("graph_service_4xx", extra={"status": resp.status_code, "body": resp.text[:200], "correlation_id": correlation_id})
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Request could not be processed (ref: {correlation_id})",
        )
    data = resp.json()

    events = data.get("events") or data.get("results") or []

    csv_content = generate_fda_csv(
        events,
        start_date=start_date,
        end_date=end_date,
        requesting_entity=requesting_entity or "",
    )

    # Audit log the FDA export (#988)
    _audit_logger.info(
        "fda_export_generated",
        extra={
            "export_type": "fda_csv",
            "start_date": start_date,
            "end_date": end_date,
            "tlc_filter": tlc,
            "requesting_entity": requesting_entity,
            "tenant_id": tenant_id,
            "event_count": len(events),
        },
    )

    filename = f"fsma_204_audit_{start_date}_{end_date}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
