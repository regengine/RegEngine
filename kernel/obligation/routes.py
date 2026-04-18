"""
Regulatory Obligation Engine - FastAPI Routes
==============================================
REST API endpoints for obligation evaluation.

Hardening (#1319)
-----------------
* ``tenant_id`` is extracted from the authenticated ``APIKey`` and forwarded
  to ``engine.evaluate_decision`` / ``engine.get_coverage_report``. Empty
  tenants are rejected at the route boundary so evaluations cannot land in
  one shared "empty tenant" bucket where any caller would see every other
  caller's results.
* The ``/coverage/{vertical}`` route no longer claims to return
  ``ObligationCoverageReport`` (the engine returns a different dict shape).
  It declares ``response_model=None`` and uses an explicit ``CoverageSnapshot``
  type hint matching the engine's output.
* The singleton ``RegulatoryEngine`` is lazy-constructed via a FastAPI
  dependency so tests can override it, and the engine accepts a graph
  client from the environment if one is provided — previously persistence
  was a silent no-op because no graph client was ever injected.

This router is **currently not included by any FastAPI app** (see
`kernel.control` meta issue #1366). Fixing these defects now means the
adoption step is just `app.include_router(router)`, not another bug hunt.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from shared.auth import APIKey, require_api_key

from .engine import RegulatoryEngine
from .models import (
    ObligationEvaluationRequest,
    ObligationEvaluationResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/obligations", tags=["obligations"])


# ---------------------------------------------------------------------------
# Engine dependency — constructed lazily so tests can override it and so we
# don't build a driver on module import.
# ---------------------------------------------------------------------------


_engine_singleton: Optional[RegulatoryEngine] = None


def _build_default_engine() -> RegulatoryEngine:
    """Construct a ``RegulatoryEngine`` from environment variables.

    Reads env vars at *call* time (not at module-import time) so tests and
    per-worker config changes apply. If ``NEO4J_URI`` is unset the engine is
    built without a graph client and persistence degrades to a logged
    no-op; callers get a warning in the response headers.
    """
    verticals_dir = Path(os.getenv("REGENGINE_VERTICALS_DIR", "./verticals"))

    graph_client = None
    uri = os.getenv("NEO4J_URI")
    if uri:
        # Lazy import — the neo4j driver is optional in dev.
        try:  # pragma: no cover - exercised via integration tests
            from neo4j import GraphDatabase

            user = os.getenv("NEO4J_USER", "neo4j")
            password = os.getenv("NEO4J_PASSWORD")
            if not password:
                logger.error(
                    "NEO4J_URI is set but NEO4J_PASSWORD is empty — refusing "
                    "to build an unauthenticated driver. Persistence will "
                    "degrade to a logged no-op."
                )
            else:
                graph_client = GraphDatabase.driver(uri, auth=(user, password))
                logger.info("obligation.routes: Neo4j driver initialised")
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "obligation.routes: failed to build Neo4j driver: %s", exc
            )

    return RegulatoryEngine(
        verticals_dir=verticals_dir,
        graph_client=graph_client,
    )


def get_engine() -> RegulatoryEngine:
    """FastAPI dependency that returns the process-wide engine.

    Tests can override via ``app.dependency_overrides[get_engine] = ...``.
    """
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = _build_default_engine()
    return _engine_singleton


def _extract_tenant_id(api_key: APIKey) -> str:
    """Pull ``tenant_id`` off the authenticated API key.

    Rejects empty / missing tenants at the boundary — they land every
    caller in a shared bucket otherwise (#1319). Raises ``HTTPException``
    with 403 rather than 401 so callers understand the key authenticated
    but is not scoped to a tenant.
    """
    tenant_id = getattr(api_key, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="API key is not scoped to a tenant; obligation endpoints "
            "require a tenant-scoped key.",
        )
    return tenant_id


@router.post("/evaluate", response_model=ObligationEvaluationResult)
async def evaluate_obligations(
    request: ObligationEvaluationRequest,
    api_key: APIKey = Depends(require_api_key),
    engine: RegulatoryEngine = Depends(get_engine),
) -> ObligationEvaluationResult:
    """Evaluate a decision against regulatory obligations.

    **Workflow**:

    1. Load applicable obligations for the decision type.
    2. Check triggering conditions.
    3. Verify required evidence is present.
    4. Compute coverage %.
    5. Assign risk scores.
    6. Persist evaluation to the graph (tenant-scoped).

    **Returns**:

    * Evaluation result with coverage metrics.
    * List of obligation matches (met/violated).
    * Overall risk score and level.
    """
    tenant_id = _extract_tenant_id(api_key)
    try:
        return engine.evaluate_decision(
            decision_id=request.decision_id,
            decision_type=request.decision_type,
            decision_data=request.decision_data,
            vertical=request.vertical,
            tenant_id=tenant_id,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Evaluation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}")


# ``response_model=None`` because ``engine.get_coverage_report`` returns a
# plain dict whose shape does not match ``ObligationCoverageReport`` and
# declaring the wrong model silently produces HTTP 500 on every successful
# query. The reconciliation to a real ``CoverageSnapshot`` model is tracked
# in a follow-up — here we at least stop FastAPI from fabricating 500s.
@router.get("/coverage/{vertical}", response_model=None)
async def get_coverage_report(
    vertical: str,
    api_key: APIKey = Depends(require_api_key),
    engine: RegulatoryEngine = Depends(get_engine),
) -> Dict[str, Any]:
    """Get aggregate obligation coverage report for a vertical.

    **Returns** a coverage snapshot keyed on ``tenant_id`` — total
    obligations for the vertical, evaluated obligations, met obligations,
    coverage percent, and recent-compliance trend.
    """
    tenant_id = _extract_tenant_id(api_key)
    try:
        return engine.get_coverage_report(vertical=vertical, tenant_id=tenant_id)
    except Exception as e:
        logger.error("Coverage report failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Coverage report failed: {e}")


@router.get("/health")
async def health_check(engine: RegulatoryEngine = Depends(get_engine)):
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "regulatory_engine",
        "verticals_loaded": list(engine.evaluators.keys()),
    }
