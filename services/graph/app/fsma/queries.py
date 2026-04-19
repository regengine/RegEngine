"""
FSMA 204 event queries: timeline, date-range search, and risk tagging.

Provides Neo4j queries for lot timelines, FDA reporting date-range
queries, and event risk flag tagging.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import structlog

from ..neo4j_utils import Neo4jClient

logger = structlog.get_logger("fsma-utils")


async def get_lot_timeline(
    client: Neo4jClient,
    tlc: str,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get chronological timeline of all events for a lot.

    Args:
        client: Neo4j client
        tlc: Traceability Lot Code
        tenant_id: Optional tenant filter

    Returns:
        List of events in chronological order
    """
    # SECURITY (#1261): every joined node must be tenant-scoped, not just
    # the start Lot. Without the predicate on ``e`` and ``f`` the OPTIONAL
    # MATCH can cross into another tenant's TraceEvent / Facility and return
    # its name, address, GLN in the timeline — a privacy leak into the UI.
    #
    # Cypher note: attaching ``WHERE`` to an OPTIONAL MATCH filters *that*
    # pattern — rows where the tenant predicate fails get f=NULL rather than
    # being dropped entirely, which matches the caller contract (timeline
    # still returns the event; facility just renders as None).
    query = """
    MATCH (l:Lot {tlc: $tlc})-[:UNDERWENT]->(e:TraceEvent)
    WHERE ($tenant_id IS NULL OR (
              l.tenant_id = $tenant_id
              AND e.tenant_id = $tenant_id
          ))
    OPTIONAL MATCH (e)-[:OCCURRED_AT]->(f:Facility)
      WHERE ($tenant_id IS NULL OR f.tenant_id = $tenant_id)
    RETURN
        e.event_id as event_id,
        e.type as type,
        e.event_date as event_date,
        e.event_time as event_time,
        e.confidence as confidence,
        e.tenant_id as event_tenant,
        f.name as facility_name,
        f.gln as facility_gln,
        f.tenant_id as facility_tenant
    ORDER BY e.event_date, e.event_time
    """

    timeline = []
    async with client.session() as session:
        result = await session.run(query, tlc=tlc, tenant_id=tenant_id)
        async for record in result:
            # SECURITY (#1261): runtime invariant — if Cypher ever returns a
            # cross-tenant event (future query edit, index fallback, etc.)
            # raise loudly rather than leak into the caller's payload.
            event_tenant = record["event_tenant"]
            facility_tenant = record["facility_tenant"]
            if tenant_id is not None:
                if event_tenant not in (None, "", tenant_id):
                    logger.error(
                        "get_lot_timeline_tenant_invariant_violation",
                        tlc=tlc,
                        expected_tenant=tenant_id,
                        event_tenant=event_tenant,
                    )
                    raise ValueError(
                        "get_lot_timeline tenant invariant violation: "
                        f"event tenant={event_tenant!r} != caller {tenant_id!r}"
                    )
                if (
                    record["facility_name"] is not None
                    and facility_tenant not in (None, "", tenant_id)
                ):
                    logger.error(
                        "get_lot_timeline_facility_invariant_violation",
                        tlc=tlc,
                        expected_tenant=tenant_id,
                        facility_tenant=facility_tenant,
                    )
                    raise ValueError(
                        "get_lot_timeline facility invariant violation: "
                        f"facility tenant={facility_tenant!r} != caller {tenant_id!r}"
                    )

            timeline.append(
                {
                    "event_id": record["event_id"],
                    "type": record["type"],
                    "event_date": record["event_date"],
                    "event_time": record["event_time"],
                    "confidence": record["confidence"],
                    "facility": (
                        {
                            "name": record["facility_name"],
                            "gln": record["facility_gln"],
                        }
                        if record["facility_name"]
                        else None
                    ),
                }
            )

    return timeline


