"""Review queue routes for curator workflow.

This module provides endpoints for the human-in-the-loop review workflow,
allowing curators to approve or reject low-confidence NLP extractions.

These endpoints delegate to the hallucination tracker which provides
database-backed persistence of review items. The v1/admin/review/flagged-extractions
endpoints in routes.py provide the full implementation -- these endpoints serve
as a convenience alias for the frontend review UI.

Security hardening (issues #1360 / #1361 / #1367 / #1369 / #1389):
  - approve/reject call ``tracker.resolve_hallucination`` with the
    caller's authenticated ``tenant_id`` so cross-tenant decisions
    by UUID are blocked at the tracker layer (404).
  - the tracker enforces idempotency and rejects a second decision
    on a non-PENDING item with ``ValueError`` which we map to 409.
  - list/approve/reject require a tenant-scoped API key; a key with
    ``tenant_id is None`` cannot list or resolve review items.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from datetime import datetime, timezone

from shared.auth import APIKey, require_api_key
from .text_sanitize import sanitize_source_text_for_response

router = APIRouter(prefix="/v1/admin", tags=["review"])


def _require_tenant_scoped_key(api_key: APIKey) -> str:
    """Ensure the API key is bound to a tenant; return the tenant_id.

    Legacy keys with ``tenant_id is None`` must not be able to list or
    resolve review items -- without a tenant, the tracker queries fall
    back to "all tenants" (issue #1389). Raise 403 rather than leak.
    """
    if not api_key.tenant_id:
        raise HTTPException(
            status_code=403,
            detail=(
                "This API key is not bound to a tenant. Create a "
                "tenant-scoped key before accessing the review queue."
            ),
        )
    return api_key.tenant_id


class ReviewItem(BaseModel):
    """A pending review item for curator validation."""
    review_id: str
    doc_hash: str
    confidence_score: float
    source_text: str
    extracted_data: dict
    created_at: datetime
    status: str = "PENDING"


class ReviewItemsResponse(BaseModel):
    """Response containing list of review items."""
    items: List[ReviewItem]
    total: int
    offset: int
    limit: int


class ReviewActionResponse(BaseModel):
    """Response for review item action (approve/reject)."""
    status: str
    review_id: str
    updated: bool


def _get_tracker():
    """Get the hallucination tracker for review queue operations."""
    from .metrics import get_hallucination_tracker
    return get_hallucination_tracker()


@router.get("/review/hallucinations", response_model=ReviewItemsResponse)
async def get_review_queue(
    status_filter: Optional[str] = Query("PENDING", description="Filter by status"),
    limit: int = Query(default=50, ge=1, le=1000, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    api_key: APIKey = Depends(require_api_key),
) -> ReviewItemsResponse:
    """Get items pending curator review.

    Returns low-confidence NLP extractions that require human validation.
    Items can be approved or rejected through the curator interface.

    Powered by the hallucination tracker database backend.

    source_text is HTML-escaped on read as defense-in-depth against
    stored XSS via document content (#1390).
    """
    tenant_id = _require_tenant_scoped_key(api_key)
    tracker = _get_tracker()
    try:
        result = tracker.list_hallucinations(
            status=status_filter,
            tenant_id=tenant_id,
            limit=limit,
            cursor=None,
        )

        items = [
            ReviewItem(
                review_id=item["review_id"],
                doc_hash=item.get("doc_hash", ""),
                confidence_score=item.get("confidence_score", 0.0),
                source_text=sanitize_source_text_for_response(
                    item.get("text_raw", "")
                ),
                extracted_data=item.get("extraction", {}),
                created_at=item.get("created_at", datetime.now(timezone.utc)),
                status=item.get("status", "PENDING"),
            )
            for item in result.get("items", [])
        ]

        return ReviewItemsResponse(
            items=items,
            total=result.get("total", len(items)),
            offset=offset,
            limit=limit,
        )
    except HTTPException:
        raise
    except (RuntimeError, OSError, ValueError, KeyError, AttributeError) as e:
        # If tracker is not initialized or DB is unavailable, return empty
        import structlog
        logger = structlog.get_logger("review")
        logger.warning("review_queue_query_failed", error=str(e))
        return ReviewItemsResponse(
            items=[],
            total=0,
            offset=offset,
            limit=limit,
        )


def _extract_actor_identity(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Pull actor identity from request state if the auth dependency set it.

    Admin routes that run under JWT auth expose ``request.state.user`` /
    ``request.state.user_id`` via the auth middleware. For API-key-only
    routes this returns (None, None) and we record the API key alone.
    """
    state = getattr(request, "state", None)
    user_id = getattr(state, "user_id", None) if state is not None else None
    user_email = getattr(state, "user_email", None) if state is not None else None
    return user_id, user_email


@router.post("/review/{review_id}/approve", response_model=ReviewActionResponse)
async def approve_review_item(
    review_id: str,
    request: Request,
    api_key: APIKey = Depends(require_api_key),
):
    """Approve a review item, marking the extraction as validated.

    Tenant-scoped at the tracker layer (#1360). Idempotent: a second
    approve/reject call raises 409 Conflict (#1361). Writes a
    tamper-evident entry to the audit_logs hash chain (#1369).
    """
    tenant_id = _require_tenant_scoped_key(api_key)
    tracker = _get_tracker()
    actor_user_id, actor_email = _extract_actor_identity(request)
    try:
        updated = tracker.resolve_hallucination(
            review_id,
            new_status="APPROVED",
            reviewer_id=api_key.key_id,
            notes=f"Approved via curator review API by key {api_key.key_id}",
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"status": "approved", "review_id": review_id, "updated": updated}
    except LookupError:
        raise HTTPException(status_code=404, detail="Review item not found")
    except ValueError as e:
        # Idempotency conflict (#1361) -- item already resolved.
        msg = str(e)
        if "already" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)


@router.post("/review/{review_id}/reject", response_model=ReviewActionResponse)
async def reject_review_item(
    review_id: str,
    request: Request,
    api_key: APIKey = Depends(require_api_key),
):
    """Reject a review item, marking the extraction as invalid.

    Tenant-scoped at the tracker layer (#1360). Idempotent: a second
    approve/reject call raises 409 Conflict (#1361). Writes a
    tamper-evident entry to the audit_logs hash chain (#1369).
    """
    tenant_id = _require_tenant_scoped_key(api_key)
    tracker = _get_tracker()
    actor_user_id, actor_email = _extract_actor_identity(request)
    try:
        updated = tracker.resolve_hallucination(
            review_id,
            new_status="REJECTED",
            reviewer_id=api_key.key_id,
            notes=f"Rejected via curator review API by key {api_key.key_id}",
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )
        return {"status": "rejected", "review_id": review_id, "updated": updated}
    except LookupError:
        raise HTTPException(status_code=404, detail="Review item not found")
    except ValueError as e:
        msg = str(e)
        if "already" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
