"""
FDA Export Monitoring & Health Checks.

Provides real-time metrics on FDA export activity and health checks
that verify the export pipeline is operational (DB connectivity,
chain integrity, export capability, KDE completeness).

Endpoints:
    GET /api/v1/monitoring/exports/{tenant_id} — Export metrics dashboard
    GET /api/v1/monitoring/health/{tenant_id}  — Pipeline health check
    GET /api/v1/monitoring/alerts/{tenant_id}  — Active monitoring alerts
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from shared.tenant_context import TenantContext

from .compliance_score import _query_required_kde_coverage
from .webhook_compat import require_tenant_context

logger = logging.getLogger("export-monitoring")

router = APIRouter(prefix="/api/v1/monitoring", tags=["Export Monitoring"])

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

HealthStatus = Literal["healthy", "warning", "critical"]

KDE_COMPLETENESS_THRESHOLD = 0.80  # 80%


class ExportMetrics(BaseModel):
    """Aggregated export activity metrics for a tenant."""

    tenant_id: str
    total_exports: int = 0
    exports_last_24h: int = 0
    exports_last_7d: int = 0
    avg_record_count: Optional[float] = None
    last_export_at: Optional[str] = None
    export_types: Dict[str, int] = Field(default_factory=dict)


class HealthCheckResult(BaseModel):
    """Result of a single health check."""

    name: str
    status: HealthStatus
    message: str
    details: Optional[Dict[str, Any]] = None


class ExportHealthCheck(BaseModel):
    """Aggregated health check results for a tenant."""

    tenant_id: str
    status: HealthStatus = "healthy"
    checks: List[HealthCheckResult] = Field(default_factory=list)
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MonitoringAlert(BaseModel):
    """A monitoring alert for export pipeline issues."""

    id: str
    tenant_id: str
    alert_type: str
    severity: HealthStatus
    message: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Helper: query export logs from DB
# ---------------------------------------------------------------------------


def _query_export_logs(tenant_id: str) -> Optional[List[dict]]:
    """Query fsma.fda_export_log for a tenant. Returns None if DB unavailable."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            rows = db.execute(
                text("""
                    SELECT id, tenant_id, export_type, record_count, generated_at
                    FROM fsma.fda_export_log
                    WHERE tenant_id = :tenant_id
                    ORDER BY generated_at DESC
                """),
                {"tenant_id": tenant_id},
            ).fetchall()

            return [
                {
                    "id": str(row.id),
                    "tenant_id": str(row.tenant_id),
                    "export_type": row.export_type,
                    "record_count": row.record_count,
                    # UTC so the endpoints can compare these strings with their UTC cut-offs.
                    "generated_at": row.generated_at.astimezone(timezone.utc).isoformat() if row.generated_at else None,
                }
                for row in rows
            ]
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Export log query failed (fallback to empty): %s", exc)
        return None


def _check_db_connectivity() -> HealthCheckResult:
    """Verify we can query fsma.cte_events."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            result = db.execute(text("SELECT 1 FROM fsma.cte_events LIMIT 1"))
            result.fetchone()
            return HealthCheckResult(
                name="db_connectivity",
                status="healthy",
                message="Database connection to fsma.cte_events is operational.",
            )
        finally:
            db.close()
    except Exception as exc:
        return HealthCheckResult(
            name="db_connectivity",
            status="critical",
            message=f"Cannot reach fsma.cte_events: {exc}",
        )


def _check_chain_integrity(tenant_id: str) -> HealthCheckResult:
    """Run verify_chain and check for gaps."""
    try:
        from shared.cte_persistence import CTEPersistence
        from shared.database import SessionLocal

        db = SessionLocal()
        try:
            persistence = CTEPersistence(db)
            result = persistence.verify_chain(tenant_id)

            if result.valid:
                return HealthCheckResult(
                    name="chain_integrity",
                    status="healthy",
                    message="SHA-256 hash chain is intact with no gaps.",
                    details={"chain_length": getattr(result, "chain_length", None)},
                )
            else:
                return HealthCheckResult(
                    name="chain_integrity",
                    status="critical",
                    message="Chain integrity verification FAILED.",
                    details={"errors": result.errors if hasattr(result, "errors") else []},
                )
        finally:
            db.close()
    except Exception as exc:
        return HealthCheckResult(
            name="chain_integrity",
            status="warning",
            message=f"Chain verification unavailable: {exc}",
        )


def _check_export_readiness(tenant_id: str) -> HealthCheckResult:
    """Verify at least one export exists in fda_export_log."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            row = db.execute(
                text("""
                    SELECT COUNT(*) AS cnt
                    FROM fsma.fda_export_log
                    WHERE tenant_id = :tenant_id
                """),
                {"tenant_id": tenant_id},
            ).fetchone()

            count = row.cnt if row else 0
            if count > 0:
                return HealthCheckResult(
                    name="export_readiness",
                    status="healthy",
                    message=f"Export pipeline operational. {count} export(s) on record.",
                    details={"export_count": count},
                )
            else:
                return HealthCheckResult(
                    name="export_readiness",
                    status="warning",
                    message="No exports found. Pipeline untested for this tenant.",
                    details={"export_count": 0},
                )
        finally:
            db.close()
    except Exception as exc:
        return HealthCheckResult(
            name="export_readiness",
            status="critical",
            message=f"Cannot verify export readiness: {exc}",
        )


