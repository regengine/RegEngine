"""Agent operator review endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
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
from shared.tenant_context import set_tenant_guc
from sqlalchemy.orm import Session

from .dependencies import get_session
from .privileged_auth import (
    PrivilegedActor,
    audit_privileged_action,
    require_review_decide,
    require_review_read,
)

router = APIRouter(prefix="/agent-reviews", tags=["agent-reviews"])


def _arm_review_tenant(db: Session, tenant_id: UUID) -> None:
    """Apply the authenticated tenant to this admin DB transaction.

    The admin credential is intentionally not given a global bypass policy on
    agent evidence.  Every list, timeline, and decision query must therefore
    bind the actor-derived tenant before touching the FORCE-RLS tables.
    """
    bind = getattr(db, "bind", None)
    dialect = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect == "postgresql":
        set_tenant_guc(db, str(tenant_id))


@router.get(
    "/items",
    response_model=AgentReviewListResponse,
    summary="List agent review items for the active tenant",
)
async def list_agent_review_items(
    request: Request,
    tenant_id: Optional[UUID] = Query(
        default=None,
        description="Optional assertion; must match the active session tenant.",
    ),
    ingestion_run_id: Optional[UUID] = None,
    review_status: Optional[ReviewStatus] = None,
    artifact_type: Optional[ArtifactType] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    actor: PrivilegedActor = Depends(require_review_read),
    db: Session = Depends(get_session),
) -> AgentReviewListResponse:
    """Return the V1 operator read model for advisory agent artifacts."""

    action = "agent_review.items.read"
    audit_privileged_action(
        request,
        action=action,
        outcome="attempted",
        actor=actor,
        selected_tenant=actor.tenant_id,
    )
    resolved_tenant = _resolve_operator_tenant_id(
        request=request,
        action=action,
        actor=actor,
        requested_tenant_id=tenant_id,
    )
    try:
        _arm_review_tenant(db, resolved_tenant)
        response = fetch_agent_review_items(
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
        audit_privileged_action(
            request,
            action=action,
            outcome="succeeded",
            actor=actor,
            target=f"{len(response.items)} items",
            selected_tenant=str(resolved_tenant),
        )
        return response
    except ValueError as exc:
        audit_privileged_action(
            request,
            action=action,
            outcome="denied",
            actor=actor,
            selected_tenant=str(resolved_tenant),
            reason="invalid_review_query",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        audit_privileged_action(
            request,
            action=action,
            outcome="failed",
            actor=actor,
            selected_tenant=str(resolved_tenant),
            reason="review_query_failed",
        )
        raise


@router.post(
    "/items/{artifact_id}/review",
    response_model=AgentReviewDecisionResponse,
    summary="Record an operator decision for one advisory artifact",
)
async def review_agent_artifact(
    request: Request,
    decision: AgentReviewDecisionRequest,
    artifact_id: UUID = Path(..., description="Agent artifact to review."),
    tenant_id: Optional[UUID] = Query(
        default=None,
        description="Optional assertion; must match the active session tenant.",
    ),
    actor: PrivilegedActor = Depends(require_review_decide),
    db: Session = Depends(get_session),
) -> AgentReviewDecisionResponse:
    """Persist the human operator decision for an advisory artifact."""

    action = "agent_review.decision.write"
    target = str(artifact_id)
    audit_privileged_action(
        request,
        action=action,
        outcome="attempted",
        actor=actor,
        target=target,
        selected_tenant=actor.tenant_id,
    )
    resolved_tenant = _resolve_operator_tenant_id(
        request=request,
        action=action,
        actor=actor,
        requested_tenant_id=tenant_id,
        target=target,
    )
    try:
        _arm_review_tenant(db, resolved_tenant)
        response = upsert_agent_artifact_review(
            db,
            tenant_id=str(resolved_tenant),
            artifact_id=str(artifact_id),
            status=decision.status,
            reviewed_by=actor.actor_id,
            review_reason=decision.review_reason,
            operator_notes=decision.operator_notes if decision.operator_notes is not None else decision.notes,
            decision_metadata=decision.decision_metadata,
        )
        db.commit()
        audit_privileged_action(
            request,
            action=action,
            outcome="succeeded",
            actor=actor,
            target=target,
            selected_tenant=str(resolved_tenant),
            reason=f"decision:{decision.status}",
        )
        return response
    except LookupError as exc:
        db.rollback()
        audit_privileged_action(
            request,
            action=action,
            outcome="denied",
            actor=actor,
            target=target,
            selected_tenant=str(resolved_tenant),
            reason="artifact_not_found",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        audit_privileged_action(
            request,
            action=action,
            outcome="denied",
            actor=actor,
            target=target,
            selected_tenant=str(resolved_tenant),
            reason="invalid_review_decision",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        audit_privileged_action(
            request,
            action=action,
            outcome="failed",
            actor=actor,
            target=target,
            selected_tenant=str(resolved_tenant),
            reason="review_decision_failed",
        )
        raise


@router.get(
    "/items/{artifact_id}/timeline",
    response_model=AgentArtifactTimelineResponse,
    summary="Fetch one advisory artifact and its run-ledger receipt timeline",
)
async def get_agent_artifact_timeline(
    request: Request,
    artifact_id: UUID = Path(..., description="Agent artifact to inspect."),
    tenant_id: Optional[UUID] = Query(
        default=None,
        description="Optional assertion; must match the active session tenant.",
    ),
    actor: PrivilegedActor = Depends(require_review_read),
    db: Session = Depends(get_session),
) -> AgentArtifactTimelineResponse:
    """Return the artifact detail view plus receipt-chain proof."""

    action = "agent_review.timeline.read"
    target = str(artifact_id)
    audit_privileged_action(
        request,
        action=action,
        outcome="attempted",
        actor=actor,
        target=target,
        selected_tenant=actor.tenant_id,
    )
    resolved_tenant = _resolve_operator_tenant_id(
        request=request,
        action=action,
        actor=actor,
        requested_tenant_id=tenant_id,
        target=target,
    )
    try:
        _arm_review_tenant(db, resolved_tenant)
        response = fetch_agent_artifact_timeline(
            db,
            tenant_id=str(resolved_tenant),
            artifact_id=str(artifact_id),
        )
        audit_privileged_action(
            request,
            action=action,
            outcome="succeeded",
            actor=actor,
            target=target,
            selected_tenant=str(resolved_tenant),
        )
        return response
    except LookupError as exc:
        audit_privileged_action(
            request,
            action=action,
            outcome="denied",
            actor=actor,
            target=target,
            selected_tenant=str(resolved_tenant),
            reason="artifact_not_found",
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        audit_privileged_action(
            request,
            action=action,
            outcome="denied",
            actor=actor,
            target=target,
            selected_tenant=str(resolved_tenant),
            reason="invalid_timeline_query",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        audit_privileged_action(
            request,
            action=action,
            outcome="failed",
            actor=actor,
            target=target,
            selected_tenant=str(resolved_tenant),
            reason="timeline_query_failed",
        )
        raise


def _resolve_operator_tenant_id(
    *,
    request: Request,
    action: str,
    actor: PrivilegedActor,
    requested_tenant_id: Optional[UUID],
    target: str | None = None,
) -> UUID:
    try:
        auth_tenant = UUID(str(actor.tenant_id))
    except (TypeError, ValueError, AttributeError) as exc:
        audit_privileged_action(
            request,
            action=action,
            outcome="denied",
            actor=actor,
            target=target,
            reason="missing_tenant_context",
        )
        raise HTTPException(
            status_code=403,
            detail="E_NO_TENANT_CONTEXT: agent review endpoint requires tenant context",
        ) from exc

    if requested_tenant_id is not None and auth_tenant != requested_tenant_id:
        audit_privileged_action(
            request,
            action=action,
            outcome="denied",
            actor=actor,
            target=target,
            selected_tenant=str(auth_tenant),
            reason="tenant_assertion_mismatch",
        )
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    return auth_tenant
