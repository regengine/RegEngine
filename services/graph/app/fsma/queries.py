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
    query = """
    MATCH (l:Lot {tlc: $tlc})-[:UNDERWENT]->(e:TraceEvent)
    WHERE ($tenant_id IS NULL OR l.tenant_id = $tenant_id)
    OPTIONAL MATCH (e)-[:OCCURRED_AT]->(f:Facility)
    RETURN
        e.event_id as event_id,
        e.type as type,
        e.event_date as event_date,
        e.event_time as event_time,
        e.confidence as confidence,
        f.name as facility_name,
        f.gln as facility_gln
    ORDER BY e.event_date, e.event_time
    """

    timeline = []
    async with client.session() as session:
        result = await session.run(query, tlc=tlc, tenant_id=tenant_id)
        async for record in result:
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
    query = """
    MATCH (e:TraceEvent)
    WHERE ($tenant_id IS NULL OR e.tenant_id = $tenant_id)
    AND e.event_date >= $start_date AND e.event_date <= $end_date
    AND ($cte_type IS NULL OR toUpper(e.type) = toUpper($cte_type))
    AND ($starting_after IS NULL OR e.event_id > $starting_after)

    // Join with Lot (Input/Output)
    OPTIONAL MATCH (e)<-[:UNDERWENT]-(l:Lot)

    // Join with Facility (Location)
    OPTIONAL MATCH (e)-[:OCCURRED_AT]->(f:Facility)

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
        f.name as facility_name,
        f.gln as facility_gln,
        f.address as facility_address
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
) -> bool:
    """
    Tag a TraceEvent node with a risk_flag property.

    Args:
        client: Neo4j client
        event_id: The event to tag
        risk_flag: The risk flag value (e.g., "BROKEN_CHAIN", "TIME_ARROW")

    Returns:
        True if tag was set, False otherwise
    """
    query = """
    MATCH (e:TraceEvent {event_id: $event_id})
    SET e.risk_flag = $risk_flag
    RETURN e.event_id as tagged_id
    """

    try:
        async with client.session() as session:
            result = await session.run(query, event_id=event_id, risk_flag=risk_flag)
            record = await result.single()

            if record:
                logger.info(
                    "event_risk_flag_tagged",
                    event_id=event_id,
                    risk_flag=risk_flag,
                )
                return True
            return False
    except Exception as e:
        logger.error(
            "event_risk_flag_tag_failed",
            event_id=event_id,
            risk_flag=risk_flag,
            error=str(e),
        )
        return False
