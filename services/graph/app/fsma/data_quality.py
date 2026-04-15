"""
FSMA 204 data quality monitors: orphan detection and KDE drift analysis.

Detects orphaned lots (created/received but never shipped) and monitors
KDE completeness rates across event types for compliance drift detection.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import structlog

from ..neo4j_utils import Neo4jClient

from .types import DataQualityReport, KDECompletenessMetrics, OrphanLot

logger = structlog.get_logger("fsma-utils")


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
    LIMIT 2000
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
