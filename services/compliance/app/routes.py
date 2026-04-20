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

from shared.auth import require_api_key
from shared.fda_export import (
    ExportWindowError,
    MAX_EXPORT_WINDOW_DAYS,
    safe_filename,
    safe_filename_token,
    validate_export_window,
)
from shared.resilient_http import resilient_client
from shared.circuit_breaker import CircuitOpenError
from shared.rules.ftl import FTL_CATEGORIES
from .config import settings
from .csv_safety import sanitize_cell
from .fsma_spreadsheet import FSMATimestampError, generate_fda_csv


# ---------------------------------------------------------------------------
# FDA spreadsheet hardening helpers
# ---------------------------------------------------------------------------
#
# EPIC-L (#1655) consolidated the cross-service safe-export primitives into
# ``services/shared/fda_export``. This route now uses
# :func:`validate_export_window` to enforce the 90-day cap mandated by
# EPIC-L ("end_date-only exports permitting full-tenant dumps") and
# :func:`safe_filename` to build ``Content-Disposition`` headers — no
# raw query-string values reach the header value.

# Cursor-pagination parameters for the upstream graph service
# (issue #1038). The graph service caps ``limit`` at 500; we request
# that maximum and loop until ``has_more`` is false. The hard cap
# bounds how much the compliance service is willing to buffer in
# memory before producing the CSV — exceeding it returns HTTP 413
# rather than silently truncating.
_GRAPH_PAGE_SIZE = 500
_MAX_EXPORT_EVENTS = 50_000

# Requesting-entity is rendered into a CSV metadata row that an auditor
# sees at the top of the spreadsheet. Restrict to a very conservative
# set so formula injection cannot land even if the CSV sanitizer is
# ever regressed.
_REQUESTING_ENTITY_RE = re.compile(r"^[A-Za-z0-9 .,&'\-]{0,120}$")

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
# HISTORY (#1203 / #1105): POST /validate was removed on 2026-04-17 as
# orphaned code. It was restored below on 2026-04-20 as part of #1105 but
# now gates STRICTLY on FTL-commodity scope — any caller that reaches this
# endpoint must declare an FDA Food Traceability List commodity, otherwise
# the request is rejected (400 ``E_NON_FTL_FOOD``) rather than returning a
# false-positive compliance stamp. The deeper rule-engine logic (per-CTE
# required-field enforcement, etc.) remains in ``services/shared/rules``
# and is pending the #1203 option-2 rewire.

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
# /validate — FTL-scoped compliance validation (issue #1105)
# ---------------------------------------------------------------------------
#
# The prior /validate endpoint was removed on 2026-04-17 (#1203) as orphaned
# code. Issue #1105 requires that when a caller asks the compliance service
# to validate a configuration, we first confirm the subject food is on the
# FDA Food Traceability List — otherwise a "compliant" response is a false-
# positive certification for a product FSMA 204 does not even cover.
#
# This handler is the catalog-level gate: every request MUST declare an
# ``ftl_commodity``. Non-FTL commodities are rejected with 400
# ``E_NON_FTL_FOOD`` so callers surface the out-of-scope food rather than
# receive a clean stamp.
#
# Per-checklist scope (``applicable_ftl_commodities``) is a follow-up — the
# existing checklist schema has no scope field, so we do not invent one here.
# If the request names a ``checklist_id`` that declares a scope in the
# future, this handler already enforces it via ``E_CHECKLIST_OUT_OF_SCOPE``.


class ValidateRequest(BaseModel):
    """Request body for POST /validate.

    ``ftl_commodity`` is required per #1105 — a caller must declare which
    FDA Food Traceability List commodity the configuration targets. Non-FTL
    commodities (bananas, apples, beef, etc.) are out of FSMA 204 scope
    and are rejected before any further validation runs.

    ``config`` and ``checklist_id`` are optional hooks for the future rules-
    engine reintegration (#1203 option 2). They are carried through today
    for forward compatibility but are not yet evaluated; downstream callers
    should still expect the endpoint to gate on ``ftl_commodity`` first.
    """

    ftl_commodity: str
    config: dict[str, Any] | None = None
    checklist_id: str | None = None
    strict: bool = False


