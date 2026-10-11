from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from shared.auth import APIKey, require_api_key
from shared.database import get_db_session
from shared.fda_export import (
    ExportWindowError,
    safe_filename,
    safe_filename_token,
    validate_export_window,
)
from shared.rules.engine import RulesEngine
from shared.rules.ftl import FTL_CATEGORIES
from shared.rules.types import EvaluationSummary, RuleEvaluationResult

from .fsma_spreadsheet import FSMAEventError, FSMATimestampError, generate_fda_csv

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

# Hard cap on events buffered into one synchronous FDA spreadsheet.
# Exceeding it returns HTTP 413 rather than silently truncating (#1038).
_MAX_EXPORT_EVENTS = 50_000

# Requesting-entity is rendered into a CSV metadata row that an auditor
# sees at the top of the spreadsheet. Restrict to a very conservative
# set so formula injection cannot land even if the CSV sanitizer is
# ever regressed.
_REQUESTING_ENTITY_RE = re.compile(r"^[A-Za-z0-9 .,&'\-]{0,120}$")

_logger = logging.getLogger(__name__)
_audit_logger = logging.getLogger("compliance-audit")

router = APIRouter(tags=["fsma-compliance"])


def _canonicalize_ftl_commodity(value: str) -> str:
    """Normalize user-facing FTL commodity labels to catalog keys."""
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ").strip().lower())


# The catalog stores hyphenated entries ("fresh-cut fruits") while
# _canonicalize_ftl_commodity folds hyphens to spaces, so a direct
# membership test against FTL_CATEGORIES rejects every spelling of
# those commodities. This lookup resolves any accepted spelling back
# to the engine-canonical catalog form (the lower-case catalog entry),
# which is what the rules engine matches in get_ftl_category (it only
# lower-cases and strips, so a space-folded stamp would classify an
# in-scope food as not-FTL scoped).
_FTL_LOOKUP: dict[str, str] = {_canonicalize_ftl_commodity(entry): entry.strip().lower() for entry in FTL_CATEGORIES}


def _is_ftl_commodity(value: str) -> bool:
    return _canonicalize_ftl_commodity(value) in _FTL_LOOKUP


def _resolve_ftl_commodity(value: str) -> str | None:
    """Return the engine-canonical catalog form of a commodity, or None."""
    return _FTL_LOOKUP.get(_canonicalize_ftl_commodity(value))


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ComplianceRequirement(BaseModel):
    id: str
    title: str
    description: str
    category: str | None = None
    priority: str | None = None  # LOW | MEDIUM | HIGH | CRITICAL
    status: str | None = None  # NOT_STARTED | IN_PROGRESS | COMPLIANT | NON_COMPLIANT


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
            "Confirm fsma_rules.json is present in the compliance app directory."
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

