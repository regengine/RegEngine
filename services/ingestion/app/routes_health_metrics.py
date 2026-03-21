"""Health and metrics routes — extracted from routes.py god file.

Part of the routes.py decomposition effort (Finding #8, Ingestion Debug Audit 2026-03-19).
"""

from __future__ import annotations

import logging
import os as _os
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

try:
    from confluent_kafka.admin import AdminClient
except ModuleNotFoundError:  # pragma: no cover
    AdminClient = None  # type: ignore[assignment]

from .config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health-metrics"])


@router.get("/health")
def health() -> dict[str, str]:
    """Health-check endpoint."""
    settings = get_settings()
    kafka_status = "unavailable"
    try:
        if AdminClient is None:
            raise RuntimeError("confluent_kafka is not installed")
        admin_client = AdminClient(
            {
                "bootstrap.servers": settings.kafka_bootstrap_servers,
                "client.id": "ingestion-healthcheck",
            }
        )
        admin_client.list_topics(timeout=5)
        kafka_status = "available"
    except Exception as exc:
        logger.warning("ingestion_health_kafka_unavailable: %s", str(exc))
    return {
        "status": "healthy",
        "service": "ingestion-service",
        "kafka": kafka_status,
    }


@router.get("/metrics", include_in_schema=False)
def metrics() -> PlainTextResponse:
    """Expose Prometheus metrics (disabled in production)."""
    _prod = (
        _os.getenv("ENV", "").lower() == "production"
        or "pooler.supabase.com" in _os.getenv("DATABASE_URL", "")
    )
    if _prod:
        raise HTTPException(status_code=403, detail="Metrics disabled in production")
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
