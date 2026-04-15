"""
FSMA 204 Traceability Query Utilities.

Provides forward and backward tracing through the supply chain graph
to support FDA 24-hour recall requirements.

Physics Engine:
- Time Arrow enforcement via shared.fsma_rules.TimeArrowRule
- Broken chain detection for SHIPPING events
- Strict temporal filtering on trace paths

This package re-exports all public names so that existing imports
(e.g. ``from services.graph.app.fsma_utils import trace_forward``)
continue to work via the backward-compatible shim in ``fsma_utils.py``.
"""

# -- types --
from .types import (
    DataQualityReport,
    KDECompletenessMetrics,
    OrphanLot,
    TraceResult,
)

# -- validation --
from .validation import _validate_temporal_order

# -- tracing --
from .tracer import trace_backward, trace_forward

# -- chain integrity --
from .chain_integrity import find_all_gaps, find_broken_chains, find_gaps

# -- data quality --
from .data_quality import analyze_kde_completeness, find_orphaned_lots

# -- queries --
from .queries import _tag_event_risk_flag, get_lot_timeline, query_events_by_range

__all__ = [
    # types
    "TraceResult",
    "OrphanLot",
    "KDECompletenessMetrics",
    "DataQualityReport",
    # validation
    "_validate_temporal_order",
    # tracing
    "trace_forward",
    "trace_backward",
    # chain integrity
    "find_broken_chains",
    "find_gaps",
    "find_all_gaps",
    # data quality
    "find_orphaned_lots",
    "analyze_kde_completeness",
    # queries
    "get_lot_timeline",
    "query_events_by_range",
    "_tag_event_risk_flag",
]
