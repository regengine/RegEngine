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


# #2856: this is now the SOLE owner of ``GET /health``. Three handlers used to
# claim that path — this one, ``admin_deep_health`` in
# services/admin/app/routes.py, and a root liveness probe in server/main.py.
# Starlette resolves first-match while FastAPI's OpenAPI ``paths`` dict is
# last-write-wins, so the monolith served this handler and documented another.
#
# This handler kept the path (rather than the root one) because
# ``services/ingestion/main.py`` has no ``/health`` of its own: the Inflow Lab
# contract workflow boots that entrypoint and gates on ``GET /health`` both as
# its readiness wait and as the source of ``inflow_contract_version``
# (.github/workflows/inflow-contract-ci.yml). The other two moved instead —
# root liveness to ``/health/live``, the admin dependency probe to
# ``/health/deep``.
@router.get("/health")
def health() -> dict[str, object]:
    """Liveness / ingestion-posture endpoint.

    Reports process liveness and optional Kafka posture only. A healthy
    response does not attest PostgreSQL, Redis, or evidence availability.

    This is deliberately shallow: ``/readiness`` (server/main.py) is the
    dependency-gated probe Railway polls, and ``/health/deep`` verifies
    Postgres/Neo4j/Redis connectivity.
    """
    # Kafka is optional — only check if explicitly configured
    kafka_servers = _os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")
    if kafka_servers and kafka_servers not in ("redpanda:9092", "localhost:9092"):
        settings = get_settings()
        kafka_result = kafka_health_check(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            timeout=3.0,
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

    # F-5 / #3229: surface webhook HMAC config status so ops can alarm
    # when a closed gate (production or any strict/cloud runtime) has no
    # secret. The gate fails closed there, so ingest is fully 401 while
    # this probe would otherwise stay green.
    try:
        from .webhook_router_v2 import webhook_hmac_configured

        hmac_configured = webhook_hmac_configured()
    except Exception:  # pragma: no cover - never break /health on import error
        hmac_configured = False

    if not hmac_configured:
        try:
            from shared.env import requires_strict_auth_runtime

            if requires_strict_auth_runtime():
                overall_status = "degraded"
                logger.warning("ingestion_health_hmac_secret_missing")
        except Exception:  # pragma: no cover - never break /health on import error
            pass

    # Advertise the ingest contract version so integrators (inflow-lab's
    # test-connection probe, the Inflow Lab Contract CI) can detect
    # cross-deploy contract skew instead of failing silently on live posts.
    # Which commit is answering. Without this, a rollout that fails its
    # healthcheck and reverts under railway.toml's ON_FAILURE restart policy
    # is invisible: the deploy workflow has already gone green and every probe
    # afterwards asserts behaviour an old image satisfies perfectly. This is
    # the field deploy.yml's post-deploy check compares against github.sha.
    from shared.build_info import current_build_info

    from .webhook_models import INFLOW_CONTRACT_VERSION

    return {
        "status": overall_status,
        "service": "regengine",
        "probe": "liveness",
        "readiness_url": "/readiness",
        "dependencies_verified": False,
        "kafka": kafka_status,
        "webhook_hmac_configured": hmac_configured,
        "inflow_contract_version": INFLOW_CONTRACT_VERSION,
        "build": current_build_info().public_dict(),
    }


@router.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, object]:
    """Compatibility liveness path used by older probes and frontend checks."""
    return health()


@router.get("/api/health", include_in_schema=False)
def api_health() -> dict[str, object]:
    """Compatibility liveness path used by frontend service discovery."""
    return health()
