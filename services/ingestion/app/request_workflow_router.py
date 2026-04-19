"""
Request-Response Workflow Router.

Provides API endpoints for FDA 24-hour response readiness — the explicit
product loop from request intake through scoped response package submission.

Endpoints:
    GET    /api/v1/requests                       — List active request cases
    POST   /api/v1/requests                       — Create request case
    GET    /api/v1/requests/{id}                   — Get request case detail
    PATCH  /api/v1/requests/{id}/scope             — Update scope
    POST   /api/v1/requests/{id}/collect           — Collect records for scope
    POST   /api/v1/requests/{id}/gap-analysis      — Run gap analysis
    POST   /api/v1/requests/{id}/assemble          — Assemble response package
    POST   /api/v1/requests/{id}/signoff           — Add signoff
    POST   /api/v1/requests/{id}/submit            — Submit package
    POST   /api/v1/requests/{id}/amend             — Create amendment
    GET    /api/v1/requests/{id}/packages          — Package version history
    GET    /api/v1/requests/{id}/blockers          — Check blocking defects
    GET    /api/v1/requests/deadlines              — Deadline urgency for all cases
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.authz import require_permission, IngestionPrincipal
from app.tenant_validation import validate_tenant_id, resolve_tenant
from shared.database import get_db_session

# Backwards-compat alias used by tests:
# ``app.dependency_overrides[_get_db_session]`` in the test harness must
# match the exact callable passed to ``Depends()`` below. Mirrors the
# pattern already in ``webhook_router_v2.py``.
_get_db_session = get_db_session

logger = logging.getLogger("request-workflow")

router = APIRouter(prefix="/api/v1/requests", tags=["Request-Response Workflow"])


def _get_service(db_session):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    from shared.request_workflow import RequestWorkflow
    return RequestWorkflow(db_session)




# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class CreateRequestCase(BaseModel):
    requesting_party: str = "FDA"
    request_channel: str = "email"
    scope_type: str = "tlc_trace"
    scope_description: Optional[str] = None
    affected_products: List[str] = Field(default_factory=list)
    affected_lots: List[str] = Field(default_factory=list)
    affected_facilities: List[str] = Field(default_factory=list)
    response_hours: int = 24


class UpdateScope(BaseModel):
    scope_description: Optional[str] = None
    affected_products: Optional[List[str]] = None
    affected_lots: Optional[List[str]] = None
    affected_facilities: Optional[List[str]] = None


class SignoffRequest(BaseModel):
    signoff_type: str  # scope_approval, package_review, final_approval, submission_authorization
    signed_by: str
    notes: Optional[str] = None


class SubmitRequest(BaseModel):
    submitted_to: Optional[str] = None
    submitted_by: str
    submission_method: str = "export"
    submission_notes: Optional[str] = None
    force: bool = Field(
        default=False,
        description="Override blocking defects (logged as audit event).",
    )


class AmendRequest(BaseModel):
    generated_by: str
    amendment_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="List active request cases",
    description="Returns request cases with countdown timer info, ordered by deadline urgency.",
)
async def list_requests(
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    cases = svc.get_active_cases(tid)
    return {"tenant_id": tid, "cases": cases, "total": len(cases)}


@router.post(
    "",
    summary="Create request case",
    description="Open a new FDA/auditor request case with deadline and scope.",
    status_code=201,
)
async def create_request(
    body: CreateRequestCase,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    case_id = svc.create_request_case(
        tenant_id=tid,
        requesting_party=body.requesting_party,
        request_channel=body.request_channel,
        scope_type=body.scope_type,
        scope_description=body.scope_description,
        affected_products=body.affected_products,
        affected_lots=body.affected_lots,
        affected_facilities=body.affected_facilities,
        response_hours=body.response_hours,
    )
    return {"request_case_id": case_id, "status": "intake"}


# NOTE: /deadlines MUST come before /{request_case_id} to avoid route shadowing
@router.get(
    "/deadlines",
    summary="Check deadline status for all active cases",
    description=(
        "Returns urgency classification for all active request cases: "
        "overdue (past deadline), critical (<2h), urgent (<6h), normal (>6h). "
        "Use for dashboard alerts and background monitoring."
    ),
)
async def check_deadlines(
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    cases = svc.check_deadline_status(tid)
    overdue = [c for c in cases if c["urgency"] == "overdue"]
    critical = [c for c in cases if c["urgency"] == "critical"]
    return {
        "tenant_id": tid,
        "cases": cases,
        "total": len(cases),
        "overdue_count": len(overdue),
        "critical_count": len(critical),
        "alert": len(overdue) > 0 or len(critical) > 0,
    }


@router.get(
    "/{request_case_id}",
    summary="Get request case detail",
)
async def get_request(
    request_case_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    cases = svc.get_active_cases(tid)
    for c in cases:
        if c.get("request_case_id") == request_case_id:
            return c
    raise HTTPException(status_code=404, detail="Request case not found")


@router.patch(
    "/{request_case_id}/scope",
    summary="Update request scope",
)
async def update_scope(
    request_case_id: str,
    body: UpdateScope,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    svc.update_scope(
        tenant_id=tid,
        request_case_id=request_case_id,
        affected_products=body.affected_products,
        affected_lots=body.affected_lots,
        affected_facilities=body.affected_facilities,
        scope_description=body.scope_description,
    )
    return {"request_case_id": request_case_id, "status": "scoping"}


@router.post(
    "/{request_case_id}/collect",
    summary="Collect records matching scope",
)
async def collect_records(
    request_case_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    records = svc.collect_records(tid, request_case_id)
    return {
        "request_case_id": request_case_id,
        "records_collected": len(records),
        "status": "collecting",
    }


@router.post(
    "/{request_case_id}/gap-analysis",
    summary="Run gap analysis on collected records",
)
async def run_gap_analysis(
    request_case_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    gaps = svc.run_gap_analysis(tid, request_case_id)
    return {
        "request_case_id": request_case_id,
        "gap_analysis": gaps,
        "status": "gap_analysis",
    }


@router.post(
    "/{request_case_id}/assemble",
    summary="Assemble response package",
    description="Create an immutable, SHA-256 sealed response package snapshot.",
)
async def assemble_package(
    request_case_id: str,
    generated_by: str = Query("system"),
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    package = svc.assemble_response_package(tid, request_case_id, generated_by)
    return {
        "request_case_id": request_case_id,
        "package_id": package.get("package_id"),
        "version_number": package.get("version_number"),
        "package_hash": package.get("package_hash"),
        "status": "assembling",
    }


@router.post(
    "/{request_case_id}/signoff",
    summary="Add signoff to request case",
)
async def add_signoff(
    request_case_id: str,
    body: SignoffRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    svc.add_signoff(
        tenant_id=tid,
        request_case_id=request_case_id,
        signoff_type=body.signoff_type,
        signed_by=body.signed_by,
        notes=body.notes,
    )
    return {"request_case_id": request_case_id, "signoff_type": body.signoff_type, "status": "signed"}


@router.post(
    "/{request_case_id}/submit",
    summary="Submit response package",
    description="Mark the response as submitted. Creates immutable submission log entry.",
)
async def submit_package(
    request_case_id: str,
    body: SubmitRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    try:
        result = svc.submit_package(
            tenant_id=tid,
            request_case_id=request_case_id,
            submitted_to=body.submitted_to,
            submitted_by=body.submitted_by,
            submission_method=body.submission_method,
            submission_notes=body.submission_notes,
            force=body.force,
        )
    except ValueError as e:
        if "blocking defect" in str(e).lower():
            raise HTTPException(status_code=422, detail=str(e))
        raise
    return {
        "request_case_id": request_case_id,
        "submission_id": result.get("submission_id"),
        "status": "submitted",
    }


@router.post(
    "/{request_case_id}/amend",
    summary="Create post-submission amendment",
    description="Reassemble package with diff against prior version.",
)
async def create_amendment(
    request_case_id: str,
    body: AmendRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    package = svc.create_amendment(tid, request_case_id, body.generated_by)
    return {
        "request_case_id": request_case_id,
        "package_id": package.get("package_id"),
        "version_number": package.get("version_number"),
        "diff_from_previous": package.get("diff_from_previous"),
        "status": "amended",
    }


@router.get(
    "/{request_case_id}/packages",
    summary="Get package version history",
)
async def package_history(
    request_case_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    packages = svc.get_package_history(tid, request_case_id)
    return {
        "request_case_id": request_case_id,
        "packages": packages,
        "total": len(packages),
    }


# ---------------------------------------------------------------------------
# Enforcement Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{request_case_id}/blockers",
    summary="Check blocking defects",
    description=(
        "Returns all defects that prevent this request case from being submitted. "
        "Critical rule failures, unresolved exceptions, unevaluated events, "
        "missing signoffs, and identity ambiguity are all checked."
    ),
)
async def check_blockers(
    request_case_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("requests.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    result = svc.check_blocking_defects(tid, request_case_id)
    return {
        "request_case_id": request_case_id,
        **result,
    }
