"""
FSMA 204 forward and backward tracing through the supply chain graph.

Supports FDA 24-hour recall requirements via Neo4j graph traversal
with Physics Engine time arrow enforcement.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import structlog
from shared.fsma_rules import TimeArrowRule, TraceEvent as SharedTraceEvent

from ..neo4j_utils import Neo4jClient
from .types import TraceResult

logger = structlog.get_logger("fsma-utils")


#: Hard ceiling on how many variable-length paths each trace query may
#: expand before unwinding nodes. The trailing ``LIMIT 5000`` only trims
#: the final row set, so without this earlier cap a dense graph can
#: explode into far more paths than the limit ever trims.
MAX_TRACE_PATHS = 1000


# #2945: the deduplicated facilities/events/lots lists on ``TraceResult``
# discard which lot took part in which event, and where. Exporters cannot
# reconstruct that from three flat lists — the FDA trace CSV "compensated" by
# pairing every lot with every event and stamping the first GLN-bearing
# facility on each row, i.e. by fabricating the association. This query
# re-reads the (lot, event, facility) edges for the nodes the traversal
# already returned, so the association survives to the exporter.
_TRACE_ROWS_QUERY = """
MATCH (l:Lot)-[:UNDERWENT|PRODUCED|CONSUMED]-(e:TraceEvent)
WHERE l.tenant_id = $tenant_id
  AND e.tenant_id = $tenant_id
  AND l.tlc IN $tlcs
  AND e.event_id IN $event_ids
OPTIONAL MATCH (e)-[:OCCURRED_AT]->(f:Facility)
WHERE f.tenant_id = $tenant_id
RETURN properties(l) AS lot, properties(e) AS event, properties(f) AS facility
LIMIT 5000
"""


async def _collect_trace_rows(
    client: Neo4jClient,
    tlc: str,
    tenant_id: str,
    lots: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return the (lot, event, facility) associations behind a trace (#2945).

    Best-effort enrichment: the deduplicated node lists remain the contract, so
    a failure here degrades the CSV to "association unknown" (blank cells)
    rather than failing the whole trace or, worse, licensing a guess.
    """
    tlcs = sorted({lot.get("tlc") for lot in lots if lot.get("tlc")})
    event_ids = sorted({event.get("event_id") for event in events if event.get("event_id")})
    if not tlcs or not event_ids:
        return []

    rows: List[Dict[str, Any]] = []
    try:
        async with client.session() as session:
            result = await session.run(
                _TRACE_ROWS_QUERY,
                tenant_id=tenant_id,
                tlcs=tlcs,
                event_ids=event_ids,
            )
            async for record in result:
                lot_props = record["lot"] or {}
                event_props = record["event"] or {}
                facility_props = record["facility"] or None
                # SECURITY (#1256): mirror the per-node tenant invariant used
                # on the traversal itself rather than trusting the predicate.
                for props in (lot_props, event_props, facility_props or {}):
                    node_tenant = props.get("tenant_id")
                    if node_tenant not in (None, "", tenant_id):
                        raise ValueError(f"trace association tenant invariant violation: tenant={node_tenant!r}")
                rows.append(
                    {
                        "lot": {
                            "tlc": lot_props.get("tlc"),
                            "product_description": lot_props.get("product_description"),
                            "quantity": lot_props.get("quantity"),
                            "unit_of_measure": lot_props.get("unit_of_measure"),
                        },
                        "event": {
                            "event_id": event_props.get("event_id"),
                            "type": event_props.get("type"),
                            "event_date": event_props.get("event_date"),
                            "event_time": event_props.get("event_time"),
                            "confidence": event_props.get("confidence"),
                        },
                        "facility": (
                            {
                                "gln": facility_props.get("gln"),
                                "name": facility_props.get("name"),
                                "address": facility_props.get("address"),
                            }
                            if facility_props
                            else None
                        ),
                    }
                )
    except ValueError:
        raise
    except Exception as err:  # pragma: no cover - defensive
        logger.warning("trace_rows_collection_failed", tlc=tlc, error=str(err))
        return []

    return rows


