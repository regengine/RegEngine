"""Agent operator review endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from shared.agent_operator_view import (
    AgentArtifactTimelineResponse,
    AgentReviewDecisionRequest,
    AgentReviewDecisionResponse,
    AgentReviewListResponse,
    ArtifactType,
    ReviewStatus,
    fetch_agent_artifact_timeline,
    fetch_agent_review_items,
    upsert_agent_artifact_review,
)
from shared.tenant_context import set_rls_tenant_id, set_tenant_guc
from sqlalchemy.orm import Session

from .dependencies import get_current_user, get_session
from .models import TenantContext
from .sqlalchemy_models import UserModel

router = APIRouter(prefix="/agent-reviews", tags=["agent-reviews"])


@router.get(
    "/items",
    response_model=AgentReviewListResponse,
    summary="List agent review items for the active tenant",
)
async def list_agent_review_items(
    tenant_id: Optional[UUID] = Query(
        default=None,
        description="Tenant to inspect. Sysadmin only; regular operators use their auth tenant.",
    ),
    ingestion_run_id: Optional[UUID] = None,
    review_status: Optional[ReviewStatus] = None,
    artifact_type: Optional[ArtifactType] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> AgentReviewListResponse:
    """Return the V1 operator read model for advisory agent artifacts."""

    resolved_tenant = _resolve_operator_tenant_id(
        db,
        current_user=current_user,
        requested_tenant_id=tenant_id,
    )
    try:
        return fetch_agent_review_items(
            db,
            tenant_id=str(resolved_tenant),
            ingestion_run_id=str(ingestion_run_id) if ingestion_run_id else None,
            review_status=review_status,
            artifact_type=artifact_type,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/items/{artifact_id}/review",
    response_model=AgentReviewDecisionResponse,
    summary="Record an operator decision for one advisory artifact",
)
async def review_agent_artifact(
    decision: AgentReviewDecisionRequest,
    artifact_id: UUID = Path(..., description="Agent artifact to review."),
    tenant_id: Optional[UUID] = Query(
        default=None,
        description="Tenant to inspect. Sysadmin only; regular operators use their auth tenant.",
    ),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> AgentReviewDecisionResponse:
    """Persist the human operator decision for an advisory artifact."""

    resolved_tenant = _resolve_operator_tenant_id(
        db,
        current_user=current_user,
        requested_tenant_id=tenant_id,
    )
    try:
        response = upsert_agent_artifact_review(
            db,
            tenant_id=str(resolved_tenant),
            artifact_id=str(artifact_id),
            status=decision.status,
            reviewed_by=str(current_user.id),
            review_reason=decision.review_reason,
            operator_notes=decision.operator_notes if decision.operator_notes is not None else decision.notes,
            decision_metadata=decision.decision_metadata,
        )
        db.commit()
        return response
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/items/{artifact_id}/timeline",
    response_model=AgentArtifactTimelineResponse,
    summary="Fetch one advisory artifact and its run-ledger receipt timeline",
)
async def get_agent_artifact_timeline(
    artifact_id: UUID = Path(..., description="Agent artifact to inspect."),
    tenant_id: Optional[UUID] = Query(
        default=None,
        description="Tenant to inspect. Sysadmin only; regular operators use their auth tenant.",
    ),
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> AgentArtifactTimelineResponse:
    """Return the artifact detail view plus receipt-chain proof."""

    resolved_tenant = _resolve_operator_tenant_id(
        db,
        current_user=current_user,
        requested_tenant_id=tenant_id,
    )
    try:
        return fetch_agent_artifact_timeline(
            db,
            tenant_id=str(resolved_tenant),
            artifact_id=str(artifact_id),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_operator_tenant_id(
    db: Session,
    *,
    current_user: UserModel,
    requested_tenant_id: Optional[UUID],
) -> UUID:
    auth_tenant = TenantContext.get_tenant_context(db)

    if requested_tenant_id is None:
        if auth_tenant is None:
            raise HTTPException(
                status_code=403,
                detail="E_NO_TENANT_CONTEXT: agent review endpoint requires tenant context",
            )
        return auth_tenant

    if not current_user.is_sysadmin and auth_tenant != requested_tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    if current_user.is_sysadmin:
        set_tenant_guc(db, str(requested_tenant_id))
        # #2461: the sysadmin cross-tenant override changes the effective
        # tenant for this request — re-seed the RLS contextvar so the
        # Engine begin-hook re-applies the REQUESTED tenant on any later
        # transaction (get_current_user seeded the sysadmin's own tenant).
        set_rls_tenant_id(str(requested_tenant_id))
    return requested_tenant_id
