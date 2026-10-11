"""
FSMA 204 data quality monitors: orphan detection and KDE drift analysis.

Detects orphaned lots (created/received but never shipped) and monitors
KDE completeness rates across event types for compliance drift detection.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import List

import structlog

from ..neo4j_utils import Neo4jClient
from .types import DataQualityReport, KDECompletenessMetrics, OrphanLot

logger = structlog.get_logger("fsma-utils")


async def find_orphaned_lots(
    client: Neo4jClient,
    tenant_id: str,
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
        tenant_id: Tenant UUID (required, non-empty)
        days_stagnant: Minimum days without outbound activity (default 30)

    Returns:
        List of OrphanLot objects with stagnant inventory details

    Raises:
        ValueError: if ``tenant_id`` is falsy/empty. On Community Neo4j all
            tenants share one database, so a null tenant would return every
            tenant's orphan lots. Fail closed (#2540).
    """
    # #2540 — fail closed on a missing tenant rather than the old
    # `$tenant_id IS NULL OR ...` shim that returned every tenant's lots.
    if not tenant_id:
        raise ValueError(
            "find_orphaned_lots requires a non-empty tenant_id; null-tenant queries are not supported (#2540)"
        )

    start_time = time.time()

    # Calculate cutoff date
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_stagnant)).strftime("%Y-%m-%d")

    # Find lots with inbound events but no outbound events
    # Inbound: RECEIVING, CREATION, or PRODUCED by transformation
    # Outbound: SHIPPING, CONSUMED by transformation
    #
    # #1270 — the inbound-event OR is wrapped in parentheses. Cypher's
    # `AND` binds tighter than `OR`, so the prior shape
    #
    #     WHERE tenant_ok
    #       AND EXISTS { inbound_a } OR EXISTS { inbound_b }
    #       AND NOT EXISTS { outbound_a }
    #       AND NOT EXISTS { outbound_b }
    #
    # parses as
    #
    #     (tenant_ok AND EXISTS a)
    #     OR
    #     (EXISTS b AND NOT EXISTS outbound_a AND NOT EXISTS outbound_b)
    #
    # — leaving the `PRODUCED` branch of the query with no tenant filter.
    # Every lot produced by a transformation in ANY tenant matched, and
    # `GET /fsma/compliance/gaps/orphans` streamed those to the caller.
    # Parenthesizing the inbound OR restores the intended
    #   tenant_ok AND (inbound_a OR inbound_b) AND NOT ...
    # shape.
    #
    # #2949 — DIRECTION. The outbound-consumption guard used to read
    # ``MATCH (l)-[:CONSUMED]->(trans:TraceEvent)`` — lot -> event — while
    # ``FSMARelationships.EVENT_CONSUMED_LOT`` persists the edge as
    # ``MERGE (e)-[:CONSUMED]->(l)`` — event -> lot. No writer creates the
    # edge in the queried direction, so the ``NOT EXISTS`` was unconditionally
    # true and the guard was dead code: every raw-material and WIP lot
    # consumed by a TRANSFORMATION would be reported as stagnant inventory in
    # ``GET /fsma/compliance/gaps/orphans``, burying the genuine orphans
    # (received-and-never-moved lots) the check exists to surface. Note the
    # inbound branch immediately above already matched the writer's direction,
    # which is what makes this an inversion rather than a local convention.
    #
    # #2949 — SCOPE. The sub-query nodes (``e``, ``trans``, ``ship``,
    # ``last_event``) carried no tenant predicate; the #1270 fix scoped only
    # the outer lot. A cross-tenant event could therefore suppress an orphan
    # classification (or supply the "most recent event" that decides
    # stagnation). Each sub-query node is now scoped explicitly.
    query = """
    MATCH (l:Lot)
    WHERE l.tenant_id = $tenant_id

    // Must have at least one inbound event
    AND (
        EXISTS {
            MATCH (l)-[:UNDERWENT]->(e:TraceEvent)
            WHERE e.tenant_id = $tenant_id
              AND e.type IN ['RECEIVING', 'CREATION']
        }
        OR EXISTS {
            MATCH (trans:TraceEvent)-[:PRODUCED]->(l)
            WHERE trans.tenant_id = $tenant_id
        }
    )

    // Must NOT have any outbound events
    AND NOT EXISTS {
        MATCH (l)-[:UNDERWENT]->(ship:TraceEvent {type: 'SHIPPING'})
        WHERE ship.tenant_id = $tenant_id
    }
    AND NOT EXISTS {
        MATCH (trans:TraceEvent)-[:CONSUMED]->(l)
        WHERE trans.tenant_id = $tenant_id
    }

    // Get the most recent event for this lot
    OPTIONAL MATCH (l)-[:UNDERWENT]->(last_event:TraceEvent)
    WHERE last_event.tenant_id = $tenant_id
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
    LIMIT 2000
    """

    orphans = []
    async with client.session() as session:
        result = await session.run(query, tenant_id=tenant_id, cutoff_date=cutoff_date)

        async for record in result:
            # Calculate stagnant days. The parsed date is naive, so anchor
            # it to UTC before subtracting: an aware minus naive
            # subtraction raises TypeError, which the fallback below would
            # swallow and report every lot as exactly `days_stagnant` old.
            last_date = record["last_event_date"]
            if last_date:
                try:
                    last_dt = datetime.strptime(str(last_date)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
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
                    created_at=(str(record["created_at"]) if record["created_at"] else None),
                    stagnant_days=stagnant,
                    last_event_type=record["last_event_type"],
                    last_event_date=(str(record["last_event_date"]) if record["last_event_date"] else None),
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
    tenant_id: str,
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
        tenant_id: Tenant UUID (required, non-empty)
        confidence_threshold: Threshold below which confidence is "low" (default 0.85)

    Returns:
        DataQualityReport with completeness metrics by event type

    Raises:
        ValueError: if ``tenant_id`` is falsy/empty. A null tenant would
            aggregate every tenant's events into one report. Fail closed
            (#2540).
    """
    # #2540 — fail closed on a missing tenant rather than the old
    # `$tenant_id IS NULL OR ...` shim that aggregated every tenant's events.
    if not tenant_id:
        raise ValueError(
            "analyze_kde_completeness requires a non-empty tenant_id; null-tenant queries are not supported (#2540)"
        )

    start_time = time.time()

    # The lot-linkage checks scope the joined Lot to the caller's tenant: an
    # UNDERWENT edge pointing at another tenant's Lot (corrupt cross-tenant
    # edge) must not mark this tenant's event as linked.
    #
    # ``complete_count`` is counted row by row. The previous code derived it
    # in Python as ``total - max(missing_date, missing_lot, low_conf)``,
    # which overstates completeness whenever different events miss different
    # fields (e.g. 5 events missing dates and 5 other events missing lots
    # reported 5 complete events instead of 0).
    #
    # ``avg(e.confidence)`` ignores NULL confidences. The previous
    # ``avg(CASE ... ELSE 0 END)`` scored events with no confidence value
    # as 0, dragging the average down for tenants that do not record it.
    query = """
    MATCH (e:TraceEvent)
    WHERE e.tenant_id = $tenant_id

    WITH e.type as event_type,
         count(e) as total,
         sum(CASE WHEN e.event_date IS NULL OR e.event_date = '' THEN 1 ELSE 0 END) as missing_date,
         sum(CASE WHEN NOT EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) WHERE l.tenant_id = $tenant_id } THEN 1 ELSE 0 END) as missing_lot,
         sum(CASE WHEN e.confidence IS NOT NULL AND e.confidence < $threshold THEN 1 ELSE 0 END) as low_confidence,
         avg(e.confidence) as avg_confidence,
         sum(CASE WHEN (e.event_date IS NOT NULL AND e.event_date <> '')
                   AND EXISTS { MATCH (e)<-[:UNDERWENT]-(l:Lot) WHERE l.tenant_id = $tenant_id }
                   AND (e.confidence IS NULL OR e.confidence >= $threshold)
                  THEN 1 ELSE 0 END) as complete_count

    RETURN
        event_type,
        total,
        missing_date,
        missing_lot,
        low_confidence,
        avg_confidence,
        complete_count
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
            # Complete events are counted row by row in Cypher (see query
            # above), not derived from the per-category maxima.
            total_complete += record["complete_count"] or 0

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