def _check_kde_completeness(tenant_id: str) -> HealthCheckResult:
    """Check that required-KDE completeness is above the 80% threshold.

    Same measure the compliance score reports (#2962): required KDE fields
    present over required KDE fields, per CTE type, read from
    ``fsma.cte_events`` and ``fsma.cte_kdes``.
    """
    try:
        from shared.database import SessionLocal

        db = SessionLocal()
        try:
            coverage = _query_required_kde_coverage(db, tenant_id)
        finally:
            db.close()
    except Exception as exc:
        return HealthCheckResult(
            name="kde_completeness",
            status="warning",
            message=f"KDE completeness check unavailable: {exc}",
        )

    total = coverage["required_kde_checks_total"]
    present = coverage["required_kde_checks_passed"]
    unchecked = coverage["events_unchecked_type"]
    details: Dict[str, Any] = {
        "required_fields": total,
        "present_fields": present,
        "events_unchecked_type": unchecked,
        "completeness_pct": None,
    }

    if total == 0:
        message = "No CTE events found for this tenant."
        if unchecked:
            message = (
                f"No CTE events with a required-KDE checklist; {unchecked} event(s) have no required-KDE checklist."
            )
        return HealthCheckResult(name="kde_completeness", status="warning", message=message, details=details)

    completeness = present / total
    pct = round(completeness * 100, 1)
    details["completeness_pct"] = pct

    if completeness >= KDE_COMPLETENESS_THRESHOLD:
        return HealthCheckResult(
            name="kde_completeness",
            status="healthy",
            message=f"Required KDE completeness at {pct}% (threshold: {KDE_COMPLETENESS_THRESHOLD * 100}%).",
            details=details,
        )
    return HealthCheckResult(
        name="kde_completeness",
        status="warning",
        message=f"Required KDE completeness at {pct}% — below {KDE_COMPLETENESS_THRESHOLD * 100}% threshold.",
        details=details,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/exports/{tenant_id}", summary="Export metrics dashboard")
async def export_metrics(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Return aggregated export metrics for a tenant."""
    tenant_id = ctx.tenant_id
    logs = _query_export_logs(tenant_id)

    if logs is None:
        # DB unavailable — return empty metrics
        return ExportMetrics(tenant_id=tenant_id).model_dump()

    now = datetime.now(timezone.utc)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_7d = (now - timedelta(days=7)).isoformat()

    total = len(logs)
    last_24h = sum(1 for l in logs if l.get("generated_at") and l["generated_at"] >= cutoff_24h)
    last_7d = sum(1 for l in logs if l.get("generated_at") and l["generated_at"] >= cutoff_7d)

    record_counts = [l["record_count"] for l in logs if l.get("record_count")]
    avg_records = sum(record_counts) / len(record_counts) if record_counts else None

    last_export = logs[0]["generated_at"] if logs else None

    type_counts: Dict[str, int] = {}
    for l in logs:
        export_type = l.get("export_type") or "unknown"
        type_counts[export_type] = type_counts.get(export_type, 0) + 1

    metrics = ExportMetrics(
        tenant_id=tenant_id,
        total_exports=total,
        exports_last_24h=last_24h,
        exports_last_7d=last_7d,
        avg_record_count=round(avg_records, 1) if avg_records is not None else None,
        last_export_at=last_export,
        export_types=type_counts,
    )

    return metrics.model_dump()


@router.get("/health/{tenant_id}", summary="Export pipeline health check")
async def health_check(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Run health checks on the export pipeline for a tenant."""
    tenant_id = ctx.tenant_id
    checks = [
        _check_db_connectivity(),
        _check_chain_integrity(tenant_id),
        _check_export_readiness(tenant_id),
        _check_kde_completeness(tenant_id),
    ]

    # Determine overall status: worst check wins
    if any(c.status == "critical" for c in checks):
        overall = "critical"
    elif any(c.status == "warning" for c in checks):
        overall = "warning"
    else:
        overall = "healthy"

    result = ExportHealthCheck(
        tenant_id=tenant_id,
        status=overall,
        checks=checks,
    )

    return result.model_dump()


@router.get("/alerts/{tenant_id}", summary="Active monitoring alerts")
async def monitoring_alerts(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Generate monitoring alerts based on current health checks."""
    tenant_id = ctx.tenant_id
    alerts: List[MonitoringAlert] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Run health checks and convert failures to alerts
    checks = [
        _check_db_connectivity(),
        _check_chain_integrity(tenant_id),
        _check_export_readiness(tenant_id),
        _check_kde_completeness(tenant_id),
    ]

    for check in checks:
        if check.status in ("warning", "critical"):
            alert = MonitoringAlert(
                id=f"mon-{check.name}-{tenant_id}",
                tenant_id=tenant_id,
                alert_type=check.name,
                severity=check.status,
                message=check.message,
                created_at=now_iso,
            )
            alerts.append(alert)

    # Check for stale exports (no exports in 7 days)
    logs = _query_export_logs(tenant_id)
    if logs:
        last_export_str = logs[0].get("generated_at")
        if last_export_str:
            try:
                last_dt = datetime.fromisoformat(last_export_str)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                stale_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
                if last_dt < stale_cutoff:
                    alerts.append(
                        MonitoringAlert(
                            id=f"mon-stale-exports-{tenant_id}",
                            tenant_id=tenant_id,
                            alert_type="stale_exports",
                            severity="warning",
                            message=f"No exports in 7+ days. Last export: {last_export_str}.",
                            created_at=now_iso,
                        )
                    )
            except (ValueError, TypeError):
                pass

    return {
        "tenant_id": tenant_id,
        "count": len(alerts),
        "alerts": [a.model_dump() for a in alerts],
    }
