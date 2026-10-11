from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from shared.auth import reconcile_tenant_scope, require_api_key
from shared.metrics_auth import require_metrics_key

# Add shared utilities (portable path resolution)
from shared.middleware import get_current_tenant_id

from ...fsma_metrics import (
    get_health_status,
    get_metrics_text,
    record_gap_detection,
    record_orphan_detection,
    update_data_quality_score,
)
from ...fsma_utils import analyze_kde_completeness, find_gaps, find_orphaned_lots
from ...neo4j_utils import Neo4jClient

router = APIRouter(tags=["Metrics"])
logger = structlog.get_logger("fsma-metrics")


# ============================================================================
# HEALTH & METRICS
# ============================================================================


@router.get("/health")
def fsma_health():
    """FSMA module health check with metrics summary."""
    return get_health_status()


@router.get("/metrics", dependencies=[Depends(require_metrics_key)])
def fsma_metrics_endpoint():
    """
    Prometheus metrics endpoint for FSMA 204 compliance monitoring.

    Exposes metrics including:
    - Trace query latency (fsma_trace_query_seconds)
    - Recall response timing (fsma_recall_sla_seconds)
    - Data quality gauges (fsma_gaps_total, fsma_orphans_total)
    - KDE completeness (fsma_kde_completeness_rate)

    Returns: Prometheus text format metrics.
    """
    return PlainTextResponse(content=get_metrics_text(), media_type="text/plain; charset=utf-8")


@router.get("/metrics/quality")
async def get_data_quality_metrics(
    confidence_threshold: float = Query(0.85, ge=0.0, le=1.0, description="Low confidence threshold"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Get data quality drift metrics across all event types.

    Monitors KDE completeness rates to detect data quality degradation:
    - Missing date rates
    - Missing lot linkage rates
    - Low confidence extraction rates
    - Average confidence scores

    Use this to identify:
    - Supplier format changes requiring extractor updates
    - ML model drift requiring retraining
    - Data entry quality issues requiring training
    """
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)

    try:
        # #2833: `async with` closes the driver — and its connection
        # pool — on every exit path. The explicit close that used to
        # sit inside the try was skipped whenever the query or the
        # serialization below it raised, leaking a driver (and pool)
        # per failed request behind the generic 500 handler.
        async with Neo4jClient(database=db_name) as client:
            report = await analyze_kde_completeness(client, str(tenant_id), confidence_threshold)

        return {
            "total_events": report.total_events,
            "overall_completeness_rate": report.overall_completeness_rate,
            "trend_direction": report.trend_direction,
            "metrics_by_type": [
                {
                    "event_type": m.event_type,
                    "total_events": m.total_events,
                    "missing_date_count": m.missing_date_count,
                    "missing_date_rate": m.missing_date_rate,
                    "missing_lot_count": m.missing_lot_count,
                    "missing_lot_rate": m.missing_lot_rate,
                    "low_confidence_count": m.low_confidence_count,
                    "low_confidence_rate": m.low_confidence_rate,
                    "average_confidence": m.average_confidence,
                }
                for m in report.metrics_by_type
            ],
            "query_time_ms": report.query_time_ms,
        }
    except Exception as e:
        logger.exception("quality_metrics_error", error=str(e))
        logger.exception("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dashboard")
async def fsma_dashboard(
    request: Request,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    FSMA compliance dashboard with aggregated health metrics.

    Returns a JSON summary of all FSMA compliance metrics suitable
    for dashboard display.
    """
    # Fail closed when the middleware-resolved tenant differs from the
    # authenticated API-key tenant (same reconcile as the gaps routes).
    scoped_tenant_id = reconcile_tenant_scope(api_key, tenant_id, request_path=request.url.path)
    scoped_uuid = uuid.UUID(scoped_tenant_id)
    db_name = Neo4jClient.get_tenant_database_name(scoped_uuid)

    try:
        # #2833: `async with` closes the driver — and its connection
        # pool — on every exit path. The explicit close that used to
        # sit inside the try was skipped whenever the query or the
        # serialization below it raised, leaking a driver (and pool)
        # per failed request behind the generic 500 handler.
        async with Neo4jClient(database=db_name) as client:
            # Get gap metrics
            gaps = await find_gaps(client, scoped_tenant_id)

            # Get orphan metrics
            orphans = await find_orphaned_lots(client, scoped_tenant_id)

            # Get KDE completeness
            completeness = await analyze_kde_completeness(client, scoped_tenant_id)

        # Update Prometheus gauges
        record_gap_detection(len(gaps), "all")
        record_orphan_detection(len(orphans))
        if completeness:
            update_data_quality_score(completeness.overall_completeness_rate)

        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "compliance": {
                "module": "FSMA-204",
                "recall_sla_target": "24_hours",
            },
            "data_quality": {
                "gaps_total": len(gaps),
                "orphans_total": len(orphans),
                "kde_completeness_rate": (completeness.overall_completeness_rate if completeness else 0.0),
            },
            "alerts": [
                (
                    {
                        "level": "warning",
                        "message": f"{len(gaps)} events have missing KDEs",
                    }
                    if gaps
                    else None
                ),
                (
                    {
                        "level": "warning",
                        "message": f"{len(orphans)} orphaned lots detected",
                    }
                    if orphans
                    else None
                ),
            ],
        }
    except Exception as e:
        logger.exception("dashboard_error", error=str(e))
        return {
            "status": "degraded",
            "error": str(e),
        }
