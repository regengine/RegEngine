"""Health and metrics routes — extracted from routes.py god file.

Part of the routes.py decomposition effort (Finding #8, Ingestion Debug Audit 2026-03-19).
"""

from __future__ import annotations

import logging
import os as _os

from fastapi import APIRouter, Depends, HTTPException
from shared.metrics_auth import require_metrics_key
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from shared.kafka_consumer_base import kafka_health_check

from .config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health-metrics"])


@router.get("/health")
def health() -> dict[str, str]:
    """Health-check endpoint.

    Returns ``"healthy"`` when all dependencies are reachable, or
    ``"degraded"`` when optional dependencies (e.g. Kafka) are
    unavailable.  Monitoring tools can alert on *degraded* without
    treating the service as fully down.
    """
    settings = get_settings()
    kafka_result = kafka_health_check(
        bootstrap_servers=settings.kafka_bootstrap_servers, timeout=3.0,
    )
    kafka_status = kafka_result["status"]

    if kafka_status != "available":
        logger.warning(
            "ingestion_health_kafka_unavailable: %s",
            kafka_result.get("error", "unknown"),
        )

    overall_status = "healthy" if kafka_status == "available" else "degraded"
    return {
        "status": overall_status,
        "service": "ingestion-service",
        "kafka": kafka_status,
    }


@router.get("/metrics", include_in_schema=False, dependencies=[Depends(require_metrics_key)])
def metrics() -> PlainTextResponse:
    """Expose Prometheus metrics (disabled in production)."""
    _prod = (
        _os.getenv("ENV", "").lower() == "production"
        or "pooler.supabase.com" in _os.getenv("DATABASE_URL", "")
    )
    if _prod:
        raise HTTPException(status_code=403, detail="Metrics disabled in production")
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
