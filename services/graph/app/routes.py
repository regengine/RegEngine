from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from shared.metrics_auth import require_metrics_key
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
import uuid
import sys
from pathlib import Path

# Add shared utilities (portable path resolution)
from shared.middleware import get_current_tenant_id
from shared.auth import require_api_key

from .neo4j_utils import Neo4jClient
from shared.rate_limit import limiter

# Health/metrics router at root level (operational endpoints)
router = APIRouter()

# Versioned API router for graph endpoints
v1_router = APIRouter(tags=["v1"])

from .routers import labels, lineage_traversal, regulations
from .routers.fsma import trace_router, science_router, recall_router, metrics_router, compliance_router

logger = structlog.get_logger("graph-api")

v1_router.include_router(regulations.router, prefix="/regulations", tags=["regulations"])
v1_router.include_router(labels.router, prefix="/labels", tags=["labels"])
v1_router.include_router(lineage_traversal.router, prefix="/lineage", tags=["lineage"])

# FSMA sub-routers
v1_router.include_router(trace_router, prefix="/fsma/traceability", tags=["fsma-traceability"])
v1_router.include_router(science_router, prefix="/fsma/science", tags=["fsma-science"])
v1_router.include_router(recall_router, prefix="/fsma/recall", tags=["fsma-recall"])
v1_router.include_router(metrics_router, prefix="/fsma/metrics", tags=["fsma-metrics"])
v1_router.include_router(compliance_router, prefix="/fsma/compliance", tags=["fsma-compliance"])

router.include_router(v1_router)


@router.get("/health")
async def health():
    """Health check endpoint with Neo4j verification."""
    client = None
    try:
        client = Neo4jClient(database=Neo4jClient.get_global_database_name())
        async with client.session() as session:
            await session.run("RETURN 1")
        return {"status": "healthy", "neo4j": "available"}
    except Exception as exc:
        logger.error("graph_health_neo4j_unavailable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="Graph database unavailable"
        ) from exc
    finally:
        if client is not None:
            await client.close()


@router.get("/ready")
async def readiness():
    """Readiness probe for k8s orchestration."""
    return {"status": "ready", "service": "graph-api"}


@router.get("/metrics", dependencies=[Depends(require_metrics_key)])
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@v1_router.get("/provisions/by-request")
@limiter.limit("10/minute")
async def provisions_by_request_id(
    request: Request,
    request_id: str = Query(..., alias="id"),
    limit: int = Query(default=50, ge=1, le=200, description="Max items to return (1–200)"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip"),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Return provisions whose provenance.request_id matches ``id``.

    Supports offset-based pagination via ``limit`` and ``offset`` (#564).

    Query params:
        id      (required) — request UUID to look up
        limit   (optional, default 50, max 200)
        offset  (optional, default 0)

    Response:
        count       — number of items in this page
        total_count — total matching provisions (for pagination UI)
        limit / offset — echo of request params
        items       — paginated provision records
    """
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    results = []
    total_count = 0
    client = None
    try:
        client = Neo4jClient(database=db_name)
        async with client.session() as session:
            # Count query — runs before the data fetch so callers can build
            # "page X of Y" UI without a second round-trip.
            count_query = (
                "MATCH (p:Provision) "
                "WHERE p.provenance.request_id = $request_id AND p.tenant_id = $tenant_id "
                "RETURN count(p) AS total"
            )
            count_result = await session.run(
                count_query, request_id=request_id, tenant_id=str(tenant_id)
            )
            count_record = await count_result.single()
            total_count = count_record["total"] if count_record else 0

            # Data query — SKIP/LIMIT applied server-side in Neo4j
            data_query = (
                "MATCH (p:Provision) "
                "WHERE p.provenance.request_id = $request_id AND p.tenant_id = $tenant_id "
                "RETURN p.hash AS hash, p.status AS status, p.provenance AS provenance, "
                "p.extraction AS extraction, p.doc_hash AS doc_hash, p.tenant_id AS tenant_id "
                "ORDER BY p.hash "
                "SKIP $offset LIMIT $limit"
            )
            result = await session.run(
                data_query,
                request_id=request_id,
                tenant_id=str(tenant_id),
                offset=offset,
                limit=limit,
            )
            async for rec in result:
                results.append(
                    {
                        "hash": rec["hash"],
                        "status": rec["status"],
                        "provenance": rec["provenance"],
                        "extraction": rec["extraction"],
                        "doc_hash": rec["doc_hash"],
                        "tenant_id": rec["tenant_id"],
                    }
                )

        logger.info(
            "provisions_by_request",
            request_id=request_id,
            count=len(results),
            total_count=total_count,
            limit=limit,
            offset=offset,
        )
        return {
            "count": len(results),
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "items": results,
        }
    except Exception as exc:  # pragma: no cover - infra dependent
        logger.exception(
            "provisions_by_request_error", request_id=request_id, error=str(exc)
        )
        raise HTTPException(
            status_code=500,
            detail="Graph database error while fetching provisions.",
        ) from exc
    finally:
        if client is not None:
            await client.close()
