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
