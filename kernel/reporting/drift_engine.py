"""
Drift Detection Engine for FSMA 204.

Monitors compliance health metrics to detect:
1. Operational Drift (SLA violations, latency spikes)
2. Data Quality Drift (Missing KDEs, unlinked events)
3. Schema Drift (Unexpected extra fields - handled by Schema Registry but monitored here)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

import uuid
import structlog

logger = structlog.get_logger("drift-engine")


@dataclass
class DriftAlert:
    id: str
    severity: str  # CRITICAL, WARNING, INFO
    metric: str
    current_value: float
    threshold: float
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "compliance_engine"


@dataclass
class ComplianceHealth:
    trace_completeness_rate: float
    average_ingest_latency_ms: float
    error_rate_percent: float
    alerts: List[DriftAlert]
    status: str  # HEALTHY, DEGRADED, CRITICAL


class DriftDetectionEngine:
    """Compliance drift detection with live database metrics.
    
    When a db_session_factory is provided, queries live PostgreSQL tables
    (pcos_extracted_facts, pcos_authority_documents) for real metrics.
    Falls back to conservative defaults when no database is available.
    """

    def __init__(self, neo4j_driver=None, db_session_factory=None):
        self.driver = neo4j_driver
        self._db_session_factory = db_session_factory
        # Thresholds
        self.THRESHOLD_TRACE_COMPLETENESS = 0.95  # 95% of events must link
        self.THRESHOLD_LATENCY_MS = 2000          # 2s max ingestion
        self.THRESHOLD_ERROR_RATE = 1.0           # 1% max error

    def check_health(self, tenant_id: str) -> ComplianceHealth:
        """
        Check compliance health for a tenant.
        
        Queries live database metrics when available, otherwise returns
        conservative estimates that will surface as warnings.
        """
        metrics = self._collect_live_metrics(tenant_id)

        trace_completeness = metrics["trace_completeness"]
        ingest_latency = metrics["ingest_latency_ms"]
        error_rate = metrics["error_rate_percent"]

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
                message=f"Ingestion latency high: {ingest_latency:.0f}ms"
            ))

        if error_rate > self.THRESHOLD_ERROR_RATE:
            alerts.append(DriftAlert(
                id=str(uuid.uuid4()),
                severity="CRITICAL",
                metric="error_rate",
                current_value=error_rate,
                threshold=self.THRESHOLD_ERROR_RATE,
                message=f"Error rate elevated: {error_rate:.1f}%"
            ))

        # Add data source indicator alert
        if not metrics.get("live"):
            alerts.append(DriftAlert(
                id=str(uuid.uuid4()),
                severity="INFO",
                metric="data_source",
                current_value=0.0,
                threshold=0.0,
                message="Drift metrics are estimated (no live DB connection). Wire db_session_factory for live data."
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

    def _collect_live_metrics(self, tenant_id: str) -> Dict[str, Any]:
        """Collect metrics from live database or return conservative defaults."""
        if self._db_session_factory is None:
            logger.warning("drift_engine.no_db_session", tenant_id=tenant_id)
            return {
                "trace_completeness": 0.0,
                "ingest_latency_ms": 0.0,
                "error_rate_percent": 0.0,
                "live": False,
            }

        try:
            from sqlalchemy import text

            db = self._db_session_factory()
            try:
                # Metric 1: Trace completeness = facts with authority_document_id / total facts
                total_result = db.execute(
                    text("""
                        SELECT 
                            COUNT(*) AS total_facts,
                            COUNT(authority_document_id) AS linked_facts
                        FROM pcos_extracted_facts
                        WHERE tenant_id = :tid
                    """),
                    {"tid": tenant_id}
                ).first()

                total_facts = total_result.total_facts if total_result else 0
                linked_facts = total_result.linked_facts if total_result else 0
                trace_completeness = (linked_facts / total_facts) if total_facts > 0 else 1.0

                # Metric 2: Average ingestion latency (time between created_at and extracted_at)
                latency_result = db.execute(
                    text("""
                        SELECT AVG(
                            EXTRACT(EPOCH FROM (extracted_at - created_at)) * 1000
                        ) AS avg_latency_ms
                        FROM pcos_extracted_facts
                        WHERE tenant_id = :tid
                          AND extracted_at IS NOT NULL
                          AND created_at >= NOW() - INTERVAL '24 hours'
                    """),
                    {"tid": tenant_id}
                ).first()

                avg_latency = latency_result.avg_latency_ms if latency_result and latency_result.avg_latency_ms else 0.0

                # Metric 3: Error rate = unverified/low-confidence facts in last 24h
                error_result = db.execute(
                    text("""
                        SELECT 
                            COUNT(*) AS recent_total,
                            COUNT(*) FILTER (WHERE extraction_confidence < 0.85) AS low_confidence
                        FROM pcos_extracted_facts
                        WHERE tenant_id = :tid
                          AND created_at >= NOW() - INTERVAL '24 hours'
                    """),
                    {"tid": tenant_id}
                ).first()

                recent_total = error_result.recent_total if error_result else 0
                low_confidence = error_result.low_confidence if error_result else 0
                error_rate = (low_confidence / recent_total * 100) if recent_total > 0 else 0.0

                logger.info(
                    "drift_engine.live_metrics",
                    tenant_id=tenant_id,
                    total_facts=total_facts,
                    trace_completeness=round(trace_completeness, 3),
                    avg_latency_ms=round(avg_latency, 1),
                    error_rate_pct=round(error_rate, 1),
                )

                return {
                    "trace_completeness": trace_completeness,
                    "ingest_latency_ms": avg_latency,
                    "error_rate_percent": error_rate,
                    "live": True,
                }
            finally:
                db.close()

        except Exception as e:
            logger.error("drift_engine.metrics_error", error=str(e), tenant_id=tenant_id)
            return {
                "trace_completeness": 0.0,
                "ingest_latency_ms": 0.0,
                "error_rate_percent": 0.0,
                "live": False,
            }