async def trace_forward(
    client: Neo4jClient,
    tlc: str,
    max_depth: int = 10,
    tenant_id: str = "",
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
        tenant_id: Tenant UUID (required, non-empty)
        enforce_time_arrow: If True, validates temporal ordering (default True)

    Returns:
        TraceResult with all downstream facilities, events, lots, and any time violations

    Raises:
        ValueError: if ``tenant_id`` is falsy/empty. Variable-length traversal
            with a null tenant would cross tenant boundaries via shared
            facilities/events. Fail closed (#2540).
    """
    # #2540 — fail closed on a missing tenant rather than the old
    # `$tenant_id IS NULL OR ...` shim, which traversed every tenant's graph.
    if not tenant_id:
        raise ValueError("trace_forward requires a non-empty tenant_id; null-tenant traces are not supported (#2540)")
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
    #
    # SECURITY (#1256): variable-length paths must enforce tenant scope
    # on *every* node in the path, not just the start node. Without the
    # `ALL(n IN nodes(path) WHERE n.tenant_id = $tenant_id)` predicate,
    # the traversal can cross tenant boundaries via shared facilities or
    # shared events and leak data from other tenants. This is enforced
    # whenever a non-null tenant_id is provided.
    query = (
        """
    MATCH path = (start:Lot {tlc: $tlc})-[:UNDERWENT|PRODUCED*1.."""
        + str(rel_depth)
        + """]->(end)
    USING INDEX start:Lot(tlc)
    WHERE start.tenant_id = $tenant_id
      AND ALL(
              n IN nodes(path) WHERE n.tenant_id = $tenant_id
          )
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

    // Cap expansion server-side: bound the paths unwound into nodes so
    // the trailing row LIMIT is not the only guard on dense graphs.
    WITH path, path_nodes LIMIT $path_cap
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
    # Same tenant-path guard (#1256) applies.
    query_no_time_filter = (
        """
    MATCH path = (start:Lot {tlc: $tlc})-[:UNDERWENT|PRODUCED*1.."""
        + str(rel_depth)
        + """]->(end)
    USING INDEX start:Lot(tlc)
    WHERE start.tenant_id = $tenant_id
      AND ALL(
              n IN nodes(path) WHERE n.tenant_id = $tenant_id
          )
    WITH path, nodes(path) as path_nodes
    WITH path, path_nodes LIMIT $path_cap
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
        result = await session.run(active_query, tlc=tlc, tenant_id=tenant_id, path_cap=MAX_TRACE_PATHS)

        async for record in result:
            labels = record["labels"]
            props = record["props"]
            hop = record["hop_count"]
            max_hops = max(max_hops, hop)

            # SECURITY (#1256): invariant check — every returned node must
            # belong to the caller's tenant. If Cypher somehow returned a
            # cross-tenant node, raise rather than leak data. This mirrors
            # the predicate in the query and guards against future edits.
            # #2540: tenant_id is guaranteed non-empty above, so the
            # invariant always runs (no `is not None` gate).
            node_tenant = props.get("tenant_id")
            if node_tenant not in (None, "", tenant_id):
                logger.error(
                    "trace_forward_tenant_invariant_violation",
                    tlc=tlc,
                    expected_tenant=tenant_id,
                    node_tenant=node_tenant,
                    labels=labels,
                )
                raise ValueError(
                    f"trace_forward tenant invariant violation: returned node "
                    f"tenant={node_tenant!r} does not match caller tenant={tenant_id!r}"
                )

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

    # Also get directly connected facilities via SHIPPED_TO.
    # #1256: enforce tenant on BOTH the Lot and the Event to avoid
    # returning facilities reached via cross-tenant events.
    facility_query = """
    MATCH (l:Lot {tlc: $tlc})-[:UNDERWENT]->(e:TraceEvent)-[:SHIPPED_TO]->(f:Facility)
    WHERE l.tenant_id = $tenant_id
      AND e.tenant_id = $tenant_id
      AND f.tenant_id = $tenant_id
    RETURN DISTINCT properties(f) as facility
    """

    async with client.session() as session:
        result = await session.run(facility_query, tlc=tlc, tenant_id=tenant_id)
        async for record in result:
            fac = record["facility"]
            # SECURITY (#1256): invariant check for facility-only results.
            # #2540: tenant_id is non-empty, so the invariant always runs.
            fac_tenant = (fac or {}).get("tenant_id")
            if fac and fac_tenant not in (None, "", tenant_id):
                logger.error(
                    "trace_forward_facility_invariant_violation",
                    tlc=tlc,
                    expected_tenant=tenant_id,
                    facility_tenant=fac_tenant,
                )
                raise ValueError(f"trace_forward facility invariant violation: tenant={fac_tenant!r}")
            if fac and fac not in [f for f in facilities if f.get("gln") == fac.get("gln")]:
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
                    parseable_events.append(
                        SharedTraceEvent(
                            event_id=e["event_id"],
                            tlc=tlc,
                            event_date=e["event_date"],
                            event_type=e.get("type"),
                        )
                    )
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
                    time_violations.append(
                        {
                            "violation_type": "TIME_ARROW",
                            "description": v.description,
                            "prev_event_id": v.event_ids[0] if v.event_ids else None,
                            "curr_event_id": v.event_ids[1] if len(v.event_ids) > 1 else None,
                            "prev_event_date": details.get("upstream_date"),
                            "curr_event_date": details.get("downstream_date"),
                        }
                    )
                    # The *downstream* event is the one that violates causality
                    if len(v.event_ids) > 1:
                        violating_ids.add(v.event_ids[1])

                # Strip violating events from the result set so callers
                # never see causally-impossible paths.
                if violating_ids:
                    events = [e for e in events if e.get("event_id") not in violating_ids]
                    logger.info(
                        "time_arrow_events_stripped",
                        tlc=tlc,
                        stripped_count=len(violating_ids),
                        stripped_ids=list(violating_ids),
                    )

    # Collect risk flags from events
    risk_flags = list(set(e.get("risk_flag") for e in events if e.get("risk_flag")))

    # #2945: preserve the lot<->event<->facility association for exporters.
    trace_rows = await _collect_trace_rows(client, tlc, tenant_id, lots, events)

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
        trace_rows=trace_rows or None,
    )


async def trace_backward(
    client: Neo4jClient,
    tlc: str,
    max_depth: int = 10,
    tenant_id: str = "",
) -> TraceResult:
    """
    Trace backward from a lot to find all source materials and suppliers.

    Given a finished good Lot ID, find all raw material Lots.

    Args:
        client: Neo4j client
        tlc: Traceability Lot Code to trace from
        max_depth: Maximum hops in the trace (default 10)
        tenant_id: Tenant UUID (required, non-empty)

    Returns:
        TraceResult with all upstream facilities, events, and lots

    Raises:
        ValueError: if ``tenant_id`` is falsy/empty. Variable-length traversal
            with a null tenant would cross tenant boundaries via shared
            facilities/events. Fail closed (#2540).
    """
    # #2540 — fail closed on a missing tenant rather than the old
    # `$tenant_id IS NULL OR ...` shim, which traversed every tenant's graph.
    if not tenant_id:
        raise ValueError("trace_backward requires a non-empty tenant_id; null-tenant traces are not supported (#2540)")
    if not isinstance(max_depth, int) or max_depth < 1:
        raise ValueError(f"max_depth must be a positive integer, got {max_depth!r}")

    start_time = time.time()

    # Cap variable-length expansion (same rationale as trace_forward)
    rel_depth = min(max_depth * 2, 20)

    # Optimized Cypher query to trace backward through transformations.
    # Path: Lot <-[:PRODUCED]- TraceEvent -[:CONSUMED]-> Lot, repeated.
    #
    # #2940 — DIRECTION. ``FSMARelationships`` persists *both* transformation
    # edges pointing event -> lot:
    #     EVENT_PRODUCED_LOT:  MERGE (e)-[:PRODUCED]->(l)
    #     EVENT_CONSUMED_LOT:  MERGE (e)-[:CONSUMED]->(l)
    # so a transformation's *inputs* hang off the event's OUTGOING ``CONSUMED``
    # edge. This query used to walk incoming edges only
    # (``<-[:PRODUCED|CONSUMED*1..N]-``): hop 1 reached the producing event and
    # hop 2 would have needed an edge pointing *into* a TraceEvent, which no
    # writer ever creates. The traversal could not extend past length 1 for any
    # ``max_depth``, so "one step back" returned no source lot at all.
    #
    # A single directed variable-length pattern cannot express "incoming
    # PRODUCED, then outgoing CONSUMED" — every hop shares one direction. So
    # the pattern is undirected and each hop's direction is asserted
    # explicitly: for PRODUCED the relationship must point *at* the node we
    # arrived on (``endNode(r) = nodes(path)[idx]``), for CONSUMED it must
    # point *away* from it. That is not merely cosmetic — an undirected
    # traversal without this predicate walks the incoming ``CONSUMED`` edge of
    # a *downstream* transformation and reports the products this lot was made
    # into as if they were its sources.
    #
    # Because no writer creates an incoming PRODUCED on an event or an
    # outgoing CONSUMED on a lot, the predicate also makes the traversal
    # self-alternating (Lot -> Event -> Lot -> ...) with no extra check.
    #
    # Performance notes:
    # - USING INDEX hint anchors on indexed Lot(tlc) start node
    # - Capped rel_depth prevents combinatorial blowup
    # - LIMIT 5000 provides a safety net on dense graphs
    #
    # SECURITY (#1256): enforce tenant_id on every node in the path, not
    # just the start node, so transitive traversals cannot cross tenant
    # boundaries via shared events or facilities.
    query = (
        """
    MATCH path = (start:Lot {tlc: $tlc})-[:PRODUCED|CONSUMED*1.."""
        + str(rel_depth)
        + """]-(source)
    USING INDEX start:Lot(tlc)
    WHERE start.tenant_id = $tenant_id
      AND ALL(
              n IN nodes(path) WHERE n.tenant_id = $tenant_id
          )
      AND ALL(
              idx IN range(0, size(relationships(path)) - 1)
              WHERE CASE type(relationships(path)[idx])
                        WHEN 'PRODUCED' THEN endNode(relationships(path)[idx]) = nodes(path)[idx]
                        ELSE startNode(relationships(path)[idx]) = nodes(path)[idx]
                    END
          )
    WITH path, nodes(path) as path_nodes
    WITH path, path_nodes LIMIT $path_cap
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
        result = await session.run(query, tlc=tlc, tenant_id=tenant_id, path_cap=MAX_TRACE_PATHS)

        async for record in result:
            labels = record["labels"]
            props = record["props"]
            hop = record["hop_count"]
            max_hops = max(max_hops, hop)

            # SECURITY (#1256): invariant check — every returned node must
            # belong to the caller's tenant. If the Cypher ALL(...) guard
            # was bypassed, fail loud rather than silently leak data.
            # #2540: tenant_id is guaranteed non-empty above, so the
            # invariant always runs (no `is not None` gate).
            node_tenant = props.get("tenant_id")
            if node_tenant not in (None, "", tenant_id):
                logger.error(
                    "trace_backward_tenant_invariant_violation",
                    tlc=tlc,
                    expected_tenant=tenant_id,
                    node_tenant=node_tenant,
                    labels=labels,
                )
                raise ValueError(
                    f"trace_backward tenant invariant violation: returned node "
                    f"tenant={node_tenant!r} does not match caller tenant={tenant_id!r}"
                )

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

    # Also get source facilities via SHIPPED relationship.
    #
    # #2940 — this used to match ``(e:TraceEvent)-[:INCLUDED]->(l:Lot)``.
    # Nothing in the repository writes an ``:INCLUDED`` relationship (no
    # MERGE, no migration, no fixture), so the query returned zero rows
    # unconditionally and ``facilities`` came back empty no matter what the
    # graph held. The real inbound-shipment shape is the event that produced
    # or consumed this lot, reached from the facility that shipped it
    # (``FSMARelationships.SHIPPED_FROM`` writes ``(f)-[:SHIPPED]->(e)``).
    #
    # #1256: enforce tenant on Facility, Event, AND Lot — all three nodes
    # on the path must belong to the caller so we never return a source
    # facility reached via a cross-tenant event.
    facility_query = """
    MATCH (f:Facility)-[:SHIPPED]->(e:TraceEvent)-[:PRODUCED|CONSUMED]->(l:Lot {tlc: $tlc})
    WHERE l.tenant_id = $tenant_id
      AND e.tenant_id = $tenant_id
      AND f.tenant_id = $tenant_id
    RETURN DISTINCT properties(f) as facility
    """

    async with client.session() as session:
        result = await session.run(facility_query, tlc=tlc, tenant_id=tenant_id)
        async for record in result:
            fac = record["facility"]
            # #2540: tenant_id is non-empty, so the invariant always runs.
            fac_tenant = (fac or {}).get("tenant_id")
            if fac and fac_tenant not in (None, "", tenant_id):
                logger.error(
                    "trace_backward_facility_invariant_violation",
                    tlc=tlc,
                    expected_tenant=tenant_id,
                    facility_tenant=fac_tenant,
                )
                raise ValueError(f"trace_backward facility invariant violation: tenant={fac_tenant!r}")
            if fac and fac not in [f for f in facilities if f.get("gln") == fac.get("gln")]:
                facilities.append(
                    {
                        "gln": fac.get("gln"),
                        "name": fac.get("name"),
                        "address": fac.get("address"),
                        "facility_type": fac.get("facility_type"),
                    }
                )

    # #2945: preserve the lot<->event<->facility association for exporters.
    trace_rows = await _collect_trace_rows(client, tlc, tenant_id, lots, events)

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
        trace_rows=trace_rows or None,
    )
