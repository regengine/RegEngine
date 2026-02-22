from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...fsma_metrics import record_trace_query
from ...fsma_utils import (
    TraceResult,
    get_lot_timeline,
    trace_backward,
    trace_forward,
)
from ...neo4j_utils import Neo4jClient
from shared.auth import require_api_key
from ...models.fsma_nodes import (
    CTEType,
    TraceEvent,
    Lot,
    Facility,
    Document,
    FSMARelationships,
)
from shared.fsma_validation import (
    validate_gln,
    validate_gtin,
    validate_tlc,
)

import uuid
import sys
from pathlib import Path

# Add shared utilities (portable path resolution)
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
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


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
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


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
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")
@router.get("/traceability/regulations")
async def get_governing_regulations_endpoint(
    lot_tlc: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """Find all regulations governing a specific Lot."""
    from kernel.graph_traceability import TraceabilityLinker
    from ...config import settings
    
    linker = TraceabilityLinker(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password
    )
    try:
        regulations = await linker.get_governing_regulations(lot_tlc, str(tenant_id))
        await linker.close()
        return {"lot_tlc": lot_tlc, "regulations": regulations}
    except Exception as e:
        await linker.close()
        logger.error("get_governing_regulations_failed", lot_tlc=lot_tlc, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traceability/impacted-lots")
async def get_impacted_lots_endpoint(
    obligation_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """Find all lots impacted by a specific regulatory obligation."""
    from kernel.graph_traceability import TraceabilityLinker
    from ...config import settings
    
    linker = TraceabilityLinker(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password
    )
    try:
        lots = await linker.get_impacted_lots(obligation_id, str(tenant_id))
        await linker.close()
        return {"obligation_id": obligation_id, "impacted_lots": lots}
    except Exception as e:
        await linker.close()
        logger.error("get_impacted_lots_failed", obligation_id=obligation_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/traceability/link/{obligation_id}")
async def link_obligation_endpoint(
    obligation_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """Trigger automated linking of a regulation to supply chain events."""
    from kernel.graph_traceability import TraceabilityLinker
    from ...config import settings
    
    linker = TraceabilityLinker(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password
    )
    try:
        links = await linker.link_obligation_to_traceability(obligation_id, str(tenant_id))
        await linker.close()
        return {"status": "linked", "links_created": len(links), "links": links}
    except Exception as e:
        await linker.close()
        logger.error("link_obligation_failed", obligation_id=obligation_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MOBILE FIELD CAPTURE ENDPOINTS
# ============================================================================

class TraceabilityEventRequest(BaseModel):
    event_type: CTEType
    event_date: str
    tlc: str
    location_identifier: str
    quantity: Optional[float] = None
    uom: Optional[str] = None
    product_description: Optional[str] = None
    gtin: Optional[str] = None
    image_data: Optional[str] = None


@router.post("/event")
async def log_traceability_event(
    request: TraceabilityEventRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    High-integrity endpoint for logging Critical Tracking Events from mobile dock.
    Performs real-time validation of identifiers and persists directly to Neo4j.
    """
    logger.info("logging_mobile_event", event_type=request.event_type, tlc=request.tlc)

    # 1. Validation Logic
    tlc_result = validate_tlc(request.tlc)
    if not tlc_result.is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid TLC: {tlc_result.errors[0].message}")

    gln_result = validate_gln(request.location_identifier)
    if not gln_result.is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid Location (GLN): {gln_result.errors[0].message}")

    if request.gtin:
        gtin_result = validate_gtin(request.gtin)
        if not gtin_result.is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid GTIN: {gtin_result.errors[0].message}")

    # 2. Persistence to Neo4j
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    client = Neo4jClient(database=db_name)
    event_id = str(uuid.uuid4())

    try:
        async with client.session() as session:
            # Create TraceEvent
            trace_event = TraceEvent(
                event_id=event_id,
                type=request.event_type,
                event_date=request.event_date,
                tenant_id=str(tenant_id),
            )
            await session.run(TraceEvent.create_cypher(), properties=trace_event.node_properties)

            # Create/Merge Lot
            lot = Lot(
                tlc=request.tlc,
                gtin=request.gtin,
                product_description=request.product_description,
                quantity=request.quantity,
                unit_of_measure=request.uom,
                tenant_id=str(tenant_id),
            )
            await session.run(Lot.merge_cypher(), tlc=request.tlc, properties=lot.node_properties)

            # Create/Merge Facility
            facility = Facility(
                gln=request.location_identifier,
                tenant_id=str(tenant_id),
            )
            await session.run(Facility.merge_cypher(), gln=request.location_identifier, properties=facility.node_properties)

            # Link Relationships
            await session.run(FSMARelationships.LOT_UNDERWENT_EVENT, tlc=request.tlc, event_id=event_id)
            await session.run(FSMARelationships.EVENT_OCCURRED_AT, event_id=event_id, gln=request.location_identifier)

            # 3. Handle Evidence (BOL Photo)
            if request.image_data:
                doc_id = str(uuid.uuid4())
                document = Document(
                    document_id=doc_id,
                    document_type="BOL",
                    # In a production environment, we would upload to S3. 
                    # For this pilot, we store the Base64 as the raw_content.
                    source_uri=f"base64://{doc_id}",
                    raw_content=request.image_data,
                    extraction_timestamp=datetime.now().isoformat(),
                    tenant_id=str(tenant_id)
                )
                await session.run(Document.merge_cypher(), document_id=doc_id, properties=document.node_properties)
                # Link Document to Event
                await session.run(FSMARelationships.DOCUMENT_EVIDENCES, document_id=doc_id, event_id=event_id)
                logger.info("secured_evidence_payload", doc_id=doc_id, event_id=event_id)

        await client.close()
        return {
            "status": "success",
            "event_id": event_id,
            "tlc": request.tlc,
            "message": f"Successfully secured {request.event_type} event on the immutable ledger.",
        }

    except Exception as e:
        await client.close()
        logger.error("mobile_event_logging_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to persist event: {str(e)}")
