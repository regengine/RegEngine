import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import neo4j.exceptions
import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ...fsma_audit import FSMAAuditAction, FSMAAuditActorType, get_audit_log
from ...fsma_metrics import record_trace_query
from ...fsma_utils import (
    TraceResult,
    get_lot_timeline,
    query_events_by_range,
    trace_backward,
    trace_forward,
)
from ...neo4j_utils import Neo4jClient
from neo4j.exceptions import Neo4jError, ServiceUnavailable
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

from shared.rate_limit import limiter

router = APIRouter(tags=["Traceability"])
logger = structlog.get_logger("fsma-traceability")


@router.get(
    "/trace/forward/{tlc}",
    responses={
        200: {
            "description": "Forward trace result",
            "content": {
                "application/json": {
                    "example": {
                        "lot_id": "LOT-2026-04-A1",
                        "direction": "forward",
                        "facilities": [
                            {"gln": "0614141000012", "name": "Distribution Center Alpha", "type": "distribution_center"},
                            {"gln": "0614141000029", "name": "Metro Fresh Market", "type": "retail"},
                        ],
                        "events": [
                            {"cte_type": "shipping", "location": "Distribution Center Alpha", "timestamp": "2026-04-12T16:00:00Z"},
                            {"cte_type": "receiving", "location": "Metro Fresh Market", "timestamp": "2026-04-13T08:30:00Z"},
                        ],
                        "downstream_lots": ["LOT-2026-04-B2"],
                        "total_quantity": 500,
                        "query_time_ms": 142,
                        "hop_count": 2,
                        "time_violations": [],
                        "risk_flags": [],
                    }
                }
            },
        }
    },
)
@limiter.limit("10/minute")
async def trace_forward_endpoint(
    request: Request,
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

        # #1033: audit KDE/CTE read access
        _actor = getattr(api_key, "key_id", str(api_key)) if api_key else "API"
        get_audit_log().log(
            action=FSMAAuditAction.KDE_READ,
            target_type="KDE",
            target_id=tlc,
            actor=_actor,
            actor_type=FSMAAuditActorType.API,
            tenant_id=str(tenant_id),
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
    except (neo4j.exceptions.Neo4jError, ConnectionError) as e:
        duration = time.time() - start_time
        record_trace_query("forward", duration, "error", 0, 0)
        logger.exception("trace_forward_error", tlc=tlc, error=str(e))
        logger.error("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get(
    "/trace/backward/{tlc}",
    responses={
        200: {
            "description": "Backward trace result",
            "content": {
                "application/json": {
                    "example": {
                        "lot_id": "LOT-2026-04-A1",
                        "direction": "backward",
                        "facilities": [
                            {"gln": "0614141000029", "name": "Port of Long Beach", "type": "first_receiver"},
                            {"gln": "0614141000036", "name": "Salinas Valley Farm", "type": "grower"},
                        ],
                        "events": [
                            {"cte_type": "receiving", "location": "Distribution Center Alpha", "timestamp": "2026-04-12T14:30:00Z"},
                            {"cte_type": "shipping", "location": "Port of Long Beach", "timestamp": "2026-04-11T08:00:00Z"},
                            {"cte_type": "harvesting", "location": "Salinas Valley Farm", "timestamp": "2026-04-10T06:00:00Z"},
                        ],
                        "source_lots": [],
                        "total_quantity": 500,
                        "query_time_ms": 98,
                        "hop_count": 3,
                    }
                }
            },
        }
    },
)
@limiter.limit("10/minute")
async def trace_backward_endpoint(
    request: Request,
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

        # #1033: best-effort KDE_READ audit (FSMA 204 / NIST AU-2)
        try:
            _actor = getattr(api_key, "key_id", str(api_key)) if api_key else "API"
            get_audit_log().log(
                action=FSMAAuditAction.KDE_READ,
                target_type="KDE",
                target_id=tlc,
                actor=_actor,
                actor_type=FSMAAuditActorType.API,
                tenant_id=str(tenant_id),
                diff=[FSMAAuditDiff("record_ids", None, [tlc] + (result.lots or []))],
            )
        except Exception as _ae:
            logger.error("kde_read_audit_failed", tlc=tlc, error=str(_ae))

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
    except (neo4j.exceptions.Neo4jError, ConnectionError) as e:
        duration = time.time() - start_time
        record_trace_query("backward", duration, "error", 0, 0)
        logger.exception("trace_backward_error", tlc=tlc, error=str(e))
        logger.error("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/timeline/{tlc}")
@limiter.limit("10/minute")
async def lot_timeline_endpoint(
    request: Request,
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

        # #1033: audit KDE/CTE read access
        _actor = getattr(api_key, "key_id", str(api_key)) if api_key else "API"
        get_audit_log().log(
            action=FSMAAuditAction.KDE_READ,
            target_type="KDE",
            target_id=tlc,
            actor=_actor,
            actor_type=FSMAAuditActorType.API,
            tenant_id=str(tenant_id),
        )

        return {"lot_id": tlc, "events": timeline}
    except (neo4j.exceptions.Neo4jError, ConnectionError) as e:
        logger.exception("timeline_error", tlc=tlc, error=str(e))
        logger.error("endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
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
    except (neo4j.exceptions.Neo4jError, ConnectionError, ValueError) as e:
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
    except (neo4j.exceptions.Neo4jError, ConnectionError, ValueError) as e:
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
    except (neo4j.exceptions.Neo4jError, ConnectionError, ValueError) as e:
        await linker.close()
        logger.error("link_obligation_failed", obligation_id=obligation_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/events")
@limiter.limit("10/minute")
async def search_traceability_events(
    request: Request,
    start_date: Optional[str] = Query(
        default=None,
        description="Start date (YYYY-MM-DD). Defaults to 30 days ago.",
    ),
    end_date: Optional[str] = Query(
        default=None,
        description="End date (YYYY-MM-DD). Defaults to today.",
    ),
    product_contains: Optional[str] = Query(
        default=None,
        max_length=120,
        description="Case-insensitive product description filter.",
    ),
    facility_contains: Optional[str] = Query(
        default=None,
        max_length=120,
        description="Case-insensitive facility name/address/GLN filter.",
    ),
    cte_type: Optional[str] = Query(
        default=None,
        max_length=32,
        description="Optional CTE type filter (RECEIVING, SHIPPING, etc).",
    ),
    limit: int = Query(100, ge=1, le=500),
    starting_after: Optional[str] = Query(
        default=None,
        max_length=128,
        description="Cursor based on event_id from the prior page.",
    ),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Search traceability events by date range + optional product/facility/CTE filters.

    This endpoint is optimized for NLP query adapters and dashboard search UIs.
    """
    db_name = Neo4jClient.get_tenant_database_name(tenant_id)
    client = Neo4jClient(database=db_name)

    now = datetime.now(timezone.utc).date()
    effective_end = end_date or now.isoformat()
    effective_start = start_date or (now - timedelta(days=30)).isoformat()
    normalized_cte = cte_type.upper() if cte_type else None

    try:
        events = await query_events_by_range(
            client,
            effective_start,
            effective_end,
            str(tenant_id),
            product_contains=product_contains,
            facility_contains=facility_contains,
            cte_type=normalized_cte,
            limit=limit + 1,
            starting_after=starting_after,
        )
        await client.close()

        has_more = len(events) > limit
        page_events = events[:limit]
        next_cursor = page_events[-1]["event_id"] if has_more and page_events else None

        # #1033: audit KDE/CTE read access on search
        _actor = getattr(api_key, "key_id", str(api_key)) if api_key else "API"
        get_audit_log().log(
            action=FSMAAuditAction.KDE_READ,
            target_type="KDE",
            target_id=f"search:{effective_start}:{effective_end}",
            actor=_actor,
            actor_type=FSMAAuditActorType.API,
            tenant_id=str(tenant_id),
        )

        return {
            "count": len(page_events),
            "events": page_events,
            "has_more": has_more,
            "next_cursor": next_cursor,
            "filters": {
                "start_date": effective_start,
                "end_date": effective_end,
                "product_contains": product_contains,
                "facility_contains": facility_contains,
                "cte_type": normalized_cte,
            },
        }
    except (neo4j.exceptions.Neo4jError, ConnectionError) as exc:
        logger.exception(
            "traceability_search_error",
            error=str(exc),
            tenant_id=str(tenant_id),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# MOBILE FIELD CAPTURE ENDPOINTS
# ============================================================================

class TraceabilityEventRequest(BaseModel):
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_type": "receiving",
                    "event_date": "2026-04-12",
                    "tlc": "LOT-2026-04-A1",
                    "location_identifier": "0614141000012",
                    "quantity": 500,
                    "uom": "cases",
                    "product_description": "Organic romaine lettuce, 24ct",
                    "responsible_party_contact": "Jane Doe, 555-0100, jane@example.com",
                    "gtin": "00614141000012",
                },
                {
                    "event_type": "shipping",
                    "event_date": "2026-04-12",
                    "tlc": "LOT-2026-04-A1",
                    "location_identifier": "0614141000029",
                    "quantity": 200,
                    "uom": "cases",
                    "product_description": "Organic romaine lettuce, 24ct",
                    "responsible_party_contact": "John Smith, 555-0200, john@example.com",
                    "gtin": "00614141000012",
                },
            ]
        }
    }

    event_type: CTEType
    event_date: str
    tlc: str
    location_identifier: str
    responsible_party_contact: str  # FSMA 204 KDE per 21 CFR 1.1370(c)
    quantity: Optional[float] = None
    uom: Optional[str] = None
    product_description: Optional[str] = None
    gtin: Optional[str] = None
    image_data: Optional[str] = None


@router.post("/event")
@limiter.limit("10/minute")
async def log_traceability_event(
    request: Request,
    payload: TraceabilityEventRequest = Body(...),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    High-integrity endpoint for logging Critical Tracking Events from mobile dock.
    Performs real-time validation of identifiers and persists directly to Neo4j.
    """
    logger.info("logging_mobile_event", event_type=payload.event_type, tlc=payload.tlc)

    # 1. Validation Logic
    tlc_result = validate_tlc(payload.tlc)
    if not tlc_result.is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid TLC: {tlc_result.errors[0].message}")

    gln_result = validate_gln(payload.location_identifier)
    if not gln_result.is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid Location (GLN): {gln_result.errors[0].message}")

    if payload.gtin:
        gtin_result = validate_gtin(payload.gtin)
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
                type=payload.event_type,
                event_date=payload.event_date,
                tenant_id=str(tenant_id),
                responsible_party_contact=payload.responsible_party_contact,
            )
            await session.run(TraceEvent.create_cypher(), properties=trace_event.node_properties)

            # Create/Merge Lot
            lot = Lot(
                tlc=payload.tlc,
                gtin=payload.gtin,
                product_description=payload.product_description,
                quantity=payload.quantity,
                unit_of_measure=payload.uom,
                tenant_id=str(tenant_id),
            )
            await session.run(Lot.merge_cypher(), tlc=payload.tlc, properties=lot.node_properties)

            # Create/Merge Facility
            facility = Facility(
                gln=payload.location_identifier,
                tenant_id=str(tenant_id),
            )
            await session.run(Facility.merge_cypher(), gln=payload.location_identifier, properties=facility.node_properties)

            # Link Relationships
            # #1284: pass tenant_id so the MATCH clauses don't walk cross-tenant
            # nodes that happen to share a TLC/event_id/GLN with the caller.
            await session.run(
                FSMARelationships.LOT_UNDERWENT_EVENT,
                tlc=payload.tlc,
                event_id=event_id,
                tenant_id=str(tenant_id),
            )
            await session.run(
                FSMARelationships.EVENT_OCCURRED_AT,
                event_id=event_id,
                gln=payload.location_identifier,
                tenant_id=str(tenant_id),
            )

            # 3. Handle Evidence (BOL Photo)
            if payload.image_data:
                doc_id = str(uuid.uuid4())
                document = Document(
                    document_id=doc_id,
                    document_type="BOL",
                    # In a production environment, we would upload to S3. 
                    # For this pilot, we store the Base64 as the raw_content.
                    source_uri=f"base64://{doc_id}",
                    raw_content=payload.image_data,
                    extraction_timestamp=datetime.now().isoformat(),
                    tenant_id=str(tenant_id)
                )
                await session.run(Document.merge_cypher(), document_id=doc_id, properties=document.node_properties)
                # Link Document to Event — tenant-scoped to prevent cross-tenant
                # edges when a document_id or event_id collides across tenants (#1284).
                await session.run(
                    FSMARelationships.DOCUMENT_EVIDENCES,
                    document_id=doc_id,
                    event_id=event_id,
                    tenant_id=str(tenant_id),
                )
                logger.info("secured_evidence_payload", doc_id=doc_id, event_id=event_id)

        await client.close()

        # Bridge to canonical pipeline so mobile events are visible to
        # FDA export, compliance scoring, and the canonical records API.
        try:
            from shared.canonical_event import (
                TraceabilityEvent as CanonicalTraceabilityEvent,
                CTEType as CanonicalCTEType,
                IngestionSource,
                ProvenanceMetadata,
            )
            from shared.canonical_persistence import CanonicalEventStore
            from shared.database import SessionLocal

            # Map graph CTEType to canonical CTEType
            _cte_map = {
                "HARVESTING": "harvesting", "COOLING": "cooling",
                "INITIAL_PACKING": "initial_packing",
                "FIRST_LAND_BASED_RECEIVING": "first_land_based_receiving",
                "SHIPPING": "shipping", "RECEIVING": "receiving",
                "TRANSFORMATION": "transformation",
            }
            cte_val = payload.event_type.value if hasattr(payload.event_type, "value") else str(payload.event_type)
            canonical_cte = _cte_map.get(cte_val.upper(), cte_val.lower())

            kdes = {}
            if payload.gtin:
                kdes["gtin"] = payload.gtin

            provenance = ProvenanceMetadata(
                mapper_name="mobile_capture_bridge",
                mapper_version="1.0.0",
                original_format="json",
                normalization_rules_applied=["mobile_field_capture"],
            )

            canonical_event = CanonicalTraceabilityEvent(
                event_id=uuid.UUID(event_id),
                tenant_id=tenant_id,
                source_system=IngestionSource.MOBILE_CAPTURE,
                event_type=CanonicalCTEType(canonical_cte),
                event_timestamp=payload.event_date,
                traceability_lot_code=payload.tlc,
                product_reference=payload.product_description or "",
                lot_reference=payload.tlc,
                quantity=payload.quantity or 1.0,
                unit_of_measure=payload.uom or "each",
                from_facility_reference=payload.location_identifier,
                kdes=kdes,
                raw_payload={
                    "event_type": cte_val,
                    "event_date": payload.event_date,
                    "tlc": payload.tlc,
                    "location_identifier": payload.location_identifier,
                    "quantity": payload.quantity,
                    "uom": payload.uom,
                    "product_description": payload.product_description,
                    "gtin": payload.gtin,
                },
                provenance_metadata=provenance,
            ).prepare_for_persistence()

            db = SessionLocal()
            try:
                store = CanonicalEventStore(db, dual_write=True)
                store.persist_event(canonical_event)
                db.commit()
            except Exception:  # Catch-all: must rollback on any failure
                db.rollback()
                raise
            finally:
                db.close()

            logger.info("mobile_event_canonical_bridged", event_id=event_id, tlc=payload.tlc)
        except (ImportError, ValueError, KeyError, TypeError) as bridge_err:
            # Non-blocking: Neo4j write already succeeded
            logger.warning("mobile_canonical_bridge_failed", event_id=event_id, error=str(bridge_err))

        return {
            "status": "success",
            "event_id": event_id,
            "tlc": payload.tlc,
            "message": f"Successfully secured {payload.event_type} event on the immutable ledger.",
        }

    except (neo4j.exceptions.Neo4jError, ConnectionError) as e:
        await client.close()
        logger.error("mobile_event_logging_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to persist event: {str(e)}")
