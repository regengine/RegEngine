"""
Prometheus Metrics for Energy Service

Operational observability for snapshot engine.
"""
from prometheus_client import Counter, Histogram, Gauge, Info

# Snapshot metrics
SNAPSHOT_CREATED_TOTAL = Counter(
    "energy_snapshot_created_total",
    "Total snapshots created",
    ["substation_id", "trigger_event", "status"]
)

SNAPSHOT_CREATION_DURATION = Histogram(
    "energy_snapshot_creation_duration_seconds",
    "Snapshot creation latency",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

SNAPSHOT_CREATION_FAILURES = Counter(
    "energy_snapshot_creation_failures_total",
    "Failed snapshot creations",
    ["reason"]  # integrity, db, unknown
)

# Chain integrity metrics
CHAIN_VERIFICATIONS_TOTAL = Counter(
    "energy_chain_verifications_total",
    "Chain integrity verifications",
    ["result"]  # success, failure
)

CHAIN_BREAKS_TOTAL = Counter(
    "energy_chain_breaks_total",
    "Chain integrity violations (CRITICAL)",
    ["substation_id", "violation_type"]  # id_mismatch, time_violation, signature_invalid
)

SNAPSHOT_INTEGRITY_REJECTIONS_TOTAL = Counter(
    "energy_snapshot_integrity_rejections_total",
    "Snapshots rejected due to integrity violations (should be zero)",
    ["reason"]  # invalid_signature, chain_break, content_mismatch
)

# Mismatch metrics
MISMATCH_DETECTED_TOTAL = Counter(
    "energy_mismatch_detected_total",
    "Mismatches detected",
    ["severity"]
)

MISMATCH_RESOLVED_TOTAL = Counter(
    "energy_mismatch_resolved_total",
    "Mismatches resolved",
    ["resolution_type"]
)

# Queue metrics
SNAPSHOT_QUEUE_DEPTH = Gauge(
    "energy_snapshot_queue_depth",
    "Pending snapshot creation requests"
)

# Idempotency metrics
SNAPSHOT_DEDUPLICATED_TOTAL = Counter(
    "energy_snapshot_deduplicated_total",
    "Snapshots deduplicated (returned existing)",
    ["trigger_event"]
)

# Service info
SERVICE_INFO = Info(
    "energy_service",
    "Energy service version and build info"
)

SERVICE_INFO.info({
    "version": "1.0.0",
    "service": "energy-api",
    "compliance_target": "NERC-CIP-013-1"
})
