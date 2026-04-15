"""
FSMA 204 Traceability Query Utilities -- backward-compatible shim.

This module has been refactored into the ``services.graph.app.fsma``
package.  All public names are re-exported here so that existing
callers (routers, tests, kernel) continue to work without changes.

New code should import directly from ``services.graph.app.fsma``.
"""

from .fsma import (  # noqa: F401 — re-export
    DataQualityReport,
    KDECompletenessMetrics,
    OrphanLot,
    TraceResult,
    _tag_event_risk_flag,
    _validate_temporal_order,
    analyze_kde_completeness,
    find_all_gaps,
    find_broken_chains,
    find_gaps,
    find_orphaned_lots,
    get_lot_timeline,
    query_events_by_range,
    trace_backward,
    trace_forward,
)

__all__ = [
    "TraceResult",
    "OrphanLot",
    "KDECompletenessMetrics",
    "DataQualityReport",
    "_validate_temporal_order",
    "trace_forward",
    "trace_backward",
    "find_broken_chains",
    "find_gaps",
    "find_all_gaps",
    "find_orphaned_lots",
    "analyze_kde_completeness",
    "get_lot_timeline",
    "query_events_by_range",
    "_tag_event_risk_flag",
]
