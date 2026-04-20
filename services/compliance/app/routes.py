from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from shared.auth import APIKey, require_api_key
from shared.resilient_http import resilient_client
from shared.circuit_breaker import CircuitOpenError
from .config import settings
from .csv_safety import sanitize_cell
from .fsma_spreadsheet import FSMATimestampError, generate_fda_csv


# ---------------------------------------------------------------------------
# FDA spreadsheet hardening helpers (issues #1283, #1272, #1291)
# ---------------------------------------------------------------------------

# FSMA 204 retention window — records older than 2 years are not in scope
# for mandatory response. We still export them, but refuse ranges that
# would materialize an unbounded history.
_MAX_EXPORT_RANGE_DAYS = 366 * 2

# Cursor-pagination parameters for the upstream graph service
# (issue #1038). The graph service caps ``limit`` at 500; we request
# that maximum and loop until ``has_more`` is false. The hard cap
# bounds how much the compliance service is willing to buffer in
# memory before producing the CSV — exceeding it returns HTTP 413
# rather than silently truncating.
_GRAPH_PAGE_SIZE = 500
_MAX_EXPORT_EVENTS = 50_000

# Narrow regex for safe filename tokens — ASCII alphanumerics plus
# ``.``, ``_``, ``-``. Anything else is stripped to prevent CRLF /
# quote / path-separator injection into the Content-Disposition header.
_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")

# Requesting-entity is rendered into a CSV metadata row that an auditor
# sees at the top of the spreadsheet. Restrict to a very conservative
# set so formula injection cannot land even if the CSV sanitizer is
# ever regressed.
_REQUESTING_ENTITY_RE = re.compile(r"^[A-Za-z0-9 .,&'\-]{0,120}$")


def _parse_iso_date(name: str, value: str) -> date:
    """Parse ``value`` as ISO-8601 ``YYYY-MM-DD`` or 400.

    Rejects typos like ``2026-13-99`` and formats like ``01/15/26`` that
    previously slipped through and either produced empty "official"
    exports (#1291) or were interpolated verbatim into Content-
    Disposition filenames (#1283).
    """
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{name} must be ISO-8601 YYYY-MM-DD",
        ) from exc


def _safe_filename_token(value: str, *, max_len: int = 64) -> str:
    """Sanitize a filename component.

    Restricts to ``[A-Za-z0-9._-]``, caps length, and rejects ``..``
    traversal. Used before interpolating any user-influenced value
    into a Content-Disposition header (issue #1283).
    """
    cleaned = _FILENAME_SAFE_RE.sub("_", value)[:max_len] or "all"
    # Defense-in-depth: prevent .. after normalization.
    while ".." in cleaned:
        cleaned = cleaned.replace("..", "_")
    return cleaned

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


