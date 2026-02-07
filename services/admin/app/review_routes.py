"""Review queue routes for curator workflow.

This module provides endpoints for the human-in-the-loop review workflow,
allowing curators to approve or reject low-confidence NLP extractions.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from datetime import datetime

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
    page: int
    limit: int


@router.get("/review/hallucinations", response_model=ReviewItemsResponse)
async def get_review_queue(
    status_filter: Optional[str] = Query("PENDING", description="Filter by status"),
    limit: int = Query(50, le=100, description="Max items to return"),
    page: int = Query(1, ge=1, description="Page number"),
    api_key: APIKey = Depends(require_api_key),
) -> ReviewItemsResponse:
    """Get items pending curator review.
    
    Returns low-confidence NLP extractions that require human validation.
    Items can be approved or rejected through the curator interface.
    
    **Note**: This is currently a stub endpoint. The full review workflow
    will be implemented as part of the NLP integration phase.
    """
    # TODO: Implement actual database query for review items
    # For now, return empty list to prevent frontend errors
    return ReviewItemsResponse(
        items=[],
        total=0,
        page=page,
        limit=limit
    )


@router.post("/review/{review_id}/approve")
async def approve_review_item(
    review_id: str,
    api_key: APIKey = Depends(require_api_key),
):
    """Approve a review item, marking the extraction as validated.
    
    **Note**: Stub endpoint - implementation pending.
    """
    # TODO: Update review item status to APPROVED
    return {"status": "approved", "review_id": review_id}


@router.post("/review/{review_id}/reject")
async def reject_review_item(
    review_id: str,
    api_key: APIKey = Depends(require_api_key),
):
    """Reject a review item, marking the extraction as invalid.
    
    **Note**: Stub endpoint - implementation pending.
    """
    # TODO: Update review item status to REJECTED
    return {"status": "rejected", "review_id": review_id}
