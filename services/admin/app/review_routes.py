"""Review queue routes for curator workflow.

This module provides endpoints for the human-in-the-loop review workflow,
allowing curators to approve or reject low-confidence NLP extractions.

These endpoints delegate to the hallucination tracker which provides
database-backed persistence of review items. The v1/admin/review/flagged-extractions
endpoints in routes.py provide the full implementation — these endpoints serve
as a convenience alias for the frontend review UI.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime, timezone

from shared.auth import APIKey, require_api_key

router = APIRouter(prefix="/v1/admin", tags=["review"])


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
    """
    tracker = _get_tracker()
    try:
        result = tracker.list_hallucinations(
            status=status_filter,
            tenant_id=api_key.tenant_id,
            limit=limit,
            offset=offset,
            cursor=None,
        )

        items = [
            ReviewItem(
                review_id=item["review_id"],
                doc_hash=item.get("doc_hash", ""),
                confidence_score=item.get("confidence_score", 0.0),
                source_text=item.get("text_raw", ""),
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


@router.post("/review/{review_id}/approve")
async def approve_review_item(
    review_id: str,
    api_key: APIKey = Depends(require_api_key),
):
    """Approve a review item, marking the extraction as validated."""
    tracker = _get_tracker()
    try:
        updated = tracker.resolve_hallucination(
            review_id,
            new_status="APPROVED",
            reviewer_id=api_key.key_id,
            notes=f"Approved via curator review API by key {api_key.key_id}",
        )
        return {"status": "approved", "review_id": review_id, "updated": updated}
    except LookupError:
        raise HTTPException(status_code=404, detail="Review item not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/review/{review_id}/reject")
async def reject_review_item(
    review_id: str,
    api_key: APIKey = Depends(require_api_key),
):
    """Reject a review item, marking the extraction as invalid."""
    tracker = _get_tracker()
    try:
        updated = tracker.resolve_hallucination(
            review_id,
            new_status="REJECTED",
            reviewer_id=api_key.key_id,
            notes=f"Rejected via curator review API by key {api_key.key_id}",
        )
        return {"status": "rejected", "review_id": review_id, "updated": updated}
    except LookupError:
        raise HTTPException(status_code=404, detail="Review item not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
