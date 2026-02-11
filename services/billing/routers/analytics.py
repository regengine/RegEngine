"""
Analytics Router — Revenue metrics and forecasting API.

Endpoints for MRR/ARR tracking, cohort analysis, conversion funnels,
credit program ROI, and revenue projections.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from analytics_engine import analytics_engine
from credit_engine import credit_engine

# Import subscription store from the subscriptions router
from routers.subscriptions import _subscriptions

router = APIRouter(prefix="/v1/billing/analytics", tags=["Analytics"])


@router.get("/overview")
async def analytics_overview():
    """Full analytics dashboard overview — MRR, key metrics, health score."""
    return analytics_engine.get_overview(_subscriptions)


@router.get("/mrr-history")
async def mrr_history(months: int = Query(12, ge=3, le=24)):
    """Monthly MRR time series for charting."""
    return {
        "history": analytics_engine.get_mrr_history(months),
        "months_requested": months,
    }


@router.get("/cohorts")
async def cohort_analysis():
    """Signup cohort retention matrix."""
    return analytics_engine.get_cohort_data()


@router.get("/funnel")
async def conversion_funnel():
    """Trial → Active → Churned conversion funnel."""
    return analytics_engine.get_conversion_funnel(_subscriptions)


@router.get("/credits")
async def credit_program_roi():
    """Credit program performance: redemptions, ROI, and abuse risk."""
    return analytics_engine.get_credit_program_roi(credit_engine)


@router.get("/forecasts")
async def revenue_forecasts(months: int = Query(6, ge=1, le=12)):
    """Revenue projections based on MRR growth trend."""
    return analytics_engine.get_revenue_forecast(months)
