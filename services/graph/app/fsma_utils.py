"""
FSMA 204 Traceability Query Utilities.

Provides forward and backward tracing through the supply chain graph
to support FDA 24-hour recall requirements.

Physics Engine:
- Time Arrow enforcement via shared.fsma_rules.TimeArrowRule
- Broken chain detection for SHIPPING events
- Strict temporal filtering on trace paths
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

from .models.fsma_nodes import CTEType
from .neo4j_utils import Neo4jClient
from shared.fsma_rules import TraceEvent as SharedTraceEvent, TimeArrowRule

logger = structlog.get_logger("fsma-utils")


@dataclass
class TraceResult:
    """Result of a traceability query."""

    lot_id: str
    direction: str  # "forward" or "backward"
    facilities: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    lots: List[Dict[str, Any]]
    total_quantity: Optional[float]
    query_time_ms: float
    hop_count: int
    # Physics Engine additions
    time_violations: Optional[List[Dict[str, Any]]] = None
    risk_flags: Optional[List[str]] = None


# Legacy wrapper functions for backward compatibility with tests.
# The core logic lives in shared.fsma_rules but these are still imported
# by test_fsma_physics.py.


def _validate_temporal_order(events: list) -> list:
    """
    Validate that events are in temporal order.

    Wrapper around shared.fsma_rules.TimeArrowRule for backward compatibility.

    Args:
        events: List of dicts with 'event_id' and 'event_date' keys.

    Returns:
        List of violation dicts (empty list if no violations).
    """
    from shared.fsma_rules import TraceEvent as SharedTraceEvent, TimeArrowRule

    trace_events = []
    for e in events:
        eid = e.get("event_id")
        edate = e.get("event_date")
        if eid and edate:
            try:
                trace_events.append(SharedTraceEvent(
                    event_id=eid,
                    tlc="N/A",
                    event_date=edate,
                    event_type=e.get("type"),
                ))
            except (ValueError, TypeError):
                continue

    if len(trace_events) < 2:
        return []

    rule = TimeArrowRule()
    result = rule.validate(trace_events)

    violations = []
    if not result.passed:
        for v in result.violations:
            details = v.details or {}
            violations.append({
                "violation_type": "TIME_ARROW",
                "description": v.description,
                "prev_event_id": v.event_ids[0] if v.event_ids else None,
                "curr_event_id": v.event_ids[1] if len(v.event_ids) > 1 else None,
                "prev_event_date": details.get("upstream_date"),
                "curr_event_date": details.get("downstream_date"),
            })

    return violations


# ============================================================================
# FORWARD / BACKWARD TRACING
# ============================================================================


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


# ============================================================================
# GAP ANALYSIS & BROKEN CHAIN DETECTION
# ============================================================================


async def find_gaps(
    client: Neo4jClient,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find TraceEvents with missing required KDEs.

    FSMA 204 requires specific KDEs for each CTE type. This query
    identifies events that are missing critical data.

    Returns:
        List of events with gap details
    """
    start_time = time.time()

    # Find events missing key fields
    query = """
    MATCH (e:TraceEvent)
    WHERE ($tenant_id IS NULL OR e.tenant_id = $tenant_id)
    AND (
        e.event_date IS NULL OR
        e.event_date = '' OR
        NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) }
    )
    RETURN
        e.event_id as event_id,
        e.type as type,
        e.event_date as event_date,
        e.document_id as document_id,
        CASE WHEN e.event_date IS NULL OR e.event_date = '' THEN 'missing_date' ELSE '' END +
        CASE WHEN NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) } THEN ',missing_lot' ELSE '' END as gaps
    """

    gaps = []
    async with client.session() as session:
        result = await session.run(query, tenant_id=tenant_id)
        async for record in result:
            gaps.append(
                {
                    "event_id": record["event_id"],
                    "type": record["type"],
                    "event_date": record["event_date"],
                    "document_id": record["document_id"],
                    "gaps": [g for g in record["gaps"].split(",") if g],
                    "violation_type": "missing_kde",
                }
            )

    query_time = (time.time() - start_time) * 1000
    logger.info(
        "gap_analysis_completed",
        gap_count=len(gaps),
        query_time_ms=round(query_time, 2),
    )

    return gaps


