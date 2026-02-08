from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
import uuid
import sys
from pathlib import Path

# Add shared utilities (portable path resolution)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.middleware import get_current_tenant_id
from shared.auth import require_api_key

from .neo4j_utils import Neo4jClient

# Health/metrics router at root level (operational endpoints)
router = APIRouter()

# Versioned API router for graph endpoints
v1_router = APIRouter(prefix="/v1", tags=["v1"])

logger = structlog.get_logger("graph-api")


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
            status_code=503, detail="Neo4j unavailable or unreachable"
        ) from exc
    finally:
        if client is not None:
            await client.close()


@router.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@v1_router.get("/provisions/by-request")
async def provisions_by_request_id(
    request_id: str = Query(..., alias="id"),
    api_key: str = Depends(require_api_key),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id)
):
    """Return provisions that have provenance.request_id equal to the given id.

    Query param: `id` (UUID string)
    """
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    results = []
    try:
        client = Neo4jClient(database=db_name)
        async with client.session() as session:
            cypher_query = (
                "MATCH (p:Provision) "
                "WHERE p.provenance.request_id = $request_id AND p.tenant_id = $tenant_id "
                "RETURN p.hash AS hash, p.status AS status, p.provenance AS provenance, "
                "p.extraction AS extraction, p.doc_hash AS doc_hash, p.tenant_id AS tenant_id "
                "LIMIT 100"
            )
            result = await session.run(cypher_query, request_id=request_id, tenant_id=str(tenant_id))
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
        await client.close()
        logger.info("provisions_by_request", request_id=request_id, count=len(results))
        return {"count": len(results), "items": results}
    except Exception as exc:  # pragma: no cover - infra dependent
        logger.exception(
            "provisions_by_request_error", request_id=request_id, error=str(exc)
        )
        return {"count": 0, "items": []}
