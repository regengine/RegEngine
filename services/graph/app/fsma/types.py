"""
FSMA 204 Traceability data types.

Dataclasses used across all FSMA utility modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


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
    # #2945: ``facilities``/``events``/``lots`` above are three independent
    # *deduplicated* lists, so the lot<->event<->facility association present
    # in the traversed path is lost by the time an exporter sees the result.
    # The FDA trace CSV compensated by pairing every lot with every event and
    # stamping the first GLN-bearing facility on the row — fabricating
    # associations rather than omitting them.
    #
    # ``trace_rows`` preserves the association at the source: one entry per
    # (lot, event) edge the graph actually records, carrying that event's own
    # ``OCCURRED_AT`` facility (or ``None``). Shape:
    #     {"lot": {...}, "event": {...}, "facility": {...} | None}
    # ``None`` (rather than ``[]``) means "the tracer did not supply
    # associations", which consumers must treat as unknown — never as a
    # licence to guess.
    trace_rows: Optional[List[Dict[str, Any]]] = None
    # SEL-515: the traversal and association queries are capped (LIMIT
    # ``TRACE_ROW_LIMIT``). When a query returns the full cap the result may be
    # incomplete, so it says so instead of looking complete during a recall.
    truncated: bool = False
    truncation_limit: Optional[int] = None


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
