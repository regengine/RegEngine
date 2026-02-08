"""
FSMA 204 Prometheus Metrics for Compliance Monitoring.

Sprint 5: FSMA Health Dashboard Metrics

Provides metrics for:
- Trace query performance (24-hour recall SLA)
- Data quality (gap rates, orphan counts)
- Compliance readiness (KDE completeness)
- API usage patterns
"""

import time
from functools import wraps
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram, Info
from prometheus_client import REGISTRY


# ============================================================================
# SAFE METRIC CREATION HELPERS
# ============================================================================
# These prevent ValueError: Duplicated timeseries when modules are
# re-imported during test collection.

def _get_or_create_histogram(name, documentation, labelnames=(), **kwargs):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return Histogram(name, documentation, labelnames, **kwargs)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


def _get_or_create_counter(name, documentation, labelnames=()):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return Counter(name, documentation, labelnames)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


def _get_or_create_gauge(name, documentation, labelnames=()):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return Gauge(name, documentation, labelnames)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


def _get_or_create_info(name, documentation):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    try:
        return Info(name, documentation)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


# ============================================================================
# TRACE QUERY METRICS
# ============================================================================

TRACE_QUERY_LATENCY = _get_or_create_histogram(
    "fsma_trace_query_seconds",
    "Time spent executing trace queries",
    ["direction", "status"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

TRACE_QUERIES_TOTAL = _get_or_create_counter(
    "fsma_trace_queries_total",
    "Total number of trace queries executed",
    ["direction", "status"],
)

TRACE_MAX_DEPTH = _get_or_create_gauge(
    "fsma_trace_max_depth", "Maximum depth reached in trace queries", ["direction"]
)

TRACE_FACILITIES_FOUND = _get_or_create_counter(
    "fsma_trace_facilities_total",
    "Total facilities found in trace queries",
    ["direction"],
)

# ============================================================================
# RECALL SLA METRICS (24-Hour Mandate)
# ============================================================================

RECALL_SLA_SECONDS = _get_or_create_histogram(
    "fsma_recall_sla_seconds",
    "Time to generate complete recall package",
    ["export_type"],
    buckets=[1, 5, 10, 30, 60, 300, 900, 3600, 7200, 21600, 43200, 86400],
)

RECALL_SLA_COMPLIANCE_RATE = _get_or_create_gauge(
    "fsma_recall_sla_compliance_rate",
    "Percentage of recalls meeting 24-hour SLA",
)

RECALL_EXPORTS_TOTAL = _get_or_create_counter(
    "fsma_recall_exports_total",
    "Total recall exports generated",
    ["export_type", "status"],
)

# ============================================================================
# DATA QUALITY METRICS
# ============================================================================

GAPS_TOTAL = _get_or_create_gauge(
    "fsma_gaps_total",
    "Total events with missing required KDEs",
    ["gap_type"],
)

GAP_RATE = _get_or_create_gauge(
    "fsma_gap_rate", "Percentage of events with missing KDEs", ["event_type"]
)

ORPHANS_TOTAL = _get_or_create_gauge(
    "fsma_orphans_total",
    "Total orphaned lots (created but never shipped/consumed)",
)

ORPHAN_QUANTITY_AT_RISK = _get_or_create_gauge(
    "fsma_orphan_quantity_at_risk",
    "Total quantity in orphaned lots",
    ["unit_of_measure"],
)

ORPHAN_AVG_STAGNANT_DAYS = _get_or_create_gauge(
    "fsma_orphan_avg_stagnant_days",
    "Average days orphaned lots have been stagnant",
)

# ============================================================================
# KDE COMPLETENESS METRICS
# ============================================================================

KDE_COMPLETENESS_RATE = _get_or_create_gauge(
    "fsma_kde_completeness_rate",
    "Overall KDE completeness rate (0.0 to 1.0)",
)

KDE_COMPLETENESS_BY_TYPE = _get_or_create_gauge(
    "fsma_kde_completeness_by_type",
    "KDE completeness rate by event type",
    ["event_type"],
)

EXTRACTION_CONFIDENCE_AVG = _get_or_create_gauge(
    "fsma_extraction_confidence_avg",
    "Average extraction confidence score",
    ["event_type"],
)

LOW_CONFIDENCE_EXTRACTIONS = _get_or_create_counter(
    "fsma_low_confidence_extractions_total",
    "Total extractions below confidence threshold",
    ["event_type"],
)

# ============================================================================
# GRAPH STATISTICS
# ============================================================================

LOTS_TOTAL = _get_or_create_gauge(
    "fsma_lots_total",
    "Total lots in the traceability graph",
)

EVENTS_TOTAL = _get_or_create_gauge(
    "fsma_events_total", "Total trace events in the graph", ["event_type"]
)

FACILITIES_TOTAL = _get_or_create_gauge(
    "fsma_facilities_total", "Total facilities in the graph", ["facility_type"]
)

BROKEN_CHAINS_TOTAL = _get_or_create_gauge(
    "fsma_broken_chains_total",
    "Total broken chain violations",
)

# ============================================================================
# API METRICS
# ============================================================================

FSMA_API_CALLS = _get_or_create_counter(
    "fsma_api_calls_total", "Total FSMA API calls", ["endpoint", "method", "status"]
)

FSMA_API_LATENCY = _get_or_create_histogram(
    "fsma_api_latency_seconds",
    "FSMA API endpoint latency",
    ["endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ============================================================================
# VALIDATION METRICS
# ============================================================================

TLC_VALIDATIONS_TOTAL = _get_or_create_counter(
    "fsma_tlc_validations_total",
    "Total TLC validations performed",
    ["result"],
)

GS1_VALIDATIONS_TOTAL = _get_or_create_counter(
    "fsma_gs1_validations_total",
    "Total GS1 identifier validations",
    ["identifier_type", "result"],
)

# ============================================================================
# SYSTEM INFO
# ============================================================================

FSMA_MODULE_INFO = _get_or_create_info("fsma_module", "FSMA 204 module information")

# Set module info on import (safe to call repeatedly)
FSMA_MODULE_INFO.info(
    {
        "version": "1.0.0",
        "regulation": "FSMA_204",
        "compliance_target": "24_hour_recall",
    }
)


# ============================================================================
# METRIC HELPER FUNCTIONS
# ============================================================================


def record_trace_query(
    direction: str,
    duration_seconds: float,
    status: str,
    hop_count: int,
    facility_count: int,
):
    """Record metrics for a trace query execution."""
    TRACE_QUERY_LATENCY.labels(direction=direction, status=status).observe(
        duration_seconds
    )
    TRACE_QUERIES_TOTAL.labels(direction=direction, status=status).inc()
    TRACE_MAX_DEPTH.labels(direction=direction).set(hop_count)
    TRACE_FACILITIES_FOUND.labels(direction=direction).inc(facility_count)


def record_recall_export(export_type: str, duration_seconds: float, status: str):
    """Record metrics for a recall export generation."""
    RECALL_SLA_SECONDS.labels(export_type=export_type).observe(duration_seconds)
    RECALL_EXPORTS_TOTAL.labels(export_type=export_type, status=status).inc()


def update_gap_metrics(
    missing_date: int, missing_lot: int, total_events: int, gap_rates: dict
):
    """Update gap-related gauges."""
    GAPS_TOTAL.labels(gap_type="missing_date").set(missing_date)
    GAPS_TOTAL.labels(gap_type="missing_lot").set(missing_lot)

    for event_type, rate in gap_rates.items():
        GAP_RATE.labels(event_type=event_type).set(rate)


def update_orphan_metrics(
    orphan_count: int,
    total_quantity: float,
    avg_stagnant_days: float,
    quantity_by_unit: dict,
):
    """Update orphan-related gauges."""
    ORPHANS_TOTAL.set(orphan_count)
    ORPHAN_AVG_STAGNANT_DAYS.set(avg_stagnant_days)

    for unit, qty in quantity_by_unit.items():
        ORPHAN_QUANTITY_AT_RISK.labels(unit_of_measure=unit or "unknown").set(qty)


def update_completeness_metrics(
    overall_rate: float, by_type: dict, confidence_by_type: dict
):
    """Update KDE completeness gauges."""
    KDE_COMPLETENESS_RATE.set(overall_rate)

    for event_type, rate in by_type.items():
        KDE_COMPLETENESS_BY_TYPE.labels(event_type=event_type).set(rate)

    for event_type, confidence in confidence_by_type.items():
        EXTRACTION_CONFIDENCE_AVG.labels(event_type=event_type).set(confidence)


def update_graph_stats(
    lots_count: int, events_by_type: dict, facilities_by_type: dict, broken_chains: int
):
    """Update graph statistics gauges."""
    LOTS_TOTAL.set(lots_count)
    BROKEN_CHAINS_TOTAL.set(broken_chains)

    for event_type, count in events_by_type.items():
        EVENTS_TOTAL.labels(event_type=event_type).set(count)

    for facility_type, count in facilities_by_type.items():
        FACILITIES_TOTAL.labels(facility_type=facility_type).set(count)


def record_api_call(endpoint: str, method: str, status: str, duration: float):
    """Record FSMA API call metrics."""
    FSMA_API_CALLS.labels(endpoint=endpoint, method=method, status=status).inc()
    FSMA_API_LATENCY.labels(endpoint=endpoint).observe(duration)


def record_validation(identifier_type: str, is_valid: bool):
    """Record identifier validation result."""
    result = "valid" if is_valid else "invalid"

    if identifier_type == "TLC":
        TLC_VALIDATIONS_TOTAL.labels(result=result).inc()
    else:
        GS1_VALIDATIONS_TOTAL.labels(
            identifier_type=identifier_type, result=result
        ).inc()


# Aliases for simpler import patterns
def record_gap_detection(gap_count: int, gap_type: str = "missing_lot"):
    """Record gap detection event."""
    GAPS_TOTAL.labels(gap_type=gap_type).set(gap_count)


def record_orphan_detection(orphan_count: int, quantity_at_risk: float = 0.0):
    """Record orphan detection event."""
    ORPHANS_TOTAL.set(orphan_count)
    if quantity_at_risk > 0:
        ORPHAN_QUANTITY_AT_RISK.labels(unit_of_measure="units").set(quantity_at_risk)


def record_recall_sla(duration_seconds: float, export_type: str = "csv"):
    """Record recall SLA timing."""
    RECALL_SLA_SECONDS.labels(export_type=export_type).observe(duration_seconds)


def update_data_quality_score(score: float):
    """Update overall data quality score."""
    KDE_COMPLETENESS_RATE.set(score)


def record_extraction_confidence(confidence: float, event_type: str = "default"):
    """Record extraction confidence score."""
    EXTRACTION_CONFIDENCE_AVG.labels(event_type=event_type).set(confidence)
    if confidence < 0.85:
        LOW_CONFIDENCE_EXTRACTIONS.labels(event_type=event_type).inc()


def get_health_status() -> dict:
    """Get current FSMA health status from metrics."""
    return {
        "status": "ok",
        "module": "fsma-204",
        "metrics_available": True,
        "compliance_target": "24_hour_recall",
    }


def get_metrics_text() -> str:
    """
    Get all FSMA metrics in Prometheus text format.

    Returns:
        Prometheus-formatted metrics text.
    """
    from prometheus_client import REGISTRY, generate_latest

    return generate_latest(REGISTRY).decode("utf-8")


# ============================================================================
# DECORATOR FOR AUTOMATIC METRIC COLLECTION
# ============================================================================


def track_fsma_endpoint(endpoint_name: str):
    """Decorator to automatically track FSMA endpoint metrics."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start_time
                record_api_call(endpoint_name, "GET", status, duration)

        return wrapper

    return decorator


def track_trace_query(direction: str):
    """Decorator to automatically track trace query metrics."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Extract metrics from result if it has the expected attributes
                hop_count = getattr(result, "hop_count", 0)
                facility_count = len(getattr(result, "facilities", []))

                record_trace_query(
                    direction, duration, status, hop_count, facility_count
                )
                return result
            except Exception as e:
                status = "error"
                duration = time.time() - start_time
                record_trace_query(direction, duration, status, 0, 0)
                raise

        return wrapper

    return decorator
