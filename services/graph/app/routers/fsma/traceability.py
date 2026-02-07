from __future__ import annotations

import time
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from ...fsma_metrics import record_trace_query
from ...fsma_utils import (
    TraceResult,
    get_lot_timeline,
    trace_backward,
    trace_forward,
)
from ...neo4j_utils import Neo4jClient
from shared.auth import require_api_key

import uuid
import sys
# Add shared utilities
sys.path.insert(0, '/Users/christophersellers/Desktop/RegEngine/services')
from shared.middleware import get_current_tenant_id

router = APIRouter(tags=["Traceability"])
logger = structlog.get_logger("fsma-traceability")


@router.get("/trace/forward/{tlc}")
async def trace_forward_endpoint(
    tlc: str,
    max_depth: int = Query(10, ge=1, le=20, description="Maximum hops in trace"),
    enforce_time_arrow: bool = Query(
        True, description="Enforce temporal ordering (Physics Engine)"
    ),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Trace forward from a lot to find all downstream facilities and products.

    Given a raw material Traceability Lot Code (TLC), returns all facilities
    the lot was shipped to and any downstream products created from it.

    Physics Engine Enhancement:
    - Time Arrow: Only follows paths where events are in temporal order
    - Returns time_violations if any events violate causal ordering
    - Returns risk_flags accumulated from traversed events

    Use case: Recall scenario - find all customers who received contaminated product.
    """
    start_time = time.time()
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    client = Neo4jClient(database=db_name)

    try:
        result = await trace_forward(
            client, tlc, max_depth, str(tenant_id), enforce_time_arrow=enforce_time_arrow
        )
        await client.close()

        # Record metrics
        duration = time.time() - start_time
        record_trace_query(
            direction="forward",
            duration_seconds=duration,
            status="success",
            hop_count=result.hop_count,
            facility_count=len(result.facilities),
        )

        return {
            "lot_id": result.lot_id,
            "direction": result.direction,
            "facilities": result.facilities,
            "events": result.events,
            "downstream_lots": result.lots,
            "total_quantity": result.total_quantity,
            "query_time_ms": result.query_time_ms,
            "hop_count": result.hop_count,
            # Physics Engine additions
            "time_violations": result.time_violations,
            "risk_flags": result.risk_flags,
        }
    except Exception as e:
        duration = time.time() - start_time
        record_trace_query("forward", duration, "error", 0, 0)
        logger.exception("trace_forward_error", tlc=tlc, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trace/backward/{tlc}")
async def trace_backward_endpoint(
    tlc: str,
    max_depth: int = Query(10, ge=1, le=20, description="Maximum hops in trace"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Trace backward from a lot to find all source materials and suppliers.

    Given a finished goods Traceability Lot Code (TLC), returns all raw material
    lots and source facilities that contributed to the product.

    Use case: Root cause analysis - trace contamination back to source.
    """
    start_time = time.time()
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    client = Neo4jClient(database=db_name)

    try:
        result = await trace_backward(client, tlc, max_depth, str(tenant_id))
        await client.close()

        # Record metrics
        duration = time.time() - start_time
        record_trace_query(
            direction="backward",
            duration_seconds=duration,
            status="success",
            hop_count=result.hop_count,
            facility_count=len(result.facilities),
        )

        return {
            "lot_id": result.lot_id,
            "direction": result.direction,
            "facilities": result.facilities,
            "events": result.events,
            "source_lots": result.lots,
            "total_quantity": result.total_quantity,
            "query_time_ms": result.query_time_ms,
            "hop_count": result.hop_count,
        }
    except Exception as e:
        duration = time.time() - start_time
        record_trace_query("backward", duration, "error", 0, 0)
        logger.exception("trace_backward_error", tlc=tlc, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline/{tlc}")
async def lot_timeline_endpoint(
    tlc: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Get chronological timeline of all events for a specific lot.

    Returns all Critical Tracking Events (CTEs) in chronological order
    with associated facility information.
    """
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    client = Neo4jClient(database=db_name)

    try:
        timeline = await get_lot_timeline(client, tlc, str(tenant_id))
        await client.close()
        return {"lot_id": tlc, "events": timeline}
    except Exception as e:
        logger.exception("timeline_error", tlc=tlc, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