class ValidateResponse(BaseModel):
    """Response body for POST /validate.

    Always returns a structured ``valid`` flag plus lists of ``errors`` and
    ``warnings``. FTL out-of-scope conditions are surfaced as HTTP 400 with
    a structured ``detail`` code rather than a 200 with ``valid=false`` so
    a caller that ignores the body still fails closed.
    """

    valid: bool
    ftl_commodity: str
    errors: list[str] = []
    warnings: list[str] = []


@router.post(
    "/validate",
    dependencies=[Depends(require_api_key)],
    response_model=ValidateResponse,
)
async def validate_compliance(request: ValidateRequest) -> ValidateResponse:
    """Validate an FSMA 204 configuration, gated on FTL commodity scope.

    Enforcement order (#1105):

    1. Request must declare ``ftl_commodity`` (Pydantic 422 if missing).
    2. The commodity must be on the FDA FTL catalog, else 400
       ``E_NON_FTL_FOOD`` — prevents false-positive compliance stamps for
       out-of-scope products.
    3. If a ``checklist_id`` is supplied and the checklist declares an
       ``applicable_ftl_commodities`` scope (future schema), the request's
       commodity must fall inside that scope, else 400
       ``E_CHECKLIST_OUT_OF_SCOPE``. Today's checklists carry no scope
       field, so this branch is a no-op — wired now so the follow-up can
       drop in a scope without another endpoint change.
    """
    # --- Step 1 / 2 — catalog-level FTL gate ------------------------------
    if not _is_ftl_commodity(request.ftl_commodity):
        raise HTTPException(status_code=400, detail="E_NON_FTL_FOOD")

    canonical_commodity = _canonicalize_ftl_commodity(request.ftl_commodity)

    # --- Step 3 — per-checklist scope (future-proofed, not yet enforced) --
    if request.checklist_id is not None:
        checklist = _CHECKLIST_INDEX.get(request.checklist_id)
        if checklist is None:
            raise HTTPException(
                status_code=404,
                detail=f"Checklist '{request.checklist_id}' not found",
            )
        # ``applicable_ftl_commodities`` is not part of the current
        # ``ComplianceChecklist`` schema — read defensively so that the
        # day a scope field is added, this gate activates automatically.
        scope = getattr(checklist, "applicable_ftl_commodities", None)
        if scope:
            normalized_scope = {_canonicalize_ftl_commodity(s) for s in scope}
            if canonical_commodity not in normalized_scope:
                raise HTTPException(
                    status_code=400,
                    detail="E_CHECKLIST_OUT_OF_SCOPE",
                )

    # --- Basic validation stub --------------------------------------------
    # The deeper rule-engine logic lives in ``services/shared/rules`` and
    # will be wired in per #1203 option 2. For now we surface a clean
    # response so callers can rely on the FTL gate being authoritative.
    return ValidateResponse(
        valid=True,
        ftl_commodity=canonical_commodity,
        errors=[],
        warnings=[],
    )


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

    Hardening applied in this handler (EPIC-L / #1655, prior #1272 /
    #1283 / #1291):

    * ``start_date`` and ``end_date`` are both required and pass
      through :func:`shared.fda_export.validate_export_window`, which
      enforces ISO-8601 format, strict ordering, and a 90-day span cap
      — "end_date-only exports permitting full-tenant dumps" from
      EPIC-L are now impossible by construction.
    * ``requesting_entity`` is rejected unless it matches
      :data:`_REQUESTING_ENTITY_RE` — a narrow character class that
      cannot carry a formula prefix into the spreadsheet header row.
    * ``Content-Disposition`` is built from parsed ``date`` objects
      passed through :func:`shared.fda_export.safe_filename`, never
      raw query-string values — blocking CRLF / quote injection of a
      second response header.
    * Zero-row exports return HTTP 404 with a structured body rather
      than an empty FDA-formatted CSV.
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
    try:
        window = validate_export_window(start_date, end_date)
    except ExportWindowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    start = window.start
    end = window.end
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
    # TLC token — never from the raw query string. ``safe_filename``
    # is the shared EPIC-L primitive so ingestion and compliance
    # produce structurally identical attachment headers.
    filename = safe_filename(
        "fsma_204_audit",
        scope=safe_filename_token(tlc) if tlc else None,
        start=start,
        end=end,
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
