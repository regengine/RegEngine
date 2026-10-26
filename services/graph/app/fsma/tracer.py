"""
FSMA 204 forward and backward tracing through the supply chain graph.

Supports FDA 24-hour recall requirements via Neo4j graph traversal
with Physics Engine time arrow enforcement.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from typing import Any, Dict, List

import structlog
from shared.fsma_rules import TimeArrowRule, TraceEvent as SharedTraceEvent

from ..neo4j_utils import Neo4jClient
from .types import TraceResult

logger = structlog.get_logger("fsma-utils")


# #2945: the deduplicated facilities/events/lots lists on ``TraceResult``
# discard which lot took part in which event, and where. Exporters cannot
# reconstruct that from three flat lists — the FDA trace CSV "compensated" by
# pairing every lot with every event and stamping the first GLN-bearing
# facility on each row, i.e. by fabricating the association. This query
# re-reads the (lot, event, facility) edges for the nodes the traversal
# already returned, so the association survives to the exporter.
# SEL-515: every capped trace query fetches ``TRACE_ROW_LIMIT + 1`` rows
# (``LIMIT 5001``). Only a query that returns more than the cap was really cut
# off: the extra row is dropped and the result is flagged ``truncated``
# (partial result, not a 413). Exactly ``TRACE_ROW_LIMIT`` rows is complete.
TRACE_ROW_LIMIT = 5000

_TRACE_ROWS_QUERY = """
MATCH (l:Lot)-[:UNDERWENT|PRODUCED|CONSUMED]-(e:TraceEvent)
WHERE l.tenant_id = $tenant_id
  AND e.tenant_id = $tenant_id
  AND l.tlc IN $tlcs
  AND e.event_id IN $event_ids
OPTIONAL MATCH (e)-[:OCCURRED_AT]->(f:Facility)
WHERE f.tenant_id = $tenant_id
RETURN properties(l) AS lot, properties(e) AS event, properties(f) AS facility
LIMIT 5001
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
                if len(rows) >= TRACE_ROW_LIMIT:
                    # SEL-515: the cap-plus-one row only signals truncation.
                    rows.append(None)  # type: ignore[arg-type]
                    break
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


def _path_row(record: Any) -> tuple[list, Any, Any] | None:
    """Read one path row, or None when the row is not usable.

    A non-mapping row is skipped. Missing properties count as an empty
    map so a null property bag cannot abort the trace.
    """
    if isinstance(record, (str, bytes, bytearray)):
        return None
    if getattr(record, "__getitem__", None) is None:
        return None
    try:
        labels = record["labels"]
        props = record["props"]
        hop = record["hop_count"]
    except (AttributeError, IndexError, KeyError, TypeError):
        return None
    if isinstance(labels, (list, tuple, set, frozenset)):
        label_list = list(labels)
    else:
        label_list = []
    if isinstance(props, Mapping) and not isinstance(props, (str, bytes, bytearray)):
        prop_map: Any = props
    else:
        prop_map = {}
    return label_list, prop_map, hop


def _quantity_parts(raw: Any) -> tuple[float, Any]:
    """Split a lot quantity into (amount added, value stored on the lot).

    Numbers and numeric strings add their value. Booleans, blanks,
    non-numeric text, NaN and infinities add nothing. Non-numeric text
    is stored as written so a later CSV export can still show it.
    """
    if isinstance(raw, bool) or raw is None:
        return 0.0, 0
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and not math.isfinite(raw):
            return 0.0, 0
        return float(raw), raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return 0.0, 0
        try:
            amount = float(text)
        except ValueError:
            return 0.0, raw
        if not math.isfinite(amount):
            return 0.0, raw
        return amount, raw
    return 0.0, raw


def _lot_identity(props: Mapping) -> tuple:
    tlc = props.get("tlc")
    if tlc:
        return ("tlc", str(tlc))
    return ("lot", id(props))


def _event_identity(props: Mapping) -> tuple:
    event_id = props.get("event_id")
    if event_id:
        return ("event", str(event_id))
    return ("event", id(props))


def _facility_identity(props: Mapping) -> tuple:
    gln = props.get("gln")
    if gln:
        return ("gln", str(gln))
    return ("place", props.get("name"), props.get("address"))


