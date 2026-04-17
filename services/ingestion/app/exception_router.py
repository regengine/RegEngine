"""
Exception & Remediation Queue Router.

Provides API endpoints for managing compliance exception cases —
turning record defects into managed operational work with ownership,
deadlines, waivers, and signoff chains.

Endpoints:
    GET    /api/v1/exceptions              — List/filter exception cases
    GET    /api/v1/exceptions/{case_id}    — Get exception detail
    POST   /api/v1/exceptions              — Create exception case
    PATCH  /api/v1/exceptions/{case_id}/assign   — Assign owner
    PATCH  /api/v1/exceptions/{case_id}/resolve  — Resolve exception
    PATCH  /api/v1/exceptions/{case_id}/waive    — Waive exception
    GET    /api/v1/exceptions/{case_id}/comments — List comments
    POST   /api/v1/exceptions/{case_id}/comments — Add comment
    GET    /api/v1/exceptions/stats/blocking     — Unresolved blocking count
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from shared.pagination import PaginationParams
from app.authz import require_permission, IngestionPrincipal
from app.tenant_validation import validate_tenant_id, resolve_tenant
from shared.database import get_db_session

logger = logging.getLogger("exception-queue")

router = APIRouter(prefix="/api/v1/exceptions", tags=["Exception Queue"])


def _get_service(db_session):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    from shared.exception_queue import ExceptionQueueService
    return ExceptionQueueService(db_session)


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class CreateExceptionRequest(BaseModel):
    severity: str = "warning"
    linked_event_ids: List[str] = Field(default_factory=list)
    linked_rule_evaluation_ids: List[str] = Field(default_factory=list)
    source_supplier: Optional[str] = None
    source_facility_reference: Optional[str] = None
    rule_category: Optional[str] = None
    recommended_remediation: Optional[str] = None
    due_date: Optional[str] = None


class AssignRequest(BaseModel):
    owner_user_id: str


class ResolveRequest(BaseModel):
    resolution_summary: str
    resolved_by: str


class WaiveRequest(BaseModel):
    waiver_reason: str
    waiver_approved_by: str


class AddCommentRequest(BaseModel):
    author_user_id: str
    comment_text: str
    comment_type: str = "note"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="List exception cases",
    description="Filter exceptions by severity, status, supplier, facility, due date, and rule category.",
)
async def list_exceptions(
    tenant_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source_supplier: Optional[str] = Query(None),
    source_facility_reference: Optional[str] = Query(None),
    due_before: Optional[str] = Query(None),
    rule_category: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    principal: IngestionPrincipal = Depends(require_permission("exceptions.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    cases = svc.list_exceptions(
        tenant_id=tid,
        severity=severity,
        status=status,
        source_supplier=source_supplier,
        source_facility_reference=source_facility_reference,
        due_before=due_before,
        rule_category=rule_category,
        limit=pagination.limit,
        offset=pagination.skip,
    )
    return {"tenant_id": tid, "cases": cases, "total": len(cases), "skip": pagination.skip, "limit": pagination.limit}


@router.get(
    "/stats/blocking",
    summary="Get unresolved blocking exception count",
    description="Count of critical-severity exceptions not yet resolved or waived.",
)
async def blocking_count(
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("exceptions.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    count = svc.get_unresolved_blocking_count(tid)
    return {"tenant_id": tid, "blocking_count": count}


@router.get(
    "/{case_id}",
    summary="Get exception detail",
)
async def get_exception(
    case_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("exceptions.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    case = svc.get_exception(tid, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Exception case not found")
    return case


@router.post(
    "",
    summary="Create exception case",
    status_code=201,
)
async def create_exception(
    body: CreateExceptionRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("exceptions.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    case_id = svc.create_exception(
        tenant_id=tid,
        severity=body.severity,
        linked_event_ids=body.linked_event_ids,
        linked_rule_evaluation_ids=body.linked_rule_evaluation_ids,
        source_supplier=body.source_supplier,
        source_facility_reference=body.source_facility_reference,
        rule_category=body.rule_category,
        recommended_remediation=body.recommended_remediation,
        due_date=body.due_date,
    )
    return {"case_id": case_id, "status": "created"}


@router.patch(
    "/{case_id}/assign",
    summary="Assign owner to exception",
)
async def assign_owner(
    case_id: str,
    body: AssignRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("exceptions.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    svc.assign_owner(tid, case_id, body.owner_user_id)
    return {"case_id": case_id, "owner_user_id": body.owner_user_id, "status": "assigned"}


@router.patch(
    "/{case_id}/resolve",
    summary="Resolve exception case",
)
async def resolve_exception(
    case_id: str,
    body: ResolveRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("exceptions.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    svc.resolve_exception(tid, case_id, body.resolution_summary, body.resolved_by)
    return {"case_id": case_id, "status": "resolved"}


@router.patch(
    "/{case_id}/waive",
    summary="Waive exception (requires reason + approver)",
)
async def waive_exception(
    case_id: str,
    body: WaiveRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("exceptions.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    svc.waive_exception(tid, case_id, body.waiver_reason, body.waiver_approved_by)
    return {"case_id": case_id, "status": "waived"}


@router.get(
    "/{case_id}/comments",
    summary="List comments on exception",
)
async def list_comments(
    case_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("exceptions.read")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    comments = svc.list_comments(tid, case_id)
    return {"case_id": case_id, "comments": comments, "total": len(comments)}


@router.post(
    "/{case_id}/comments",
    summary="Add comment to exception",
    status_code=201,
)
async def add_comment(
    case_id: str,
    body: AddCommentRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("exceptions.write")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(tenant_id, principal)
    svc = _get_service(db_session)
    comment_id = svc.add_comment(tid, case_id, body.author_user_id, body.comment_text, body.comment_type)
    return {"comment_id": comment_id, "status": "created"}
