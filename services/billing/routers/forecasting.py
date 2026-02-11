"""
Forecasting Router — Advanced analytics & prediction API.

Endpoints for MRR forecasting, churn prediction, CLV,
cohort analysis, and revenue anomaly detection.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from forecasting_engine import forecasting_engine, ChurnRisk

router = APIRouter(prefix="/v1/billing/forecasting", tags=["Forecasting"])


@router.get("/mrr/history")
async def mrr_history():
    """Historical MRR data."""
    history = forecasting_engine.get_mrr_history()
    return {"history": history, "months": len(history)}


@router.get("/mrr/forecast")
async def mrr_forecast(months: int = Query(6, ge=1, le=24)):
    """MRR forecast with confidence intervals."""
    forecasts = forecasting_engine.forecast_mrr(months)
    return {"forecasts": [f.model_dump() for f in forecasts], "months_ahead": months}


@router.get("/churn/scores")
async def churn_scores(risk: Optional[ChurnRisk] = Query(None)):
    """Churn prediction scores per tenant."""
    scores = forecasting_engine.get_churn_scores(risk=risk)
    return {"scores": [s.model_dump() for s in scores], "total": len(scores)}


@router.get("/churn/overview")
async def churn_overview():
    """Churn risk overview."""
    return forecasting_engine.get_churn_overview()


@router.get("/clv")
async def clv_estimates(sort_by: str = Query("lifetime_value")):
    """Customer lifetime value estimates."""
    estimates = forecasting_engine.get_clv_estimates(sort_by=sort_by)
    return {"estimates": [e.model_dump() for e in estimates], "total": len(estimates)}


@router.get("/clv/summary")
async def clv_summary():
    """CLV summary and top customers."""
    return forecasting_engine.get_clv_summary()


@router.get("/cohorts")
async def cohorts():
    """Cohort data."""
    data = forecasting_engine.get_cohorts()
    return {"cohorts": [c.model_dump() for c in data], "total": len(data)}


@router.get("/cohorts/retention")
async def retention_matrix():
    """Retention heatmap matrix."""
    return forecasting_engine.get_retention_matrix()


@router.get("/anomalies")
async def anomalies():
    """Revenue anomalies."""
    data = forecasting_engine.get_anomalies()
    return {"anomalies": [a.model_dump() for a in data], "total": len(data)}


@router.get("/summary")
async def executive_summary():
    """Executive analytics summary."""
    return forecasting_engine.get_executive_summary()