async def find_broken_chains(
    client: Neo4jClient,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find SHIPPING events that violate chain-of-custody requirements.

    Detects two classes of broken-chain violations:

    1. **Missing Origin** -- A SHIPPING event exists for a Lot that has no
       preceding CREATION, RECEIVING, INITIAL_PACKING, or TRANSFORMATION
       event, meaning the Lot appeared in the supply chain without a
       documented origin.

    2. **Temporal Paradox** -- A SHIPPING event exists for a Lot where the
       earliest origin event (CREATION/RECEIVING/INITIAL_PACKING/TRANSFORMATION) has a date
       *after* the SHIPPING event, violating the Time Arrow constraint.

    FSMA 204 requires full chain of custody -- products cannot be shipped
    without documented receipt or creation, and the origin must precede
    the shipment in time.

    Returns:
        List of violation dicts, each containing event details and
        violation_type ``"broken_chain"``.
    """
    start_time = time.time()

    # ------------------------------------------------------------------ #
    # Query 1: SHIPPING with no origin event at all
    # Optimization: single-hop UNDERWENT only (no variable-length path),
    # LIMIT 2000 caps result set on large tenants for sub-second response.
    # ------------------------------------------------------------------ #
    missing_origin_query = """
    MATCH (l:Lot)-[:UNDERWENT]->(shipping:TraceEvent {type: 'SHIPPING'})
    WHERE ($tenant_id IS NULL OR l.tenant_id = $tenant_id)
    AND NOT EXISTS {
        MATCH (l)-[:UNDERWENT]->(origin:TraceEvent)
        WHERE origin.type IN ['CREATION', 'RECEIVING', 'INITIAL_PACKING', 'TRANSFORMATION']
    }
    RETURN
        shipping.event_id    AS event_id,
        shipping.type         AS type,
        shipping.event_date   AS event_date,
        shipping.document_id  AS document_id,
        l.tlc                 AS lot_tlc,
        l.product_description AS product_description
    ORDER BY shipping.event_date
    LIMIT 2000
    """

    # ------------------------------------------------------------------ #
    # Query 2: SHIPPING that precedes its own origin (Time Arrow violation)
    # ------------------------------------------------------------------ #
    temporal_paradox_query = """
    MATCH (l:Lot)-[:UNDERWENT]->(shipping:TraceEvent {type: 'SHIPPING'})
    WHERE ($tenant_id IS NULL OR l.tenant_id = $tenant_id)
      AND shipping.event_date IS NOT NULL
    WITH l, shipping
    MATCH (l)-[:UNDERWENT]->(origin:TraceEvent)
    WHERE origin.type IN ['CREATION', 'RECEIVING', 'INITIAL_PACKING', 'TRANSFORMATION']
      AND origin.event_date IS NOT NULL
    // Optimization: min() aggregate computes earliest origin date in a single
    // pass, replacing ORDER BY + collect()[0] that sorted all origins per lot.
    WITH l, shipping,
         min(origin.event_date) AS earliest_origin_date,
         head(collect(origin.event_id)) AS earliest_origin_id
    WHERE earliest_origin_date > shipping.event_date
    RETURN
        shipping.event_id            AS event_id,
        shipping.type                AS type,
        shipping.event_date          AS event_date,
        shipping.document_id         AS document_id,
        l.tlc                        AS lot_tlc,
        l.product_description        AS product_description,
        earliest_origin_id           AS origin_event_id,
        earliest_origin_date         AS origin_date
    ORDER BY shipping.event_date
    LIMIT 2000
    """

    violations: List[Dict[str, Any]] = []
    seen_event_ids: set = set()

    async with client.session() as session:
        # --- Missing origin violations --------------------------------
        result = await session.run(missing_origin_query, tenant_id=tenant_id)
        async for record in result:
            eid = record["event_id"]
            if eid in seen_event_ids:
                continue
            seen_event_ids.add(eid)
            violations.append(
                {
                    "event_id": eid,
                    "type": record["type"],
                    "event_date": record["event_date"],
                    "document_id": record["document_id"],
                    "lot_tlc": record["lot_tlc"],
                    "product_description": record["product_description"],
                    "violation_type": "broken_chain",
                    "violation_reason": (
                        "SHIPPING without CREATION, RECEIVING, INITIAL_PACKING, or TRANSFORMATION"
                    ),
                    "gaps": ["missing_origin_event"],
                }
            )

        # --- Temporal paradox violations ------------------------------
        result = await session.run(temporal_paradox_query, tenant_id=tenant_id)
        async for record in result:
            eid = record["event_id"]
            if eid in seen_event_ids:
                continue
            seen_event_ids.add(eid)

            # Validate via TimeArrowRule for authoritative UTC check
            try:
                origin_evt = SharedTraceEvent(
                    event_id=record["origin_event_id"],
                    tlc=record["lot_tlc"] or "N/A",
                    event_date=str(record["origin_date"]),
                    event_type="ORIGIN",
                )
                shipping_evt = SharedTraceEvent(
                    event_id=eid,
                    tlc=record["lot_tlc"] or "N/A",
                    event_date=str(record["event_date"]),
                    event_type="SHIPPING",
                )
                rule = TimeArrowRule()
                rule_result = rule.validate([origin_evt, shipping_evt])
                if not rule_result.passed:
                    desc = rule_result.violations[0].description
                else:
                    # Cypher flagged it but TimeArrowRule disagrees
                    # (edge case with time precision). Skip false positive.
                    continue
            except (ValueError, TypeError):
                desc = (
                    f"SHIPPING {eid} on {record['event_date']} precedes "
                    f"origin {record['origin_event_id']} on {record['origin_date']}"
                )

            violations.append(
                {
                    "event_id": eid,
                    "type": record["type"],
                    "event_date": record["event_date"],
                    "document_id": record["document_id"],
                    "lot_tlc": record["lot_tlc"],
                    "product_description": record["product_description"],
                    "violation_type": "broken_chain",
                    "violation_reason": desc,
                    "gaps": ["temporal_paradox"],
                    "origin_event_id": record["origin_event_id"],
                    "origin_date": (
                        str(record["origin_date"]) if record["origin_date"] else None
                    ),
                }
            )

        # ------------------------------------------------------------------ #
        # Query 3: Cryptographic gap -- SHIPPING events where origin events
        # exist but the merkle_prev_hash chain does not connect the SHIPPING
        # event to any origin event for the same Lot.
        # ------------------------------------------------------------------ #
        crypto_gap_query = """
        MATCH (l:Lot)-[:UNDERWENT]->(shipping:TraceEvent {type: 'SHIPPING'})
        WHERE ($tenant_id IS NULL OR l.tenant_id = $tenant_id)
          AND shipping.merkle_hash IS NOT NULL
        AND EXISTS {
            MATCH (l)-[:UNDERWENT]->(origin:TraceEvent)
            WHERE origin.type IN ['CREATION', 'RECEIVING', 'INITIAL_PACKING']
        }
        WITH l, shipping
        MATCH (l)-[:UNDERWENT]->(origin:TraceEvent)
        WHERE origin.type IN ['CREATION', 'RECEIVING', 'INITIAL_PACKING']
        WITH shipping, l,
             collect({
                 event_id: origin.event_id,
                 type: origin.type,
                 event_date: origin.event_date,
                 merkle_hash: origin.merkle_hash
             }) AS origins
        WHERE shipping.merkle_prev_hash IS NULL
           OR NOT any(o IN origins WHERE o.merkle_hash = shipping.merkle_prev_hash)
        RETURN
            shipping.event_id          AS event_id,
            shipping.type              AS type,
            shipping.event_date        AS event_date,
            shipping.document_id       AS document_id,
            shipping.merkle_hash       AS merkle_hash,
            shipping.merkle_prev_hash  AS merkle_prev_hash,
            l.tlc                      AS lot_tlc,
            l.product_description      AS product_description,
            origins                    AS expected_predecessors
        ORDER BY shipping.event_date
        """

        result = await session.run(crypto_gap_query, tenant_id=tenant_id)
        async for record in result:
            eid = record["event_id"]
            if eid in seen_event_ids:
                continue
            seen_event_ids.add(eid)
            violations.append({
                "event_id": eid,
                "type": record["type"],
                "event_date": record["event_date"],
                "document_id": record["document_id"],
                "lot_tlc": record["lot_tlc"],
                "product_description": record["product_description"],
                "violation_type": "broken_chain",
                "violation_reason": (
                    "SHIPPING event hash-chain does not link to any "
                    "CREATION, RECEIVING, or INITIAL_PACKING event"
                ),
                "merkle_hash": record["merkle_hash"],
                "merkle_prev_hash": record["merkle_prev_hash"],
                "expected_predecessor": record["expected_predecessors"],
                "gaps": ["missing_cryptographic_link"],
            })

    query_time = (time.time() - start_time) * 1000
    logger.info(
        "broken_chain_analysis_completed",
        violation_count=len(violations),
        missing_origin_count=sum(
            1 for v in violations if "missing_origin_event" in v["gaps"]
        ),
        temporal_paradox_count=sum(
            1 for v in violations if "temporal_paradox" in v["gaps"]
        ),
        cryptographic_gap_count=sum(
            1 for v in violations if "missing_cryptographic_link" in v["gaps"]
        ),
        query_time_ms=round(query_time, 2),
    )

    return violations


async def find_all_gaps(
    client: Neo4jClient,
    tenant_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Find all gaps and violations including broken chains.

    Combines results from:
    - find_gaps(): Missing KDE violations
    - find_broken_chains(): Broken chain of custody violations

    Returns:
        Combined list of all gaps and violations
    """
    gaps = await find_gaps(client, tenant_id)
    broken_chains = await find_broken_chains(client, tenant_id)

    # Combine results
    all_violations = gaps + broken_chains

    logger.info(
        "comprehensive_gap_analysis_completed",
        missing_kde_count=len(gaps),
        broken_chain_count=len(broken_chains),
        total_violations=len(all_violations),
    )

    return all_violations


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


# ============================================================================
# DATA QUALITY MONITORS: ORPHAN DETECTION & KDE DRIFT
# ============================================================================


@dataclass
class OrphanLot:
    """A lot that was created/received but never shipped or consumed."""

    tlc: str
    product_description: Optional[str]
    quantity: Optional[float]
    unit_of_measure: Optional[str]
    created_at: Optional[str]
    stagnant_days: int
    last_event_type: Optional[str]
    last_event_date: Optional[str]


@dataclass
class KDECompletenessMetrics:
    """Data quality metrics for a specific event type."""

    event_type: str
    total_events: int
    missing_date_count: int
    missing_date_rate: float
    missing_lot_count: int
    missing_lot_rate: float
    low_confidence_count: int
    low_confidence_rate: float
    average_confidence: float


@dataclass
class DataQualityReport:
    """Aggregate data quality report across all event types."""

    total_events: int
    overall_completeness_rate: float
    metrics_by_type: List[KDECompletenessMetrics]
    trend_direction: str  # "improving", "stable", "degrading"
    query_time_ms: float


async def find_orphaned_lots(
    client: Neo4jClient,
    tenant_id: Optional[str] = None,
    days_stagnant: int = 30,
) -> List[OrphanLot]:
    """
    Find Lots that have been created/received but never shipped or consumed.

    These "orphan" lots represent potential inventory issues or data entry failures:
    - Product received but never used or shipped
    - Transformation outputs that were never distributed
    - Data entry errors where outbound events were not recorded

    FSMA 204 requires complete chain of custody - orphan lots represent
    gaps in the traceability record that may indicate compliance issues.

    Args:
        client: Neo4j client
        tenant_id: Optional tenant filter
        days_stagnant: Minimum days without outbound activity (default 30)

    Returns:
        List of OrphanLot objects with stagnant inventory details
    """
    start_time = time.time()

    # Calculate cutoff date
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_stagnant)).strftime(
        "%Y-%m-%d"
    )

    # Find lots with inbound events but no outbound events
    # Inbound: RECEIVING, CREATION, or PRODUCED by transformation
    # Outbound: SHIPPING, CONSUMED by transformation
    query = """
    MATCH (l:Lot)
    WHERE ($tenant_id IS NULL OR l.tenant_id = $tenant_id)

    // Must have at least one inbound event
    AND EXISTS {
        MATCH (l)-[:UNDERWENT]->(e:TraceEvent)
        WHERE e.type IN ['RECEIVING', 'CREATION']
    } OR EXISTS {
        MATCH (trans:TraceEvent)-[:PRODUCED]->(l)
    }

    // Must NOT have any outbound events
    AND NOT EXISTS {
        MATCH (l)-[:UNDERWENT]->(ship:TraceEvent {type: 'SHIPPING'})
    }
    AND NOT EXISTS {
        MATCH (l)-[:CONSUMED]->(trans:TraceEvent)
    }

    // Get the most recent event for this lot
    OPTIONAL MATCH (l)-[:UNDERWENT]->(last_event:TraceEvent)
    WITH l, last_event
    ORDER BY last_event.event_date DESC
    WITH l, collect(last_event)[0] as most_recent_event

    // Filter by stagnant days
    WHERE most_recent_event IS NULL
       OR most_recent_event.event_date IS NULL
       OR most_recent_event.event_date <= $cutoff_date

    RETURN
        l.tlc as tlc,
        l.product_description as product_description,
        l.quantity as quantity,
        l.unit_of_measure as unit_of_measure,
        l.created_at as created_at,
        most_recent_event.type as last_event_type,
        most_recent_event.event_date as last_event_date
    ORDER BY most_recent_event.event_date ASC
    """

    orphans = []
    async with client.session() as session:
        result = await session.run(query, tenant_id=tenant_id, cutoff_date=cutoff_date)

        async for record in result:
            # Calculate stagnant days
            last_date = record["last_event_date"]
            if last_date:
                try:
                    last_dt = datetime.strptime(str(last_date)[:10], "%Y-%m-%d")
                    stagnant = (datetime.now(timezone.utc) - last_dt).days
                except (ValueError, TypeError):
                    stagnant = days_stagnant  # Default if date parsing fails
            else:
                stagnant = days_stagnant  # Unknown, assume at threshold

            orphans.append(
                OrphanLot(
                    tlc=record["tlc"],
                    product_description=record["product_description"],
                    quantity=record["quantity"],
                    unit_of_measure=record["unit_of_measure"],
                    created_at=(
                        str(record["created_at"]) if record["created_at"] else None
                    ),
                    stagnant_days=stagnant,
                    last_event_type=record["last_event_type"],
                    last_event_date=(
                        str(record["last_event_date"])
                        if record["last_event_date"]
                        else None
                    ),
                )
            )

    query_time = (time.time() - start_time) * 1000

    logger.info(
        "orphan_detection_completed",
        orphan_count=len(orphans),
        days_threshold=days_stagnant,
        query_time_ms=round(query_time, 2),
    )

    return orphans