def _raise_node_tenant(direction: str, tlc: str, tenant_id: str, node_tenant: Any, labels: list) -> None:
    logger.error(
        f"trace_{direction}_tenant_invariant_violation",
        tlc=tlc,
        expected_tenant=tenant_id,
        node_tenant=node_tenant,
        labels=labels,
    )
    raise ValueError(
        f"trace_{direction} tenant invariant violation: returned node "
        f"tenant={node_tenant!r} does not match caller tenant={tenant_id!r}"
    )


def _take_path_node(
    record: Any,
    *,
    tenant_id: str,
    tlc: str,
    direction: str,
    include_risk_flag: bool,
    facilities: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    lots: List[Dict[str, Any]],
    seen_facilities: set,
    seen_events: set,
    seen_lots: set,
    running: Dict[str, Any],
) -> None:
    parsed = _path_row(record)
    if parsed is None:
        return
    labels, props, hop = parsed
    node_tenant = props.get("tenant_id")
    if node_tenant not in (None, "", tenant_id):
        _raise_node_tenant(direction, tlc, tenant_id, node_tenant, labels)
    # Keep the longest hop even when this node was already recorded.
    if isinstance(hop, (int, float)) and not isinstance(hop, bool):
        running["max_hops"] = max(running["max_hops"], hop)
    if "Facility" in labels:
        key = _facility_identity(props)
        if key in seen_facilities:
            return
        seen_facilities.add(key)
        facilities.append(
            {
                "gln": props.get("gln"),
                "name": props.get("name"),
                "address": props.get("address"),
                "facility_type": props.get("facility_type"),
            }
        )
    elif "TraceEvent" in labels:
        key = _event_identity(props)
        if key in seen_events:
            return
        seen_events.add(key)
        event = {
            "event_id": props.get("event_id"),
            "type": props.get("type"),
            "event_date": props.get("event_date"),
            "confidence": props.get("confidence"),
        }
        if include_risk_flag:
            event["risk_flag"] = props.get("risk_flag")
        events.append(event)
    elif "Lot" in labels:
        key = _lot_identity(props)
        if key in seen_lots:
            return
        seen_lots.add(key)
        amount, stored = _quantity_parts(props.get("quantity", 0))
        running["total_quantity"] += amount
        lots.append(
            {
                "tlc": props.get("tlc"),
                "product_description": props.get("product_description"),
                "quantity": stored,
                "unit_of_measure": props.get("unit_of_measure"),
            }
        )


def _take_follow_up_facility(
    record: Any,
    *,
    tenant_id: str,
    tlc: str,
    direction: str,
    facilities: List[Dict[str, Any]],
    seen_facilities: set,
) -> None:
    if isinstance(record, (str, bytes, bytearray)) or getattr(record, "__getitem__", None) is None:
        return
    try:
        fac = record["facility"]
    except (AttributeError, IndexError, KeyError, TypeError):
        return
    if not isinstance(fac, Mapping) or isinstance(fac, (str, bytes, bytearray)) or not fac:
        return
    # Tenant check before the seen-set skip, so a later cross-tenant copy
    # of a GLN we already stored still fails closed.
    fac_tenant = fac.get("tenant_id")
    if fac_tenant not in (None, "", tenant_id):
        logger.error(
            f"trace_{direction}_facility_invariant_violation",
            tlc=tlc,
            expected_tenant=tenant_id,
            facility_tenant=fac_tenant,
        )
        raise ValueError(f"trace_{direction} facility invariant violation: tenant={fac_tenant!r}")
    key = _facility_identity(fac)
    if key in seen_facilities:
        return
    seen_facilities.add(key)
    facilities.append(
        {
            "gln": fac.get("gln"),
            "name": fac.get("name"),
            "address": fac.get("address"),
            "facility_type": fac.get("facility_type"),
        }
    )


