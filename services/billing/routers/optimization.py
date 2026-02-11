"""
Optimization Router — Revenue intelligence API.

Endpoints for pricing recommendations, revenue opportunities,
win-back campaigns, customer health, and expansion metrics.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional

from optimization_engine import (
    OptimizationEngine, OpportunityType, OpportunityStatus, CampaignStatus, HealthGrade,
)
from dependencies import get_optimization_engine

router = APIRouter(prefix="/v1/billing/optimization", tags=["Optimization"])


class UpdateOppStatusRequest(BaseModel):
    status: OpportunityStatus


@router.get("/pricing")
async def pricing_recommendations(
    engine: OptimizationEngine = Depends(get_optimization_engine),
):
    """Dynamic pricing recommendations."""
    recs = engine.get_recommendations()
    return {"recommendations": [r.model_dump() for r in recs], "total": len(recs)}


@router.get("/opportunities")
async def list_opportunities(
    opp_type: Optional[OpportunityType] = Query(None),
    status: Optional[OpportunityStatus] = Query(None),
    engine: OptimizationEngine = Depends(get_optimization_engine),
):
    """Revenue opportunities pipeline."""
    opps = engine.list_opportunities(opp_type=opp_type, status=status)
    return {"opportunities": [o.model_dump() for o in opps], "total": len(opps)}


@router.put("/opportunities/{opp_id}/status")
async def update_opportunity(
    opp_id: str,
    request: UpdateOppStatusRequest,
    engine: OptimizationEngine = Depends(get_optimization_engine),
):
    """Update opportunity status."""
    try:
        opp = engine.update_opportunity(opp_id, request.status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"opportunity": opp.model_dump()}


@router.get("/campaigns")
async def list_campaigns(
    status: Optional[CampaignStatus] = Query(None),
    engine: OptimizationEngine = Depends(get_optimization_engine),
):
    """Win-back campaigns."""
    campaigns = engine.list_campaigns(status=status)
    return {"campaigns": [c.model_dump() for c in campaigns], "total": len(campaigns)}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str = Path(...),
    engine: OptimizationEngine = Depends(get_optimization_engine),
):
    """Campaign detail."""
    campaign = engine.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found")
    return {"campaign": campaign.model_dump()}


@router.get("/health")
async def health_scores(
    min_grade: Optional[HealthGrade] = Query(None),
    engine: OptimizationEngine = Depends(get_optimization_engine),
):
    """Customer health scores."""
    scores = engine.get_health_scores(min_grade=min_grade)
    return {"scores": [s.model_dump() for s in scores], "total": len(scores)}


@router.get("/expansion")
async def expansion_metrics(
    engine: OptimizationEngine = Depends(get_optimization_engine),
):
    """Expansion revenue metrics."""
    metrics = engine.get_expansion_metrics()
    return {"metrics": [m.model_dump() for m in metrics], "total": len(metrics)}


@router.get("/pipeline")
async def pipeline_summary(
    engine: OptimizationEngine = Depends(get_optimization_engine),
):
    """Revenue pipeline summary."""
    return engine.get_pipeline_summary()
