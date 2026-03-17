from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
import uuid
import sys
from pathlib import Path

# Add shared utilities (portable path resolution)
from shared.middleware import get_current_tenant_id
from shared.auth import require_api_key

from .neo4j_utils import Neo4jClient

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
