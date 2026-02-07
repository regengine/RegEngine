"""
Drift Detection Engine for FSMA 204.

Monitors compliance health metrics to detect:
1. Operational Drift (SLA violations, latency spikes)
2. Data Quality Drift (Missing KDEs, unlinked events)
3. Schema Drift (Unexpected extra fields - handled by Schema Registry but monitored here)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional

import uuid

@dataclass
class DriftAlert:
    id: str  # Added ID for frontend keying
    severity: str  # CRITICAL, WARNING, INFO
    metric: str
    current_value: float
    threshold: float
    message: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = "compliance_engine"  # Added source

@dataclass
class ComplianceHealth:
    trace_completeness_rate: float
    average_ingest_latency_ms: float
    error_rate_percent: float
    alerts: List[DriftAlert]
    status: str  # HEALTHY, DEGRADED, CRITICAL

class DriftDetectionEngine:
    def __init__(self, neo4j_driver=None):
        self.driver = neo4j_driver
        # Thresholds
        self.THRESHOLD_TRACE_COMPLETENESS = 0.95  # 95% of events must link
        self.THRESHOLD_LATENCY_MS = 2000          # 2s max ingestion
        self.THRESHOLD_ERROR_RATE = 1.0           # 1% max error

    def check_health(self, tenant_id: str) -> ComplianceHealth:
        """
        Check compliance health for a tenant.
        In a real implementation, this would query Prometheus/Neo4j.
        For now, we simulate based on "observed" state or mock for the UI.
        """
        
        # Simulated metrics (Mocking for Sprint 5 Speed)
        # In production: query neo4j for unlinked events count
        trace_completeness = 0.98
        ingest_latency = 450.0
        error_rate = 0.2
        
        alerts = []
        
        # Drift Rules
        if trace_completeness < self.THRESHOLD_TRACE_COMPLETENESS:
            alerts.append(DriftAlert(
                id=str(uuid.uuid4()),
                severity="WARNING",
                metric="trace_completeness",
                current_value=trace_completeness,
                threshold=self.THRESHOLD_TRACE_COMPLETENESS,
                message=f"Trace completeness dropped to {trace_completeness:.1%}"
            ))
            
        if ingest_latency > self.THRESHOLD_LATENCY_MS:
             alerts.append(DriftAlert(
                id=str(uuid.uuid4()),
                severity="WARNING",
                metric="latency",
                current_value=ingest_latency,
                threshold=self.THRESHOLD_LATENCY_MS,
                message=f"Ingestion latency high: {ingest_latency}ms"
            ))

        if error_rate > self.THRESHOLD_ERROR_RATE:
             alerts.append(DriftAlert(
                id=str(uuid.uuid4()),
                severity="CRITICAL",
                metric="error_rate",
                current_value=error_rate,
                threshold=self.THRESHOLD_ERROR_RATE,
                message=f"Error rate elevated: {error_rate}%"
            ))

        # Overall Status
        status = "HEALTHY"
        if any(a.severity == "CRITICAL" for a in alerts):
            status = "CRITICAL"
        elif any(a.severity == "WARNING" for a in alerts):
            status = "DEGRADED"

        return ComplianceHealth(
            trace_completeness_rate=trace_completeness,
            average_ingest_latency_ms=ingest_latency,
            error_rate_percent=error_rate,
            alerts=alerts,
            status=status
        )