# Industry filter aliases (#2851).
#
# ``checklists[].industry`` in fsma_rules.json holds the industry *display
# name* ("Dairy", "Fresh Produce"), but ``GET /industries`` hands callers the
# *id* ("dairy", "fresh-produce"). Matching the query param against the
# display name alone meant ``?industry=fresh-produce``, ``?industry=deli-
# prepared`` and ``?industry=shell-eggs`` — three of the five ids this API
# publishes — returned an empty list. An empty checklist is not an error
# response, so a client reads it as "this industry has no requirements".
#
# Both spellings resolve here. An unrecognised value still falls through to a
# literal comparison and yields an empty list, so the documented
# unknown-industry behaviour is unchanged.
_INDUSTRY_FILTER_ALIASES: dict[str, str] = {
    alias.lower(): _i["name"].lower() for _i in _rules["industries"] for alias in (_i["id"], _i["name"])
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
#
# HISTORY (#1203 / #1105): POST /validate was removed on 2026-04-17 as
# orphaned code. It was restored on 2026-04-20 as part of #1105, gating
# STRICTLY on FTL-commodity scope — any caller that reaches this endpoint
# must declare an FDA Food Traceability List commodity, otherwise the
# request is rejected (400 ``E_NON_FTL_FOOD``) rather than returning a
# false-positive compliance stamp. The #1203 option-2 rewire landed with
# WS-9: verdicts now derive from the versioned rules engine in
# ``services/shared/rules`` (per-CTE KDE enforcement), replacing the
# endpoint's former lightweight local contract check.


@router.get("/industries", dependencies=[Depends(require_api_key)], response_model=IndustriesResponse)
async def list_industries() -> IndustriesResponse:
    return {"industries": [i.model_dump() for i in _INDUSTRIES], "total": len(_INDUSTRIES)}


@router.get("/checklists", dependencies=[Depends(require_api_key)], response_model=ChecklistsResponse)
async def list_checklists(industry: str | None = None) -> ChecklistsResponse:
    results = _CHECKLISTS
    if industry:
        key = industry.strip().lower()
        wanted = _INDUSTRY_FILTER_ALIASES.get(key, key)
        results = [c for c in results if c.industry.lower() == wanted]
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

    ``config``, when supplied, is evaluated against the versioned rules
    engine in ``services/shared/rules`` (#1203 option 2): ``cte_type``
    selects the per-CTE ruleset and the remaining keys are treated as
    event fields/KDEs (nested under ``kdes`` or flat). ``checklist_id``
    remains a scope hook — the endpoint still gates on ``ftl_commodity``
    first.
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

    ``rules_evaluated`` / ``no_verdict_reason`` (#1203 option 2) expose the
    rules-engine provenance of the verdict: how many active rule
    definitions applied, and — when the engine could not produce a verdict
    (``no_rules_loaded``, ``ftl_classification_missing``) — why. A
    no-verdict outcome is reported as ``valid=false`` with a ``NO_VERDICT``
    error, never as a silent pass.
    """

    valid: bool
    ftl_commodity: str
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    rules_evaluated: int = 0
    no_verdict_reason: str | None = None


_ALLOWED_VALIDATE_CTE_TYPES = {
    "HARVESTING",
    "COOLING",
    "INITIAL_PACKING",
    "FIRST_LAND_BASED_RECEIVING",
    "SHIPPING",
    "RECEIVING",
    "TRANSFORMATION",
}


def _validation_issue(
    path: str,
    code: str,
    message: str,
    *,
    suggestion: str | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {"path": path, "code": code, "message": message}
    if suggestion is not None:
        issue["suggestion"] = suggestion
    return issue


# ---------------------------------------------------------------------------
# #1203 option-2 rewire — /validate verdicts derive from services/shared/rules
# ---------------------------------------------------------------------------
#
# The previous handler ran a local 8-field contract check
# (``_validate_fsma204_config``). That duplicated — and drifted from — the
# versioned per-CTE rules in ``services/shared/rules``, which is what the
# ingestion paths actually enforce. The mapping below converts the caller's
# ``config`` into the engine's canonical event shape, evaluates it against
# the active rule definitions (``fsma.rule_definitions``), and translates
# the ``EvaluationSummary`` back into this endpoint's response contract.
#
# The drift test in
# ``services/shared/tests/test_rules_enforcement_manifest.py`` asserts this
# module keeps importing ``RulesEngine`` so the endpoint cannot silently
# revert to a local stub.

# Engine-canonical top-level event fields (mirrors the ingestion
# rules-router request model). Config keys matching these pass through
# at the top level; everything else lands under ``kdes.``.
_ENGINE_TOP_LEVEL_FIELDS = {
    "traceability_lot_code",
    "product_reference",
    "quantity",
    "unit_of_measure",
    "from_facility_reference",
    "to_facility_reference",
    "from_entity_reference",
    "to_entity_reference",
    "transport_reference",
}

# Legacy /validate config keys → engine-canonical names.
_CONFIG_KEY_ALIASES = {
    "tlc": "traceability_lot_code",
    "product_description": "product_reference",
}


def _config_to_engine_event(
    config: dict[str, Any],
    canonical_commodity: str,
) -> dict[str, Any]:
    """Map a /validate ``config`` payload to the engine's canonical event shape.

    ``ftl_category`` is stamped from the endpoint's own FTL gate — the
    commodity was already verified against the FTL catalog, so the engine
    classifies the event as on-FTL and applies the full per-CTE ruleset.
    ``cte_type`` becomes the engine's lower-case ``event_type``. Any key
    that is not engine-canonical is preserved under ``kdes.`` so callers
    can supply KDEs either nested (``{"kdes": {...}}``) or flat.
    """
    event: dict[str, Any] = {
        "event_id": f"validate:{uuid.uuid4()}",
        "event_type": str(config.get("cte_type", "")).strip().lower(),
        "ftl_category": canonical_commodity,
    }
    kdes: dict[str, Any] = {}
    raw_kdes = config.get("kdes")
    if isinstance(raw_kdes, dict):
        kdes.update(raw_kdes)
    for key, value in config.items():
        if key in ("cte_type", "kdes"):
            continue
        target = _CONFIG_KEY_ALIASES.get(key, key)
        if target in _ENGINE_TOP_LEVEL_FIELDS:
            event[target] = value
        else:
            kdes.setdefault(key, value)
    event["kdes"] = kdes
    return event


def _rule_result_issue(result: RuleEvaluationResult, code: str) -> dict[str, Any]:
    """Translate one engine rule result into the endpoint's issue shape."""
    path = "config"
    for evidence in result.evidence_fields_inspected:
        field = evidence.get("field")
        if field:
            path = str(field)
            break
    issue = _validation_issue(
        path,
        code,
        result.why_failed or result.rule_title,
        suggestion=result.remediation_suggestion,
    )
    issue["rule_id"] = result.rule_id
    issue["rule_title"] = result.rule_title
    issue["severity"] = result.severity
    if result.citation_reference:
        issue["citation_reference"] = result.citation_reference
    return issue


def _summary_to_validate_response(
    summary: EvaluationSummary,
    canonical_commodity: str,
    *,
    strict: bool,
) -> "ValidateResponse":
    """Map an ``EvaluationSummary`` onto the /validate response contract.

    Fail-closed semantics (#1346/#1347 carried through to this endpoint):
    a tri-state ``compliant is None`` (no rules loaded / nothing evaluated)
    is NEVER reported as ``valid=true`` — it surfaces as a structured
    ``NO_VERDICT`` error so a caller cannot mistake "not evaluated" for
    "compliant".
    """
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for result in summary.results:
        if result.result == "fail":
            errors.append(_rule_result_issue(result, "RULE_FAILED"))
        elif result.result == "error":
            errors.append(_rule_result_issue(result, "RULE_EVALUATION_ERROR"))
        elif result.result == "warn":
            if strict:
                errors.append(_rule_result_issue(result, "STRICT_MODE_WARNING"))
            else:
                warnings.append(_rule_result_issue(result, "RULE_WARNING"))

    if summary.compliant is None:
        reason = summary.no_verdict_reason or "nothing_evaluated"
        errors.append(
            _validation_issue(
                "config",
                "NO_VERDICT",
                (
                    "The rules engine produced no compliance verdict "
                    f"({reason}). A missing verdict is not a pass — supply a "
                    "valid cte_type and ensure rule definitions are seeded."
                ),
            )
        )

    valid = summary.compliant is True and not errors
    return ValidateResponse(
        valid=valid,
        ftl_commodity=canonical_commodity,
        errors=errors,
        warnings=warnings,
        rules_evaluated=summary.total_rules,
        no_verdict_reason=summary.no_verdict_reason,
    )


@router.post(
    "/validate",
    response_model=ValidateResponse,
)
async def validate_compliance(
    request: ValidateRequest,
    api_key: APIKey = Depends(require_api_key),
    db=Depends(get_db_session),
) -> ValidateResponse:
    """Validate an FSMA 204 configuration against the versioned rules engine.

    Enforcement order (#1105 gate + #1203 option-2 rewire):

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
    4. When a ``config`` is supplied, it is mapped to the engine's
       canonical event shape and evaluated against the active rule
       definitions in ``services/shared/rules`` (#1203 option 2) — the
       same per-CTE FSMA 204 rules the ingestion paths enforce. The
       evaluation is advisory (``persist=False``): nothing is written to
       ``fsma.rule_evaluations``. A no-verdict evaluation fails closed
       (``valid=false`` + ``NO_VERDICT``), and requesting rule evaluation
       without a database available returns 503 rather than a fabricated
       verdict.

    ``config.cte_type`` must be one of the FSMA 204 CTE types — it selects
    which per-CTE rules apply. KDEs may be supplied nested
    (``config.kdes.harvest_date``) or flat (``config.harvest_date``);
    ``tlc`` and ``product_description`` are aliased to the engine's
    ``traceability_lot_code`` / ``product_reference``.
    """
    # --- Step 1 / 2 — catalog-level FTL gate ------------------------------
    # Resolve to the engine-canonical catalog form (None when not FTL).
    # The space-folded canonical form is kept for the scope comparison
    # and the response echo; the catalog form is what the engine event
    # is stamped with so get_ftl_category recognizes it.
    canonical_commodity = _canonicalize_ftl_commodity(request.ftl_commodity)
    engine_commodity = _FTL_LOOKUP.get(canonical_commodity)
    if engine_commodity is None:
        raise HTTPException(status_code=400, detail="E_NON_FTL_FOOD")

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

    # --- Step 4 — rules-engine evaluation (#1203 option 2) ----------------
    if request.config is None:
        # Nothing to validate: the request passed the FTL scope gate but
        # supplied no configuration. This is NOT a compliance verdict on
        # any event — rules_evaluated=0 makes the distinction machine-readable.
        return ValidateResponse(
            valid=True,
            ftl_commodity=canonical_commodity,
            rules_evaluated=0,
        )

    cte_value = request.config.get("cte_type")
    # Strip to match _config_to_engine_event, which strips before lowercasing:
    # padded input must reach the engine, not die here as INVALID_CTE_TYPE.
    cte_type = cte_value.strip().upper() if isinstance(cte_value, str) else None
    if cte_type not in _ALLOWED_VALIDATE_CTE_TYPES:
        # Fail fast with a structured error rather than handing the engine
        # an event_type no rule targets (which would surface as a less
        # actionable NO_VERDICT).
        return ValidateResponse(
            valid=False,
            ftl_commodity=canonical_commodity,
            errors=[
                _validation_issue(
                    "cte_type",
                    "INVALID_CTE_TYPE",
                    "cte_type must be a valid FSMA 204 CTE type",
                )
            ],
        )

    if db is None:
        # Rule definitions live in the database. Refuse rather than
        # fabricate a verdict from nothing (fail-closed, #1347).
        raise HTTPException(status_code=503, detail="Database unavailable")

    event_data = _config_to_engine_event(request.config, engine_commodity)
    engine = RulesEngine(db)
    summary = engine.evaluate_event(
        event_data,
        persist=False,
        tenant_id=api_key.tenant_id,
    )
    return _summary_to_validate_response(
        summary,
        canonical_commodity,
        strict=request.strict,
    )


# ---------------------------------------------------------------------------
# FDA Audit Spreadsheet Export
# ---------------------------------------------------------------------------


class EventStorageUnavailable(Exception):
    """Event store could not be reached. Must not be reported as an empty export."""


def _load_fsma_audit_events(
    *,
    tenant_id: str,
    start_date: str,
    end_date: str,
    tlc: str | None,
    limit: int,
) -> list[dict]:
    """Load spreadsheet events in-process from Postgres (#2862).

    Reuses the ingestion recall-export query (tenant + date window + optional
    TLC). Graph HTTP is not used: that service is experimental, disabled in
    production, and previously defaulted to a dead hostname whose connect
    failures were indistinguishable from "no events".
    """
    from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError

    filters = {
        "tenant_id": tenant_id,
        "product": None,
        "location": None,
        "tlc": tlc,
        "event_type": None,
        "start_date": start_date,
        "end_date": end_date,
    }
    db_session = None
    try:
        from shared.cte_persistence import CTEPersistence
        from shared.database import SessionLocal

        try:
            from services.ingestion.app.fda_export.queries import (
                build_recall_where_clause,
                build_recall_where_clause_canonical,
                export_v1_reads_canonical,
                fetch_recall_events,
                fetch_recall_events_canonical,
                rows_to_event_dicts,
            )
        except ImportError:  # standalone compliance entrypoint has services/ on path
            from ingestion.app.fda_export.queries import (
                build_recall_where_clause,
                build_recall_where_clause_canonical,
                export_v1_reads_canonical,
                fetch_recall_events,
                fetch_recall_events_canonical,
                rows_to_event_dicts,
            )

        db_session = SessionLocal()
        CTEPersistence(db_session).set_tenant_context(tenant_id)
        if export_v1_reads_canonical():
            where_clause, params = build_recall_where_clause_canonical(**filters)
            rows = fetch_recall_events_canonical(db_session, where_clause, params, limit=limit)
        else:
            where_clause, params = build_recall_where_clause(**filters)
            rows = fetch_recall_events(db_session, where_clause, params, limit=limit)
        return rows_to_event_dicts(rows)
    except (OperationalError, InterfaceError, DBAPIError, OSError, ConnectionError, TimeoutError, ImportError) as exc:
        raise EventStorageUnavailable(str(exc)) from exc
    finally:
        if db_session is not None:
            db_session.close()


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
      than an empty FDA-oriented CSV.
    * Event storage connect/timeout failures return HTTP 503, never an
      empty-result 404 (#2862).
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
    client_tenant_header = request.headers.get("X-Tenant-ID") or request.headers.get("X-RegEngine-Tenant-ID")
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

    # ---- In-process event load (#2862) -----------------------------------
    # Postgres via the ingestion recall-export query. Do not HTTP to graph:
    # that host is experimental and a connect failure must never look like
    # an empty-result 404.
    try:
        events = _load_fsma_audit_events(
            tenant_id=tenant_id,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            tlc=tlc,
            limit=_MAX_EXPORT_EVENTS + 1,
        )
    except EventStorageUnavailable as exc:
        correlation_id = str(uuid.uuid4())
        _logger.error(
            "fda_export_storage_unavailable",
            extra={
                "tenant_id": tenant_id,
                "error": str(exc),
                "correlation_id": correlation_id,
            },
        )
        raise HTTPException(
            status_code=503,
            detail=f"Event storage unavailable (ref: {correlation_id})",
        ) from exc

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
            detail=(f"No FSMA 204 events found for {start.isoformat()} to {end.isoformat()} — verify query parameters"),
        )

    try:
        csv_content = generate_fda_csv(
            events,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            requesting_entity=requesting_entity or "",
        )
    except (FSMATimestampError, FSMAEventError) as exc:
        # A malformed event_date or malformed event shape in the loaded
        # events is not a 5xx — it's a data-quality problem the caller
        # needs to resolve before a submission is valid (issue #1108).
        # Failing loudly here also keeps one bad record from taking the
        # whole export down as an unhandled 500.
        _logger.warning(
            "fda_export_malformed_event",
            extra={"error": str(exc), "tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "FDA export aborted: at least one event carried malformed "
                "data that cannot be rendered into an FSMA-204 submission. "
                f"{exc}"
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
