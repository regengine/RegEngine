"""
Sandbox in-memory lot trace-back / trace-forward (BFS).

Moved from sandbox_router.py.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request

from .csv_parser import _parse_csv_to_events
from .models import (
    SandboxTraceRequest,
    TraceEdge,
    TraceGraphResponse,
    TraceNode,
)
from .rate_limiting import _check_sandbox_rate_limit


def _trace_in_memory(
    raw_events: List[Dict[str, Any]],
    seed_tlc: str,
    direction: str = "both",
    max_depth: int = 10,
) -> TraceGraphResponse:
    """BFS trace through CSV events following lot code linkages.

    Links are formed by:
    1. Same TLC across events (harvest -> ship -> receive chain)
    2. input_traceability_lot_codes on transformation events (LOT-A,LOT-B -> LOT-MEGA)
    3. Facility handoffs: shipping.ship_to == receiving.location within same TLC

    Returns a graph of nodes (events) and edges (linkages).
    """
    max_depth = min(max_depth, 20)

    # Index events by TLC for fast lookup
    by_tlc: Dict[str, List[int]] = defaultdict(list)
    # Index: transformation events that consume a given input TLC
    consumes_tlc: Dict[str, List[int]] = defaultdict(list)
    # Index: transformation events that produce a given output TLC
    produces_tlc: Dict[str, List[int]] = defaultdict(list)

    for i, ev in enumerate(raw_events):
        tlc = (ev.get("traceability_lot_code") or "").strip()
        if tlc:
            by_tlc[tlc].append(i)

        cte = (ev.get("cte_type") or "").strip().lower()
        if cte == "transformation":
            # This event produces its own TLC
            if tlc:
                produces_tlc[tlc].append(i)
            # It consumes input TLCs
            kdes = ev.get("kdes", {})
            input_tlcs = kdes.get("input_traceability_lot_codes", [])
            if isinstance(input_tlcs, str):
                input_tlcs = [t.strip() for t in input_tlcs.split(",") if t.strip()]
            for input_tlc in input_tlcs:
                consumes_tlc[input_tlc].append(i)

    # BFS
    visited: set[int] = set()
    nodes: List[TraceNode] = []
    edges: List[TraceEdge] = []
    lots_touched: set[str] = set()
    facilities: set[str] = set()
    max_depth_reached = 0

    # Queue entries: (event_index, depth, came_from_index_or_None, link_type)
    queue: deque[tuple[int, int, Optional[int], str]] = deque()

    # Seed: all events with the target TLC
    seed_indices = by_tlc.get(seed_tlc.strip(), [])
    if not seed_indices:
        return TraceGraphResponse(
            seed_tlc=seed_tlc,
            direction=direction,
            nodes=[],
            edges=[],
            lots_touched=[],
            facilities=[],
            max_depth=0,
        )

    for idx in seed_indices:
        queue.append((idx, 0, None, "seed"))

    while queue:
        evt_idx, depth, parent_idx, link_type = queue.popleft()

        if evt_idx in visited:
            # Still add edge if parent exists
            if parent_idx is not None and parent_idx != evt_idx:
                ev = raw_events[evt_idx]
                tlc = (ev.get("traceability_lot_code") or "").strip()
                edge_exists = any(
                    e.from_event_index == parent_idx and e.to_event_index == evt_idx
                    for e in edges
                )
                if not edge_exists:
                    edges.append(TraceEdge(
                        from_event_index=parent_idx,
                        to_event_index=evt_idx,
                        link_type=link_type,
                        lot_code=tlc,
                    ))
            continue

        visited.add(evt_idx)
        ev = raw_events[evt_idx]
        tlc = (ev.get("traceability_lot_code") or "").strip()
        cte = (ev.get("cte_type") or "").strip().lower()
        kdes = ev.get("kdes", {})
        loc = ev.get("location_name") or ""
        fac_from = kdes.get("ship_from_location") or loc
        fac_to = kdes.get("ship_to_location") or kdes.get("receiving_location") or ""

        qty = ev.get("quantity")
        if isinstance(qty, str):
            try:
                qty = float(qty)
            except ValueError:
                qty = None

        node = TraceNode(
            event_index=evt_idx,
            cte_type=cte,
            traceability_lot_code=tlc,
            product_description=ev.get("product_description", ""),
            quantity=qty,
            unit_of_measure=ev.get("unit_of_measure", ""),
            timestamp=ev.get("timestamp", ""),
            location_name=loc,
            facility_from=fac_from,
            facility_to=fac_to,
            depth=depth,
        )
        nodes.append(node)
        lots_touched.add(tlc)
        if loc:
            facilities.add(loc)
        if fac_from:
            facilities.add(fac_from)
        if fac_to:
            facilities.add(fac_to)
        max_depth_reached = max(max_depth_reached, depth)

        # Add edge from parent
        if parent_idx is not None and parent_idx != evt_idx:
            edges.append(TraceEdge(
                from_event_index=parent_idx,
                to_event_index=evt_idx,
                link_type=link_type,
                lot_code=tlc,
            ))

        if depth >= max_depth:
            continue

        # ---- Expand neighbors ----

        # A. Same TLC — other events in the same lot group
        if direction in ("both", "downstream", "upstream"):
            for neighbor_idx in by_tlc.get(tlc, []):
                if neighbor_idx not in visited:
                    queue.append((neighbor_idx, depth + 1, evt_idx, "same_lot"))

        # B. Downstream: if this event's TLC is consumed by a transformation
        if direction in ("both", "downstream"):
            for trans_idx in consumes_tlc.get(tlc, []):
                if trans_idx not in visited:
                    queue.append((trans_idx, depth + 1, evt_idx, "transformation_input"))
                # Also follow the output TLC of that transformation
                trans_ev = raw_events[trans_idx]
                output_tlc = (trans_ev.get("traceability_lot_code") or "").strip()
                if output_tlc and output_tlc != tlc:
                    for out_idx in by_tlc.get(output_tlc, []):
                        if out_idx not in visited:
                            queue.append((out_idx, depth + 2, trans_idx, "transformation_output"))

        # C. Upstream: if this is a transformation, follow input TLCs backward
        if direction in ("both", "upstream"):
            if cte == "transformation":
                input_tlcs = kdes.get("input_traceability_lot_codes", [])
                if isinstance(input_tlcs, str):
                    input_tlcs = [t.strip() for t in input_tlcs.split(",") if t.strip()]
                for input_tlc in input_tlcs:
                    for inp_idx in by_tlc.get(input_tlc, []):
                        if inp_idx not in visited:
                            queue.append((inp_idx, depth + 1, evt_idx, "transformation_input"))

            # Also: if this TLC is produced by a transformation, go to its inputs
            for prod_idx in produces_tlc.get(tlc, []):
                if prod_idx != evt_idx and prod_idx not in visited:
                    queue.append((prod_idx, depth + 1, evt_idx, "transformation_output"))

    total_qty = 0.0
    for n in nodes:
        if n.quantity:
            total_qty += n.quantity

    return TraceGraphResponse(
        seed_tlc=seed_tlc,
        direction=direction,
        nodes=nodes,
        edges=edges,
        lots_touched=sorted(lots_touched),
        facilities=sorted(facilities),
        max_depth=max_depth_reached,
        total_quantity=total_qty,
    )


async def sandbox_trace(payload: SandboxTraceRequest, request: Request) -> TraceGraphResponse:
    """Stateless in-memory lot tracing for the sandbox."""
    client_ip = request.client.host if request.client else "unknown"
    _check_sandbox_rate_limit(client_ip)

    if not payload.csv.strip():
        raise HTTPException(status_code=400, detail="CSV text is required")
    if not payload.tlc.strip():
        raise HTTPException(status_code=400, detail="TLC (traceability lot code) is required")

    try:
        raw_events = _parse_csv_to_events(payload.csv)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parsing error: {str(e)}")

    if not raw_events:
        raise HTTPException(status_code=400, detail="No valid events found in CSV")

    if len(raw_events) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 events per sandbox request")

    direction = payload.direction.lower()
    if direction not in ("upstream", "downstream", "both"):
        direction = "both"

    return _trace_in_memory(
        raw_events=raw_events,
        seed_tlc=payload.tlc.strip(),
        direction=direction,
        max_depth=payload.max_depth,
    )
