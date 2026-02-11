"""
Analytics Router — Revenue metrics and forecasting API.

Endpoints for MRR/ARR tracking, cohort analysis, conversion funnels,
credit program ROI, and revenue projections.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from analytics_engine import AnalyticsEngine
from credit_engine import CreditEngine
from dependencies import get_analytics_engine, get_credit_engine

# Import subscription store from the subscriptions router
from routers.subscriptions import _subscriptions

router = APIRouter(prefix="/v1/billing/analytics", tags=["Analytics"])


@router.get("/overview")
async def analytics_overview(engine: AnalyticsEngine = Depends(get_analytics_engine)):
    """Full analytics dashboard overview — MRR, key metrics, health score."""
    return engine.get_overview(_subscriptions)


@router.get("/mrr-history")
async def mrr_history(
    months: int = Query(12, ge=3, le=24),
    engine: AnalyticsEngine = Depends(get_analytics_engine),
):
    """Monthly MRR time series for charting."""
    return {
        "history": engine.get_mrr_history(months),
        "months_requested": months,
    }


@router.get("/cohorts")
async def cohort_analysis(engine: AnalyticsEngine = Depends(get_analytics_engine)):
    """Signup cohort retention matrix."""
    return engine.get_cohort_data()


@router.get("/funnel")
async def conversion_funnel(engine: AnalyticsEngine = Depends(get_analytics_engine)):
    """Trial → Active → Churned conversion funnel."""
    return engine.get_conversion_funnel(_subscriptions)


@router.get("/credits")
async def credit_program_roi(
    analytics: AnalyticsEngine = Depends(get_analytics_engine),
    credits: CreditEngine = Depends(get_credit_engine),
):
    """Credit program performance: redemptions, ROI, and abuse risk."""
    return analytics.get_credit_program_roi(credits)


@router.get("/forecasts")
async def revenue_forecasts(
    months: int = Query(6, ge=1, le=12),
    engine: AnalyticsEngine = Depends(get_analytics_engine),
):
    """Revenue projections based on MRR growth trend."""
    return engine.get_revenue_forecast(months)
