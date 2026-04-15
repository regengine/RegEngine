"""
FSMA 204 forward and backward tracing through the supply chain graph.

Supports FDA 24-hour recall requirements via Neo4j graph traversal
with Physics Engine time arrow enforcement.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import structlog

from ..neo4j_utils import Neo4jClient
from shared.fsma_rules import TraceEvent as SharedTraceEvent, TimeArrowRule

from .types import TraceResult

logger = structlog.get_logger("fsma-utils")


async def trace_forward(
    client: Neo4jClient,
    tlc: str,
    max_depth: int = 10,
    tenant_id: Optional[str] = None,
    enforce_time_arrow: bool = True,
) -> TraceResult:
    """
    Trace forward from a lot to find all downstream products and customers.

    Given a raw material Lot ID, find all shipped finished goods and customers.
    This is the primary query for recall scenarios.

    Physics Engine Enhancement:
    - Time Arrow: Only follows paths where events are in temporal order
      (event_next.date >= event_prev.date).  When ``enforce_time_arrow``
      is True the Cypher query pre-filters paths, **and** a post-query
      validation pass via ``TimeArrowRule`` strips any events that still
      violate strict UTC ordering (handles time-zone edge cases that
      string comparison in Cypher cannot catch).

    Args:
        client: Neo4j client
        tlc: Traceability Lot Code to trace from
        max_depth: Maximum hops in the trace (default 10)
        tenant_id: Optional tenant filter
        enforce_time_arrow: If True, validates temporal ordering (default True)

    Returns:
        TraceResult with all downstream facilities, events, lots, and any time violations
    """
    if not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError(f"max_depth must be a positive integer, got {max_depth!r}")

    start_time = time.time()

    # Cap variable-length expansion to avoid combinatorial blowup.
    # Each logical hop (Lot->Event->Lot) is 2 relationships, so
    # max_depth hops = max_depth * 2 relationship traversals.
    # Neo4j Cypher does not support parameterized bounds in *1..N,
    # so we must interpolate — but we cap at 20 to keep plans bounded.
    rel_depth = min(max_depth * 2, 20)

    # Optimized Cypher query with temporal ordering hint.
    # Performance notes:
    # - USING INDEX hint on Lot(tlc) forces the planner to anchor on
    #   the indexed start node rather than scanning all Lot nodes
    # - Dropped unused `rels` variable from WITH to reduce memory
    # - LIMIT 5000 caps result set to prevent runaway expansion on
    #   dense supply chain graphs
    query = (
        """
    MATCH path = (start:Lot {tlc: $tlc})-[:UNDERWENT|PRODUCED*1.."""
        + str(rel_depth)
        + """]->(end)
    USING INDEX start:Lot(tlc)
    WHERE ($tenant_id IS NULL OR start.tenant_id = $tenant_id)
    WITH path, nodes(path) as path_nodes

    // Extract events with dates for temporal validation
    WITH path, path_nodes,
         [n IN path_nodes WHERE n:TraceEvent | {event_id: n.event_id, event_date: n.event_date, type: n.type}] as event_nodes

    // Filter paths: all events must be in temporal order (Time Arrow constraint)
    WITH path, path_nodes, event_nodes
    WHERE size(event_nodes) <= 1 OR
          all(idx IN range(0, size(event_nodes)-2)
              WHERE event_nodes[idx].event_date IS NULL
                 OR event_nodes[idx+1].event_date IS NULL
                 OR event_nodes[idx].event_date <= event_nodes[idx+1].event_date)

    UNWIND path_nodes as node
    WITH DISTINCT node, path
    RETURN
        labels(node) as labels,
        properties(node) as props,
        length(path) as hop_count
    ORDER BY hop_count
    LIMIT 5000
    """
    )

    # Fallback query without temporal filtering (for comparison or if disabled).
    # Same optimizations: index hint, capped depth, LIMIT.
    query_no_time_filter = (
        """
    MATCH path = (start:Lot {tlc: $tlc})-[:UNDERWENT|PRODUCED*1.."""
        + str(rel_depth)
        + """]->(end)
    USING INDEX start:Lot(tlc)
    WHERE ($tenant_id IS NULL OR start.tenant_id = $tenant_id)
    WITH path, nodes(path) as path_nodes
    UNWIND path_nodes as node
    WITH DISTINCT node, path
    RETURN
        labels(node) as labels,
        properties(node) as props,
        length(path) as hop_count
    ORDER BY hop_count
    LIMIT 5000
    """
    )

    facilities = []
    events = []
    lots = []
    max_hops = 0
    total_quantity = 0.0

    # Use time-filtered query if enforcing time arrow
    active_query = query if enforce_time_arrow else query_no_time_filter

    async with client.session() as session:
        result = await session.run(active_query, tlc=tlc, tenant_id=tenant_id)

        async for record in result:
            labels = record["labels"]
            props = record["props"]
            hop = record["hop_count"]
            max_hops = max(max_hops, hop)

            if "Facility" in labels:
                facilities.append(
                    {
                        "gln": props.get("gln"),
                        "name": props.get("name"),
                        "address": props.get("address"),
                        "facility_type": props.get("facility_type"),
                    }
                )
            elif "TraceEvent" in labels:
                events.append(
                    {
                        "event_id": props.get("event_id"),
                        "type": props.get("type"),
                        "event_date": props.get("event_date"),
                        "confidence": props.get("confidence"),
                        "risk_flag": props.get("risk_flag"),
                    }
                )
            elif "Lot" in labels:
                lot_qty = props.get("quantity", 0) or 0
                total_quantity += lot_qty
                lots.append(
                    {
                        "tlc": props.get("tlc"),
                        "product_description": props.get("product_description"),
                        "quantity": lot_qty,
                        "unit_of_measure": props.get("unit_of_measure"),
                    }
                )

    # Also get directly connected facilities via SHIPPED_TO
    facility_query = """
    MATCH (l:Lot {tlc: $tlc})-[:UNDERWENT]->(e:TraceEvent)-[:SHIPPED_TO]->(f:Facility)
    WHERE ($tenant_id IS NULL OR l.tenant_id = $tenant_id)
    RETURN DISTINCT properties(f) as facility
    """

    async with client.session() as session:
        result = await session.run(facility_query, tlc=tlc, tenant_id=tenant_id)
        async for record in result:
            fac = record["facility"]
            if fac and fac not in [
                f for f in facilities if f.get("gln") == fac.get("gln")
            ]:
                facilities.append(
                    {
                        "gln": fac.get("gln"),
                        "name": fac.get("name"),
                        "address": fac.get("address"),
                        "facility_type": fac.get("facility_type"),
                    }
                )

    # ------------------------------------------------------------------
    # Strict Time Arrow enforcement via shared SSOT rule
    # ------------------------------------------------------------------
    # The Cypher string-comparison filter above handles the common case,
    # but cannot account for timezone normalization.  We run the canonical
    # TimeArrowRule as a second pass and *remove* any events that create
    # a temporal paradox, ensuring only causally valid events survive.
    # ------------------------------------------------------------------
    time_violations: List[Dict[str, Any]] = []

    if enforce_time_arrow and len(events) >= 2:
        # Build SharedTraceEvent list (skip events we cannot parse)
        parseable_events: List[SharedTraceEvent] = []
        parseable_indices: List[int] = []
        for idx, e in enumerate(events):
            if e.get("event_id") and e.get("event_date"):
                try:
                    parseable_events.append(SharedTraceEvent(
                        event_id=e["event_id"],
                        tlc=tlc,
                        event_date=e["event_date"],
                        event_type=e.get("type"),
                    ))
                    parseable_indices.append(idx)
                except (ValueError, TypeError) as err:
                    logger.warning(
                        "trace_event_validation_skip",
                        event_id=e["event_id"],
                        error=str(err),
                    )

        if len(parseable_events) >= 2:
            rule = TimeArrowRule()
            validation = rule.validate(parseable_events)

            if not validation.passed:
                # Collect violating event IDs so we can strip them
                violating_ids: set = set()
                for v in validation.violations:
                    details = v.details or {}
                    time_violations.append({
                        "violation_type": "TIME_ARROW",
                        "description": v.description,
                        "prev_event_id": v.event_ids[0] if v.event_ids else None,
                        "curr_event_id": v.event_ids[1] if len(v.event_ids) > 1 else None,
                        "prev_event_date": details.get("upstream_date"),
                        "curr_event_date": details.get("downstream_date"),
                    })
                    # The *downstream* event is the one that violates causality
                    if len(v.event_ids) > 1:
                        violating_ids.add(v.event_ids[1])

                # Strip violating events from the result set so callers
                # never see causally-impossible paths.
                if violating_ids:
                    events = [
                        e for e in events
                        if e.get("event_id") not in violating_ids
                    ]
                    logger.info(
                        "time_arrow_events_stripped",
                        tlc=tlc,
                        stripped_count=len(violating_ids),
                        stripped_ids=list(violating_ids),
                    )

    # Collect risk flags from events
    risk_flags = list(set(e.get("risk_flag") for e in events if e.get("risk_flag")))

    query_time = (time.time() - start_time) * 1000  # Convert to ms

    logger.info(
        "trace_forward_completed",
        tlc=tlc,
        facilities=len(facilities),
        events=len(events),
        lots=len(lots),
        time_violations=len(time_violations),
        risk_flags=risk_flags,
        query_time_ms=round(query_time, 2),
    )

    return TraceResult(
        lot_id=tlc,
        direction="forward",
        facilities=facilities,
        events=events,
        lots=lots,
        total_quantity=total_quantity if total_quantity > 0 else None,
        query_time_ms=round(query_time, 2),
        hop_count=max_hops,
        time_violations=time_violations if time_violations else None,
        risk_flags=risk_flags if risk_flags else None,
    )


async def trace_backward(
    client: Neo4jClient,
    tlc: str,
    max_depth: int = 10,
    tenant_id: Optional[str] = None,
) -> TraceResult:
    """
    Trace backward from a lot to find all source materials and suppliers.

    Given a finished good Lot ID, find all raw material Lots.

    Args:
        client: Neo4j client
        tlc: Traceability Lot Code to trace from
        max_depth: Maximum hops in the trace (default 10)
        tenant_id: Optional tenant filter

    Returns:
        TraceResult with all upstream facilities, events, and lots
    """
    if not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError(f"max_depth must be a positive integer, got {max_depth!r}")

    start_time = time.time()

    # Cap variable-length expansion (same rationale as trace_forward)
    rel_depth = min(max_depth * 2, 20)

    # Optimized Cypher query to trace backward through transformations.
    # Path: Lot <- PRODUCED <- TraceEvent <- CONSUMED <- Lot
    # Performance notes:
    # - USING INDEX hint anchors on indexed Lot(tlc) start node
    # - Capped rel_depth prevents combinatorial blowup
    # - LIMIT 5000 provides a safety net on dense graphs
    query = (
        """
    MATCH path = (start:Lot {tlc: $tlc})<-[:PRODUCED|CONSUMED*1.."""
        + str(rel_depth)
        + """]-(source)
    USING INDEX start:Lot(tlc)
    WHERE ($tenant_id IS NULL OR start.tenant_id = $tenant_id)
    WITH path, nodes(path) as path_nodes
    UNWIND path_nodes as node
    WITH DISTINCT node, path
    RETURN
        labels(node) as labels,
        properties(node) as props,
        length(path) as hop_count
    ORDER BY hop_count
    LIMIT 5000
    """
    )

    facilities = []
    events = []
    lots = []
    max_hops = 0
    total_quantity = 0.0

    async with client.session() as session:
        result = await session.run(query, tlc=tlc, tenant_id=tenant_id)

        async for record in result:
            labels = record["labels"]
            props = record["props"]
            hop = record["hop_count"]
            max_hops = max(max_hops, hop)

            if "Facility" in labels:
                facilities.append(
                    {
                        "gln": props.get("gln"),
                        "name": props.get("name"),
                        "address": props.get("address"),
                        "facility_type": props.get("facility_type"),
                    }
                )
            elif "TraceEvent" in labels:
                events.append(
                    {
                        "event_id": props.get("event_id"),
                        "type": props.get("type"),
                        "event_date": props.get("event_date"),
                        "confidence": props.get("confidence"),
                    }
                )
            elif "Lot" in labels:
                lot_qty = props.get("quantity", 0) or 0
                total_quantity += lot_qty
                lots.append(
                    {
                        "tlc": props.get("tlc"),
                        "product_description": props.get("product_description"),
                        "quantity": lot_qty,
                        "unit_of_measure": props.get("unit_of_measure"),
                    }
                )

    # Also get source facilities via SHIPPED relationship
    facility_query = """
    MATCH (f:Facility)-[:SHIPPED]->(e:TraceEvent)-[:INCLUDED]->(l:Lot {tlc: $tlc})
    WHERE ($tenant_id IS NULL OR l.tenant_id = $tenant_id)
    RETURN DISTINCT properties(f) as facility
    """

    async with client.session() as session:
        result = await session.run(facility_query, tlc=tlc, tenant_id=tenant_id)
        async for record in result:
            fac = record["facility"]
            if fac and fac not in [
                f for f in facilities if f.get("gln") == fac.get("gln")
            ]:
                facilities.append(
                    {
                        "gln": fac.get("gln"),
                        "name": fac.get("name"),
                        "address": fac.get("address"),
                        "facility_type": fac.get("facility_type"),
                    }
                )

    query_time = (time.time() - start_time) * 1000

    logger.info(
        "trace_backward_completed",
        tlc=tlc,
        facilities=len(facilities),
        events=len(events),
        lots=len(lots),
        query_time_ms=round(query_time, 2),
    )

    return TraceResult(
        lot_id=tlc,
        direction="backward",
        facilities=facilities,
        events=events,
        lots=lots,
        total_quantity=total_quantity if total_quantity > 0 else None,
        query_time_ms=round(query_time, 2),
        hop_count=max_hops,
    )