def _truncation(path_records: int, trace_rows: List[Dict[str, Any]], *, direction: str, tlc: str) -> Dict[str, Any]:
    """SEL-515: flag a trace whose capped queries hit ``TRACE_ROW_LIMIT``."""
    truncated = path_records > TRACE_ROW_LIMIT or len(trace_rows or []) > TRACE_ROW_LIMIT
    if truncated:
        logger.warning(
            "trace_truncated_at_cap",
            direction=direction,
            tlc=tlc,
            path_records=path_records,
            trace_rows=len(trace_rows or []),
            limit=TRACE_ROW_LIMIT,
        )
    return {"truncated": truncated, "truncation_limit": TRACE_ROW_LIMIT if truncated else None}


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
    # - LIMIT 5001 (cap plus one, SEL-515) caps result set to prevent runaway expansion on
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

    UNWIND path_nodes as node
    WITH DISTINCT node, path
    RETURN
        labels(node) as labels,
        properties(node) as props,
        length(path) as hop_count
    ORDER BY hop_count
    LIMIT 5001
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
    UNWIND path_nodes as node
    WITH DISTINCT node, path
    RETURN
        labels(node) as labels,
        properties(node) as props,
        length(path) as hop_count
    ORDER BY hop_count
    LIMIT 5001
    """
    )

    facilities = []
    events = []
    lots = []
    seen_facilities = set()
    seen_events = set()
    seen_lots = set()
    running = {"max_hops": 0, "total_quantity": 0.0}
    path_records = 0

    # Use time-filtered query if enforcing time arrow
    active_query = query if enforce_time_arrow else query_no_time_filter

    async with client.session() as session:
        result = await session.run(active_query, tlc=tlc, tenant_id=tenant_id)

        async for record in result:
            path_records += 1
            if path_records > TRACE_ROW_LIMIT:
                # SEL-515: the cap-plus-one row only signals truncation.
                break
            _take_path_node(
                record,
                tenant_id=tenant_id,
                tlc=tlc,
                direction="forward",
                include_risk_flag=True,
                facilities=facilities,
                events=events,
                lots=lots,
                seen_facilities=seen_facilities,
                seen_events=seen_events,
                seen_lots=seen_lots,
                running=running,
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
            _take_follow_up_facility(
                record,
                tenant_id=tenant_id,
                tlc=tlc,
                direction="forward",
                facilities=facilities,
                seen_facilities=seen_facilities,
            )

    max_hops = running["max_hops"]
    total_quantity = running["total_quantity"]

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
    truncation = _truncation(path_records, trace_rows, direction="forward", tlc=tlc)
    trace_rows = trace_rows[:TRACE_ROW_LIMIT]

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
        **truncation,
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
    # - LIMIT 5001 (cap plus one, SEL-515) provides a safety net on dense graphs
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
    UNWIND path_nodes as node
    WITH DISTINCT node, path
    RETURN
        labels(node) as labels,
        properties(node) as props,
        length(path) as hop_count
    ORDER BY hop_count
    LIMIT 5001
    """
    )

    facilities = []
    events = []
    lots = []
    seen_facilities = set()
    seen_events = set()
    seen_lots = set()
    running = {"max_hops": 0, "total_quantity": 0.0}
    path_records = 0

    async with client.session() as session:
        result = await session.run(query, tlc=tlc, tenant_id=tenant_id)

        async for record in result:
            path_records += 1
            if path_records > TRACE_ROW_LIMIT:
                # SEL-515: the cap-plus-one row only signals truncation.
                break
            _take_path_node(
                record,
                tenant_id=tenant_id,
                tlc=tlc,
                direction="backward",
                include_risk_flag=False,
                facilities=facilities,
                events=events,
                lots=lots,
                seen_facilities=seen_facilities,
                seen_events=seen_events,
                seen_lots=seen_lots,
                running=running,
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
            _take_follow_up_facility(
                record,
                tenant_id=tenant_id,
                tlc=tlc,
                direction="backward",
                facilities=facilities,
                seen_facilities=seen_facilities,
            )

    max_hops = running["max_hops"]
    total_quantity = running["total_quantity"]

    # #2945: preserve the lot<->event<->facility association for exporters.
    trace_rows = await _collect_trace_rows(client, tlc, tenant_id, lots, events)
    truncation = _truncation(path_records, trace_rows, direction="backward", tlc=tlc)
    trace_rows = trace_rows[:TRACE_ROW_LIMIT]

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
        **truncation,
    )
