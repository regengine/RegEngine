"""Health-check route — extracted from routes.py god file.

Part of the routes.py decomposition effort (Finding #8, Ingestion Debug Audit 2026-03-19).

NOTE: ``/metrics`` exposition is installed via
``shared.observability.fastapi_metrics.install_metrics`` in ``main.py`` —
don't re-register it here. The shared installer uses
``prometheus-fastapi-instrumentator`` which adds proper RED metrics and the
``X-Metrics-Key`` auth guard; the previous hand-rolled endpoint returned 403
in production, which silenced scraping and broke SLO dashboards (#1325).
"""

from __future__ import annotations

import logging
import os as _os

from fastapi import APIRouter

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
    # Kafka is optional — only check if explicitly configured
    kafka_servers = _os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")
    if kafka_servers and kafka_servers not in ("redpanda:9092", "localhost:9092"):
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
    else:
        kafka_status = "not_configured"
        overall_status = "healthy"

    return {
        "status": overall_status,
        "service": "regengine",
        "kafka": kafka_status,
    }
