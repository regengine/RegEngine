"""
Forecasting Router — Advanced analytics & prediction API.

Endpoints for MRR forecasting, churn prediction, CLV,
cohort analysis, and revenue anomaly detection.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from forecasting_engine import ForecastingEngine, ChurnRisk
from dependencies import get_forecasting_engine

router = APIRouter(prefix="/v1/billing/forecasting", tags=["Forecasting"])


@router.get("/mrr/history")
async def mrr_history(engine: ForecastingEngine = Depends(get_forecasting_engine)):
    """Historical MRR data."""
    history = engine.get_mrr_history()
    return {"history": history, "months": len(history)}


@router.get("/mrr/forecast")
async def mrr_forecast(
    months: int = Query(6, ge=1, le=24),
    engine: ForecastingEngine = Depends(get_forecasting_engine),
):
    """MRR forecast with confidence intervals."""
    forecasts = engine.forecast_mrr(months)
    return {"forecasts": [f.model_dump() for f in forecasts], "months_ahead": months}


@router.get("/churn/scores")
async def churn_scores(
    risk: Optional[ChurnRisk] = Query(None),
    engine: ForecastingEngine = Depends(get_forecasting_engine),
):
    """Churn prediction scores per tenant."""
    scores = engine.get_churn_scores(risk=risk)
    return {"scores": [s.model_dump() for s in scores], "total": len(scores)}


@router.get("/churn/overview")
async def churn_overview(engine: ForecastingEngine = Depends(get_forecasting_engine)):
    """Churn risk overview."""
    return engine.get_churn_overview()


@router.get("/clv")
async def clv_estimates(
    sort_by: str = Query("lifetime_value"),
    engine: ForecastingEngine = Depends(get_forecasting_engine),
):
    """Customer lifetime value estimates."""
    estimates = engine.get_clv_estimates(sort_by=sort_by)
    return {"estimates": [e.model_dump() for e in estimates], "total": len(estimates)}


@router.get("/clv/summary")
async def clv_summary(engine: ForecastingEngine = Depends(get_forecasting_engine)):
    """CLV summary and top customers."""
    return engine.get_clv_summary()


@router.get("/cohorts")
async def cohorts(engine: ForecastingEngine = Depends(get_forecasting_engine)):
    """Cohort data."""
    data = engine.get_cohorts()
    return {"cohorts": [c.model_dump() for c in data], "total": len(data)}


@router.get("/cohorts/retention")
async def retention_matrix(engine: ForecastingEngine = Depends(get_forecasting_engine)):
    """Retention heatmap matrix."""
    return engine.get_retention_matrix()


@router.get("/anomalies")
async def anomalies(engine: ForecastingEngine = Depends(get_forecasting_engine)):
    """Revenue anomalies."""
    data = engine.get_anomalies()
    return {"anomalies": [a.model_dump() for a in data], "total": len(data)}


@router.get("/summary")
async def executive_summary(engine: ForecastingEngine = Depends(get_forecasting_engine)):
    """Executive analytics summary."""
    return engine.get_executive_summary()