async def analyze_kde_completeness(
    client: Neo4jClient,
    tenant_id: Optional[str] = None,
    confidence_threshold: float = 0.85,
) -> DataQualityReport:
    """
    Analyze KDE completeness rates across all event types.

    This monitors data quality drift by tracking:
    - Missing date rates
    - Missing lot linkage rates
    - Low confidence extraction rates
    - Average confidence scores

    FSMA 204 requires complete KDEs for each CTE. This analysis helps
    identify if data quality is degrading over time, which may indicate:
    - Supplier format changes
    - Extraction model drift
    - Training data gaps

    Args:
        client: Neo4j client
        tenant_id: Optional tenant filter
        confidence_threshold: Threshold below which confidence is "low" (default 0.85)

    Returns:
        DataQualityReport with completeness metrics by event type
    """
    start_time = time.time()

    query = """
    MATCH (e:TraceEvent)
    WHERE ($tenant_id IS NULL OR e.tenant_id = $tenant_id)

    WITH e.type as event_type,
         count(e) as total,
         sum(CASE WHEN e.event_date IS NULL OR e.event_date = '' THEN 1 ELSE 0 END) as missing_date,
         sum(CASE WHEN NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) } THEN 1 ELSE 0 END) as missing_lot,
         sum(CASE WHEN e.confidence IS NOT NULL AND e.confidence < $threshold THEN 1 ELSE 0 END) as low_confidence,
         avg(CASE WHEN e.confidence IS NOT NULL THEN e.confidence ELSE 0 END) as avg_confidence

    RETURN
        event_type,
        total,
        missing_date,
        missing_lot,
        low_confidence,
        avg_confidence
    ORDER BY total DESC
    """

    metrics_list = []
    total_events = 0
    total_complete = 0

    async with client.session() as session:
        result = await session.run(query, tenant_id=tenant_id, threshold=confidence_threshold)

        async for record in result:
            event_type = record["event_type"] or "UNKNOWN"
            total = record["total"] or 0
            missing_date = record["missing_date"] or 0
            missing_lot = record["missing_lot"] or 0
            low_conf = record["low_confidence"] or 0
            avg_conf = record["avg_confidence"] or 0.0

            # Calculate rates
            missing_date_rate = missing_date / total if total > 0 else 0.0
            missing_lot_rate = missing_lot / total if total > 0 else 0.0
            low_conf_rate = low_conf / total if total > 0 else 0.0

            metrics_list.append(
                KDECompletenessMetrics(
                    event_type=event_type,
                    total_events=total,
                    missing_date_count=missing_date,
                    missing_date_rate=round(missing_date_rate, 4),
                    missing_lot_count=missing_lot,
                    missing_lot_rate=round(missing_lot_rate, 4),
                    low_confidence_count=low_conf,
                    low_confidence_rate=round(low_conf_rate, 4),
                    average_confidence=round(avg_conf, 4),
                )
            )

            total_events += total
            # Event is "complete" if it has date, lot linkage, and good confidence
            complete_count = total - max(missing_date, missing_lot, low_conf)
            total_complete += max(0, complete_count)

    # Calculate overall completeness
    overall_rate = total_complete / total_events if total_events > 0 else 1.0

    # Determine trend (simplified - would need historical data for real trend)
    # For now, based on overall rate thresholds
    if overall_rate >= 0.95:
        trend = "stable"
    elif overall_rate >= 0.85:
        trend = "stable"
    else:
        trend = "degrading"

    query_time = (time.time() - start_time) * 1000

    logger.info(
        "kde_completeness_analysis_completed",
        total_events=total_events,
        overall_completeness_rate=round(overall_rate, 4),
        event_types_analyzed=len(metrics_list),
        trend=trend,
        query_time_ms=round(query_time, 2),
    )

    return DataQualityReport(
        total_events=total_events,
        overall_completeness_rate=round(overall_rate, 4),
        metrics_by_type=metrics_list,
        trend_direction=trend,
        query_time_ms=round(query_time, 2),
    )
