"""
Optimization Router — Revenue intelligence API.

Endpoints for pricing recommendations, revenue opportunities,
win-back campaigns, customer health, and expansion metrics.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional

from optimization_engine import (
    optimization_engine, OpportunityType, OpportunityStatus, CampaignStatus, HealthGrade,
)

router = APIRouter(prefix="/v1/billing/optimization", tags=["Optimization"])


class UpdateOppStatusRequest(BaseModel):
    status: OpportunityStatus


@router.get("/pricing")
async def pricing_recommendations():
    """Dynamic pricing recommendations."""
    recs = optimization_engine.get_recommendations()
    return {"recommendations": [r.model_dump() for r in recs], "total": len(recs)}


@router.get("/opportunities")
async def list_opportunities(
    opp_type: Optional[OpportunityType] = Query(None),
    status: Optional[OpportunityStatus] = Query(None),
):
    """Revenue opportunities pipeline."""
    opps = optimization_engine.list_opportunities(opp_type=opp_type, status=status)
    return {"opportunities": [o.model_dump() for o in opps], "total": len(opps)}


@router.put("/opportunities/{opp_id}/status")
async def update_opportunity(opp_id: str, request: UpdateOppStatusRequest):
    """Update opportunity status."""
    try:
        opp = optimization_engine.update_opportunity(opp_id, request.status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"opportunity": opp.model_dump()}


@router.get("/campaigns")
async def list_campaigns(status: Optional[CampaignStatus] = Query(None)):
    """Win-back campaigns."""
    campaigns = optimization_engine.list_campaigns(status=status)
    return {"campaigns": [c.model_dump() for c in campaigns], "total": len(campaigns)}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str = Path(...)):
    """Campaign detail."""
    campaign = optimization_engine.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")
    return {"campaign": campaign.model_dump()}


@router.get("/health")
async def health_scores(min_grade: Optional[HealthGrade] = Query(None)):
    """Customer health scores."""
    scores = optimization_engine.get_health_scores(min_grade=min_grade)
    return {"scores": [s.model_dump() for s in scores], "total": len(scores)}


@router.get("/expansion")
async def expansion_metrics():
    """Expansion revenue metrics."""
    metrics = optimization_engine.get_expansion_metrics()
    return {"metrics": [m.model_dump() for m in metrics], "total": len(metrics)}


@router.get("/pipeline")
async def pipeline_summary():
    """Revenue pipeline summary."""
    return optimization_engine.get_pipeline_summary()