@router.get("/v1/fsma/audit/spreadsheet")
async def fsma_audit_spreadsheet(
    request: Request,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    tlc: str | None = Query(None, description="Filter by Traceability Lot Code"),
    requesting_entity: str | None = Query(None, description="Name of requesting entity"),
    api_key: APIKey = Depends(require_api_key),
) -> StreamingResponse:
    """Generate an FDA 204 Sortable Spreadsheet CSV for the given date range.

    Hardening applied in this handler (issues #1272, #1283, #1291, #1106):

    * ``start_date`` / ``end_date`` must parse as ISO-8601 ``YYYY-MM-DD``
      and be ordered — misspelled dates no longer produce empty
      "official" exports with an FDA-formatted cover block.
    * The date-range span is capped at :data:`_MAX_EXPORT_RANGE_DAYS`
      to prevent DoS / cost exhaustion on pathological windows.
    * ``requesting_entity`` is rejected unless it matches
      :data:`_REQUESTING_ENTITY_RE` — a narrow character class that
      cannot carry a formula prefix into the spreadsheet header row.
    * ``Content-Disposition`` is built from parsed ``date`` objects
      passed through :func:`_safe_filename_token`, never raw
      query-string values — blocking CRLF / quote injection of a
      second response header (issue #1283).
    * Zero-row exports return HTTP 404 with a structured body rather
      than an empty FDA-formatted CSV (issue #1291).
    * **Tenant trust (#1106)**: ``tenant_id`` is derived solely from
      the authenticated API key, never from client-supplied
      ``X-Tenant-ID`` / ``X-RegEngine-Tenant-ID`` headers. A mismatch
      between a client-supplied header and the API key's tenant
      raises HTTP 409 ``E_TENANT_MISMATCH`` so cross-tenant FDA
      exports are impossible, even for a legitimately authenticated
      user. We also stop forwarding the caller's raw
      ``X-RegEngine-API-Key`` to the graph service; the compliance
      service authenticates to graph with an internal service secret
      (``REGENGINE_INTERNAL_SECRET``) plus the authenticated
      tenant_id.
    """
    # ---- Tenant binding (#1106) ------------------------------------------
    # The authenticated API key is the sole source of truth for tenant
    # scope. If the client sent an X-Tenant-ID / X-RegEngine-Tenant-ID
    # header that disagrees, reject loudly rather than silently taking
    # the header (which would let any authenticated caller export
    # another tenant's FDA package).
    authenticated_tenant_id = getattr(api_key, "tenant_id", None)
    if not authenticated_tenant_id:
        raise HTTPException(
            status_code=403,
            detail="API key is not associated with a tenant",
        )
    client_tenant_header = (
        request.headers.get("X-Tenant-ID")
        or request.headers.get("X-RegEngine-Tenant-ID")
    )
    if client_tenant_header and client_tenant_header != str(authenticated_tenant_id):
        _logger.warning(
            "fda_export_tenant_mismatch",
            extra={
                "authenticated_tenant": str(authenticated_tenant_id),
                "client_header_tenant": client_tenant_header,
                "key_id": getattr(api_key, "key_id", None),
            },
        )
        raise HTTPException(
            status_code=409,
            detail="E_TENANT_MISMATCH",
        )
    tenant_id = str(authenticated_tenant_id)

    # ---- Input validation -------------------------------------------------
    start = _parse_iso_date("start_date", start_date)
    end = _parse_iso_date("end_date", end_date)
    if end < start:
        raise HTTPException(
            status_code=400,
            detail="end_date must be on or after start_date",
        )
    if (end - start).days > _MAX_EXPORT_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Date range exceeds the {_MAX_EXPORT_RANGE_DAYS}-day "
                "FSMA 204 retention window — narrow the query"
            ),
        )
    if requesting_entity and not _REQUESTING_ENTITY_RE.match(requesting_entity):
        raise HTTPException(
            status_code=400,
            detail=(
                "requesting_entity must match ^[A-Za-z0-9 .,&'-]{0,120}$ "
                "— avoids spreadsheet formula injection and header-"
                "splitting attacks"
            ),
        )

    # ---- Downstream request ----------------------------------------------
    # Use the parsed ISO strings going forward so the graph service sees
    # canonical values, never the raw query params.
    base_params: dict[str, str] = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "limit": str(_GRAPH_PAGE_SIZE),
    }
    if tlc:
        base_params["tlc"] = tlc

    # Build outbound headers. We forward the authenticated tenant_id
    # (never the client-supplied header) and an internal service
    # secret for service-to-service auth. We do NOT forward the
    # caller's raw X-RegEngine-API-Key to the graph service — that
    # header stays at the compliance boundary (#1106).
    headers: dict[str, str] = {
        "X-RegEngine-Tenant-ID": tenant_id,
    }
    internal_secret = settings.internal_service_secret
    if internal_secret:
        headers["X-RegEngine-Internal-Secret"] = internal_secret
    request_id = request.headers.get("X-Request-ID")
    if request_id:
        headers["X-Request-ID"] = request_id

    # ---- Cursor-paginated fetch (issue #1038) ----------------------------
    # Graph service paginates at <=500 events and returns
    # ``has_more=true`` + ``next_cursor`` when additional records exist.
    # Loop until ``has_more`` is false OR the accumulated count exceeds
    # :data:`_MAX_EXPORT_EVENTS` (the hard cap). We do NOT silently
    # truncate the way the old single-page fetch did — exceeding the
    # cap returns HTTP 413 so an operator sees "narrow your query"
    # rather than "recall submission is missing 1500 events".
    events: list[dict] = []
    next_cursor: Optional[str] = None
    try:
        async with resilient_client(timeout=30.0, circuit_name="graph-service") as client:
            while True:
                params = dict(base_params)
                if next_cursor:
                    params["starting_after"] = next_cursor

                resp = await client.get(
                    f"{_GRAPH_SERVICE_URL}/v1/fsma/traceability/search/events",
                    params=params,
                    headers=headers,
                )

                if resp.status_code >= 500:
                    correlation_id = str(uuid.uuid4())
                    _logger.error(
                        "graph_service_5xx",
                        extra={
                            "status": resp.status_code,
                            "body": resp.text[:200],
                            "correlation_id": correlation_id,
                        },
                    )
                    raise HTTPException(
                        status_code=502,
                        detail=f"Upstream service temporarily unavailable (ref: {correlation_id})",
                    )
                if resp.status_code >= 400:
                    correlation_id = str(uuid.uuid4())
                    _logger.warning(
                        "graph_service_4xx",
                        extra={
                            "status": resp.status_code,
                            "body": resp.text[:200],
                            "correlation_id": correlation_id,
                        },
                    )
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=f"Request could not be processed (ref: {correlation_id})",
                    )

                data = resp.json()
                page = data.get("events") or data.get("results") or []
                events.extend(page)

                if len(events) > _MAX_EXPORT_EVENTS:
                    _logger.warning(
                        "fda_export_exceeded_hard_cap",
                        extra={
                            "tenant_id": tenant_id,
                            "cap": _MAX_EXPORT_EVENTS,
                            "accumulated": len(events),
                        },
                    )
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"Export exceeds the {_MAX_EXPORT_EVENTS:,}-event "
                            "hard cap — narrow your date range, TLC, or "
                            "contact support for an async batched job"
                        ),
                    )

                has_more = bool(data.get("has_more"))
                next_cursor = data.get("next_cursor")
                if not has_more or not next_cursor or not page:
                    break
    except CircuitOpenError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Graph service circuit open — retry after {exc.retry_after:.0f}s",
        ) from exc

    # Zero-row exports produce an auditor-facing empty "official"
    # FDA spreadsheet that's easy to misread as "no compliance
    # activity in this period" (issue #1291). Fail loudly instead.
    if not events:
        # Still record the attempted export so a spike in empty queries
        # is observable.
        _audit_logger.info(
            "fda_export_empty",
            extra={
                "export_type": "fda_csv_empty",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "tlc_filter": tlc,
                "requesting_entity": requesting_entity,
                "tenant_id": tenant_id,
                "event_count": 0,
            },
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"No FSMA 204 events found for {start.isoformat()} to "
                f"{end.isoformat()} — verify query parameters"
            ),
        )

    try:
        csv_content = generate_fda_csv(
            events,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            requesting_entity=requesting_entity or "",
        )
    except FSMATimestampError as exc:
        # A malformed event_date in the graph response is not a 5xx —
        # it's a data-quality problem the caller needs to resolve
        # before a submission is valid (issue #1108).
        _logger.warning(
            "fda_export_malformed_event_date",
            extra={"error": str(exc), "tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "FDA export aborted: at least one event carried a "
                "malformed event_date that cannot be truncated into an "
                f"FSMA-204 submission. {exc}"
            ),
        ) from exc

    # Audit log the FDA export (#988), now including ``initiated_at_utc``
    # for FSMA-204 chain-of-custody (#1205 mirror).
    _audit_logger.info(
        "fda_export_generated",
        extra={
            "export_type": "fda_csv",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "tlc_filter": tlc,
            "requesting_entity": requesting_entity,
            "tenant_id": tenant_id,
            "event_count": len(events),
            "initiated_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )

    # Build the filename from parsed ``date`` objects and a sanitized
    # TLC token — never from the raw query string (issue #1283).
    tlc_token = f"_{_safe_filename_token(tlc)}" if tlc else ""
    filename = f"fsma_204_audit_{start.isoformat()}_{end.isoformat()}{tlc_token}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
