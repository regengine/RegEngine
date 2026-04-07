"""PostgreSQL recursive CTE lot tracing — replaces Neo4j graph traversal.

Provides forward and backward traceability through the supply chain using
fsma.traceability_events. Uses recursive CTEs instead of Neo4j Cypher queries.

Scaling trigger: If lot tracing exceeds 3 hops or >100K records per tenant,
migrate to Neo4j for graph-native traversal.

Usage:
    from app.workers.lot_tracing import trace_forward, trace_backward
    result = trace_forward(db, tlc="LOT-001", tenant_id="...", max_depth=5)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger("lot-tracing")


@dataclass
class TraceResult:
    """Result of a forward or backward lot trace."""
    lots: List[Dict[str, Any]] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    facilities: List[Dict[str, Any]] = field(default_factory=list)
    max_hops: int = 0
    total_quantity: float = 0.0
    duration_ms: float = 0.0
    time_violations: List[Dict[str, Any]] = field(default_factory=list)


def trace_forward(
    db: Session,
    tlc: str,
    max_depth: int = 10,
    tenant_id: Optional[str] = None,
    enforce_time_arrow: bool = True,
) -> TraceResult:
    """Trace forward from a lot to find all downstream products and customers.

    Given a raw material Lot ID, follows the supply chain forward:
      shipping -> receiving -> transformation -> shipping -> ...

    The recursive CTE follows the chain:
      Lot A shipped -> Lot B received -> Lot B transformed -> Lot C shipped -> ...

    Links are formed by matching traceability_lot_code across events where:
      - A shipping event's lot becomes a receiving event's lot at the next facility
      - A transformation event produces new lots from input lots

    Args:
        db: SQLAlchemy session
        tlc: Traceability Lot Code to trace from
        max_depth: Maximum hops (default 10, capped at 20)
        tenant_id: Required tenant filter for RLS
        enforce_time_arrow: Validate temporal ordering (default True)

    Returns:
        TraceResult with downstream facilities, events, and lots
    """
    import time as _time
    start = _time.time()
    max_depth = min(max_depth, 20)

    time_arrow_clause = ""
    if enforce_time_arrow:
        time_arrow_clause = "AND e2.event_timestamp >= e1.event_timestamp"

    query = text(f"""
        WITH RECURSIVE trace AS (
            -- Anchor: find the starting lot's events
            SELECT
                e.event_id,
                e.traceability_lot_code AS tlc,
                e.event_type,
                e.event_timestamp,
                e.from_entity_reference,
                e.to_entity_reference,
                e.from_facility_reference,
                e.to_facility_reference,
                e.product_reference,
                e.quantity,
                e.unit_of_measure,
                e.confidence_score,
                1 AS depth
            FROM fsma.traceability_events e
            WHERE e.traceability_lot_code = :tlc
              AND e.tenant_id = :tenant_id::uuid
              AND e.status = 'active'

            UNION ALL

            -- Recursive step: follow the chain forward
            -- A lot that was received or transformed links to its next shipment
            SELECT
                e2.event_id,
                e2.traceability_lot_code AS tlc,
                e2.event_type,
                e2.event_timestamp,
                e2.from_entity_reference,
                e2.to_entity_reference,
                e2.from_facility_reference,
                e2.to_facility_reference,
                e2.product_reference,
                e2.quantity,
                e2.unit_of_measure,
                e2.confidence_score,
                t.depth + 1 AS depth
            FROM trace t
            JOIN fsma.traceability_events e2
              ON e2.tenant_id = :tenant_id::uuid
             AND e2.status = 'active'
             AND e2.event_id != t.event_id
             AND (
                -- Same lot, next event in chain (e.g., ship -> receive)
                (e2.traceability_lot_code = t.tlc
                 AND e2.from_facility_reference = t.to_facility_reference)
                OR
                -- Transformation: input lot -> output lot at same facility
                (e2.event_type = 'transformation'
                 AND e2.from_facility_reference = t.to_facility_reference
                 AND e2.traceability_lot_code != t.tlc)
             )
             {time_arrow_clause}
            WHERE t.depth < :max_depth
        )
        SELECT DISTINCT ON (event_id)
            event_id, tlc, event_type, event_timestamp,
            from_entity_reference, to_entity_reference,
            from_facility_reference, to_facility_reference,
            product_reference, quantity, unit_of_measure,
            confidence_score, depth
        FROM trace
        ORDER BY event_id, depth
        LIMIT 5000
    """)

    if not tenant_id:
        raise ValueError("tenant_id is required for RLS-filtered lot tracing")

    rows = db.execute(query, {
        "tlc": tlc,
        "tenant_id": tenant_id,
        "max_depth": max_depth,
    }).fetchall()

    return _build_result(rows, _time.time() - start)


def trace_backward(
    db: Session,
    tlc: str,
    max_depth: int = 10,
    tenant_id: Optional[str] = None,
) -> TraceResult:
    """Trace backward from a lot to find all source materials and suppliers.

    Given a finished good Lot ID, follows the supply chain backward:
      receiving <- shipping <- transformation <- receiving <- ...

    Args:
        db: SQLAlchemy session
        tlc: Traceability Lot Code to trace from
        max_depth: Maximum hops (default 10, capped at 20)
        tenant_id: Required tenant filter for RLS

    Returns:
        TraceResult with upstream facilities, events, and lots
    """
    import time as _time
    start = _time.time()
    max_depth = min(max_depth, 20)

    query = text("""
        WITH RECURSIVE trace AS (
            -- Anchor: find the starting lot's events
            SELECT
                e.event_id,
                e.traceability_lot_code AS tlc,
                e.event_type,
                e.event_timestamp,
                e.from_entity_reference,
                e.to_entity_reference,
                e.from_facility_reference,
                e.to_facility_reference,
                e.product_reference,
                e.quantity,
                e.unit_of_measure,
                e.confidence_score,
                1 AS depth
            FROM fsma.traceability_events e
            WHERE e.traceability_lot_code = :tlc
              AND e.tenant_id = :tenant_id::uuid
              AND e.status = 'active'

            UNION ALL

            -- Recursive step: follow the chain backward
            SELECT
                e2.event_id,
                e2.traceability_lot_code AS tlc,
                e2.event_type,
                e2.event_timestamp,
                e2.from_entity_reference,
                e2.to_entity_reference,
                e2.from_facility_reference,
                e2.to_facility_reference,
                e2.product_reference,
                e2.quantity,
                e2.unit_of_measure,
                e2.confidence_score,
                t.depth + 1 AS depth
            FROM trace t
            JOIN fsma.traceability_events e2
              ON e2.tenant_id = :tenant_id::uuid
             AND e2.status = 'active'
             AND e2.event_id != t.event_id
             AND (
                -- Same lot, previous event in chain (e.g., receive <- ship)
                (e2.traceability_lot_code = t.tlc
                 AND e2.to_facility_reference = t.from_facility_reference)
                OR
                -- Transformation: output lot <- input lot at same facility
                (t.event_type = 'transformation'
                 AND e2.to_facility_reference = t.from_facility_reference
                 AND e2.traceability_lot_code != t.tlc)
             )
             AND e2.event_timestamp <= t.event_timestamp
            WHERE t.depth < :max_depth
        )
        SELECT DISTINCT ON (event_id)
            event_id, tlc, event_type, event_timestamp,
            from_entity_reference, to_entity_reference,
            from_facility_reference, to_facility_reference,
            product_reference, quantity, unit_of_measure,
            confidence_score, depth
        FROM trace
        ORDER BY event_id, depth
        LIMIT 5000
    """)

    if not tenant_id:
        raise ValueError("tenant_id is required for RLS-filtered lot tracing")

    rows = db.execute(query, {
        "tlc": tlc,
        "tenant_id": tenant_id,
        "max_depth": max_depth,
    }).fetchall()

    return _build_result(rows, _time.time() - start)


def _build_result(rows, elapsed: float) -> TraceResult:
    """Convert raw query rows into a TraceResult."""
    result = TraceResult(duration_ms=elapsed * 1000)
    seen_lots = set()
    seen_facilities = set()

    for row in rows:
        result.max_hops = max(result.max_hops, row.depth)

        # Collect events
        result.events.append({
            "event_id": str(row.event_id),
            "type": row.event_type,
            "event_date": row.event_timestamp.isoformat() if row.event_timestamp else None,
            "confidence": row.confidence_score,
        })

        # Collect unique lots
        if row.tlc not in seen_lots:
            seen_lots.add(row.tlc)
            qty = row.quantity or 0
            result.total_quantity += qty
            result.lots.append({
                "tlc": row.tlc,
                "product_description": row.product_reference,
                "quantity": qty,
                "unit_of_measure": row.unit_of_measure,
            })

        # Collect unique facilities
        for fac_ref, fac_type in [
            (row.from_facility_reference, "source"),
            (row.to_facility_reference, "destination"),
        ]:
            if fac_ref and fac_ref not in seen_facilities:
                seen_facilities.add(fac_ref)
                result.facilities.append({
                    "gln": fac_ref,
                    "name": fac_ref,
                    "facility_type": fac_type,
                })

    logger.info(
        "lot_trace_complete",
        lots=len(result.lots),
        events=len(result.events),
        facilities=len(result.facilities),
        max_hops=result.max_hops,
        duration_ms=round(result.duration_ms, 1),
    )
    return result