async def query_events_by_range(
    client: Neo4jClient,
    start_date: str,
    end_date: str,
    tenant_id: Optional[str] = None,
    *,
    product_contains: Optional[str] = None,
    facility_contains: Optional[str] = None,
    cte_type: Optional[str] = None,
    limit: int = 500,
    starting_after: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Query all TraceEvents within a date range for FDA reporting.

    Includes joined Lot and Facility data for each event to populate
    the FDA Sortable Spreadsheet columns.

    Args:
        client: Neo4j client
        start_date: Start date (ISO format YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        end_date: End date
        tenant_id: Optional tenant filter

    Returns:
        List of event objects with lot and facility details
    """
    # Normalize dates if needed (assuming string comparison works for ISO dates in Neo4j)
    # Search endpoint support adds optional field filters and cursor paging.
    #
    # SECURITY (#1261): this query feeds the FDA Sortable Spreadsheet export.
    # Before this fix, only the root TraceEvent was tenant-scoped — the
    # joined Lot and Facility were unrestricted, so an event in tenant A
    # with an UNDERWENT edge pointing back to a Lot in tenant B would emit
    # tenant B's product_description and quantity in tenant A's FDA CSV.
    # The OCCURRED_AT join into Facility had the symmetric leak. Every
    # joined node now carries the tenant predicate.
    query = """
    MATCH (e:TraceEvent)
    WHERE ($tenant_id IS NULL OR e.tenant_id = $tenant_id)
    AND e.event_date >= $start_date AND e.event_date <= $end_date
    AND ($cte_type IS NULL OR toUpper(e.type) = toUpper($cte_type))
    AND ($starting_after IS NULL OR e.event_id > $starting_after)

    // Join with Lot (Input/Output) — tenant-scoped (#1261)
    OPTIONAL MATCH (e)<-[:UNDERWENT]-(l:Lot)
      WHERE ($tenant_id IS NULL OR l.tenant_id = $tenant_id)

    // Join with Facility (Location) — tenant-scoped (#1261)
    OPTIONAL MATCH (e)-[:OCCURRED_AT]->(f:Facility)
      WHERE ($tenant_id IS NULL OR f.tenant_id = $tenant_id)

    WITH e, l, f
    WHERE (
        $product_contains IS NULL
        OR toLower(coalesce(l.product_description, '')) CONTAINS toLower($product_contains)
    )
    AND (
        $facility_contains IS NULL
        OR toLower(
            coalesce(f.name, '') + ' ' + coalesce(f.address, '') + ' ' + coalesce(f.gln, '')
        ) CONTAINS toLower($facility_contains)
    )

    RETURN
        e.event_id as event_id,
        e.type as type,
        e.event_date as event_date,
        e.event_time as event_time,
        e.risk_flag as risk_flag,
        l.tlc as tlc,
        l.product_description as product_description,
        l.quantity as quantity,
        l.unit_of_measure as uom,
        l.tenant_id as lot_tenant,
        f.name as facility_name,
        f.gln as facility_gln,
        f.address as facility_address,
        f.tenant_id as facility_tenant
    ORDER BY e.event_date, e.event_time, e.event_id
    LIMIT $limit
    """

    events = []
    async with client.session() as session:
        result = await session.run(
            query,
            start_date=start_date,
            end_date=end_date,
            tenant_id=tenant_id,
            product_contains=product_contains,
            facility_contains=facility_contains,
            cte_type=cte_type,
            limit=max(1, min(1000, int(limit))),
            starting_after=starting_after,
        )
        async for record in result:
            # SECURITY (#1261): defence in depth — if Cypher ever returns a
            # cross-tenant Lot or Facility (e.g. via a future query edit),
            # drop the row and log loudly rather than leak into the FDA CSV.
            # The Cypher predicates above are the primary guard; this
            # runtime check pins the contract for CI and future refactors.
            lot_tenant = record["lot_tenant"]
            facility_tenant = record["facility_tenant"]
            if tenant_id is not None:
                if record["tlc"] is not None and lot_tenant not in (None, "", tenant_id):
                    logger.error(
                        "query_events_by_range_lot_invariant_violation",
                        expected_tenant=tenant_id,
                        lot_tenant=lot_tenant,
                        event_id=record["event_id"],
                    )
                    raise ValueError(
                        "query_events_by_range lot invariant violation: "
                        f"lot tenant={lot_tenant!r} != caller {tenant_id!r}"
                    )
                if (
                    record["facility_name"] is not None
                    and facility_tenant not in (None, "", tenant_id)
                ):
                    logger.error(
                        "query_events_by_range_facility_invariant_violation",
                        expected_tenant=tenant_id,
                        facility_tenant=facility_tenant,
                        event_id=record["event_id"],
                    )
                    raise ValueError(
                        "query_events_by_range facility invariant violation: "
                        f"facility tenant={facility_tenant!r} != caller {tenant_id!r}"
                    )

            events.append({
                "event_id": record["event_id"],
                "type": record["type"],
                "event_date": record["event_date"],
                "event_time": record["event_time"],
                "risk_flag": record["risk_flag"],
                "tlc": record["tlc"] or "N/A",
                "product_description": record["product_description"] or "",
                "quantity": record["quantity"],
                "unit_of_measure": record["uom"],
                "location_description": record["facility_name"] or record["facility_address"] or "Unknown",
                "location_gln": record["facility_gln"] or "",
                "reference_doc_type": "Invoice", # Placeholder for now
                "reference_doc_num": record["event_id"], # Using Event ID as proxy for Ref Doc
            })

    logger.info(
        "range_query_completed",
        start=start_date,
        end=end_date,
        count=len(events),
        cte_type=cte_type,
        has_product_filter=bool(product_contains),
        has_facility_filter=bool(facility_contains),
    )
    return events


async def _tag_event_risk_flag(
    client: Neo4jClient,
    event_id: str,
    risk_flag: str,
    *,
    tenant_id: str,
) -> bool:
    """
    Tag a TraceEvent node with a risk_flag property.

    Tenant-scoped: the MATCH clause restricts mutation to the caller's
    tenant, preventing cross-tenant writes for colliding ``event_id``
    values. The composite uniqueness constraint on TraceEvent is
    ``(event_id, tenant_id)`` meaning two tenants can legitimately
    share an ``event_id``; requiring ``tenant_id`` in the MATCH ensures
    we only mutate the caller's row.

    Args:
        client: Neo4j client
        event_id: The event to tag
        risk_flag: The risk flag value (e.g., "BROKEN_CHAIN", "TIME_ARROW")
        tenant_id: Tenant UUID (required; keyword-only). A TypeError is
            raised if omitted. Pass the tenant context the caller is
            authenticated against -- never a user-controllable value.

    Returns:
        True if tag was set on a TraceEvent owned by ``tenant_id``,
        False if no matching event was found (either because the event
        does not exist OR it belongs to a different tenant).
    """
    if not tenant_id:
        # Fail closed -- an empty/None tenant_id would degrade to a
        # cross-tenant MATCH. Raise so callers notice at dev time.
        raise ValueError(
            "_tag_event_risk_flag requires a non-empty tenant_id to prevent "
            "cross-tenant writes"
        )

    query = """
    MATCH (e:TraceEvent {event_id: $event_id, tenant_id: $tenant_id})
    SET e.risk_flag = $risk_flag
    RETURN e.event_id as tagged_id
    """

    try:
        async with client.session() as session:
            result = await session.run(
                query,
                event_id=event_id,
                risk_flag=risk_flag,
                tenant_id=tenant_id,
            )
            record = await result.single()

            if record:
                logger.info(
                    "event_risk_flag_tagged",
                    event_id=event_id,
                    risk_flag=risk_flag,
                    tenant_id=tenant_id,
                )
                return True
            return False
    except Exception as e:
        logger.error(
            "event_risk_flag_tag_failed",
            event_id=event_id,
            risk_flag=risk_flag,
            tenant_id=tenant_id,
            error=str(e),
        )
        return False
