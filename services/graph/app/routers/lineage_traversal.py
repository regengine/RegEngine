"""Fact lineage traversal — version history for regulatory facts.

Provides endpoints to retrieve the complete version chain of a
regulatory fact identified by its Traceability Lot Code (TLC),
including both current and superseded versions.
"""

from __future__ import annotations

import time
import uuid
import sys
from pathlib import Path
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..neo4j_utils import Neo4jClient
from shared.auth import require_api_key

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.middleware import get_current_tenant_id

from shared.rate_limit import limiter

router = APIRouter(tags=["Lineage"])
logger = structlog.get_logger("fact-lineage")


# ── Response Models ──────────────────────────────────────────────────────────


class FactVersion(BaseModel):
    """A single version of a regulatory fact."""
    version: int
    record_hash: Optional[str] = None
    prev_hash: Optional[str] = None
    created_at: Optional[str] = None
    superseded_at: Optional[str] = None
    superseded_by: Optional[str] = None
    is_current: bool = False
    source_document: Optional[str] = None
    fact_type: Optional[str] = None
    properties: dict = {}


class FactLineageResponse(BaseModel):
    """Full version history for a fact."""
    tlc: str
    total_versions: int
    current_version: int
    versions: List[FactVersion]
    query_time_ms: float


# ── Cypher Queries ───────────────────────────────────────────────────────────

# Query to find a fact and all its previous versions via SUPERSEDES chain.
# SECURITY (#1256): the variable-length `[:SUPERSEDES*0..50]` traversal
# must filter tenant on *every* node in the path, not just the start.
# Without the `ALL(n IN nodes(path) WHERE n.tenant_id = $tenant_id)`
# predicate, an attacker could reach another tenant's RegulatoryFact
# via a shared SUPERSEDES chain and read its version history.
LINEAGE_QUERY = """
MATCH (current:RegulatoryFact {tlc: $tlc, tenant_id: $tenant_id})
OPTIONAL MATCH path = (current)-[:SUPERSEDES*0..50]->(older:RegulatoryFact)
WHERE path IS NULL OR ALL(n IN nodes(path) WHERE n.tenant_id = $tenant_id)
WITH collect(DISTINCT older) AS all_versions, current
UNWIND all_versions AS v
WITH v, current
WHERE v IS NULL OR v.tenant_id = $tenant_id
RETURN
    v.tlc AS tlc,
    v.version AS version,
    v.record_hash AS record_hash,
    v.prev_hash AS prev_hash,
    v.created_at AS created_at,
    v.superseded_at AS superseded_at,
    v.source_document AS source_document,
    v.fact_type AS fact_type,
    v = current AS is_current,
    properties(v) AS all_props
ORDER BY v.version DESC
"""

# Simpler alternative: find all facts with same TLC regardless of chain
LINEAGE_BY_TLC_QUERY = """
MATCH (f:RegulatoryFact {tenant_id: $tenant_id})
WHERE f.tlc = $tlc OR f.lot_number = $tlc OR f.identifier = $tlc
WITH f ORDER BY f.version DESC, f.created_at DESC
OPTIONAL MATCH (f)-[:SUPERSEDES]->(prev:RegulatoryFact)
RETURN
    f.tlc AS tlc,
    coalesce(f.version, 1) AS version,
    f.record_hash AS record_hash,
    f.prev_hash AS prev_hash,
    f.created_at AS created_at,
    f.superseded_at AS superseded_at,
    f.source_document AS source_document,
    f.fact_type AS fact_type,
    f.is_current AS is_current,
    prev.tlc AS superseded_by,
    properties(f) AS all_props
"""


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/lineage/{tlc}/history",
    response_model=FactLineageResponse,
    summary="Get fact version history",
    description=(
        "Returns the full version chain for a regulatory fact, including "
        "both current and all superseded (non-current) versions. "
        "Useful for audit trails and change tracking."
    ),
)
@limiter.limit("10/minute")
async def get_fact_lineage(
    request: Request,
    tlc: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """Retrieve all versions of a regulatory fact by its TLC."""
    start_time = time.time()
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    client = Neo4jClient(database=db_name)

    try:
        # Try chain-based traversal first
        records = await client.execute_read(
            LINEAGE_QUERY,
            tlc=tlc,
            tenant_id=str(tenant_id),
        )

        # Fall back to TLC-based lookup if chain traversal returns nothing
        if not records:
            records = await client.execute_read(
                LINEAGE_BY_TLC_QUERY,
                tlc=tlc,
                tenant_id=str(tenant_id),
            )

        await client.close()

        if not records:
            raise HTTPException(
                status_code=404,
                detail=f"No regulatory fact found for TLC '{tlc}'"
            )

        # Build version list
        versions = []
        max_version = 0
        tenant_str = str(tenant_id)
        for record in records:
            props = record.get("all_props", {}) if record.get("all_props") else {}

            # SECURITY (#1256): invariant check — every returned record
            # must belong to the caller's tenant. If a cross-tenant row
            # somehow slipped past the Cypher filter, fail loudly rather
            # than leak.
            record_tenant = props.get("tenant_id") if props else None
            if record_tenant not in (None, "", tenant_str):
                logger.error(
                    "lineage_tenant_invariant_violation",
                    tlc=tlc,
                    expected_tenant=tenant_str,
                    record_tenant=record_tenant,
                )
                raise HTTPException(
                    status_code=500,
                    detail="lineage invariant violation: cross-tenant record",
                )

            # Remove internal properties from the properties dict
            display_props = {
                k: v for k, v in props.items()
                if k not in {
                    "tlc", "version", "record_hash", "prev_hash",
                    "created_at", "superseded_at", "tenant_id",
                    "source_document", "fact_type", "is_current",
                    "identifier", "lot_number",
                }
            }

            ver = record.get("version", 1) or 1
            max_version = max(max_version, ver)

            versions.append(FactVersion(
                version=ver,
                record_hash=record.get("record_hash"),
                prev_hash=record.get("prev_hash"),
                created_at=str(record["created_at"]) if record.get("created_at") else None,
                superseded_at=str(record["superseded_at"]) if record.get("superseded_at") else None,
                superseded_by=record.get("superseded_by"),
                is_current=bool(record.get("is_current", False)),
                source_document=record.get("source_document"),
                fact_type=record.get("fact_type"),
                properties=display_props,
            ))

        duration_ms = (time.time() - start_time) * 1000

        return FactLineageResponse(
            tlc=tlc,
            total_versions=len(versions),
            current_version=max_version,
            versions=versions,
            query_time_ms=round(duration_ms, 2),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("lineage_query_error", tlc=tlc, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
