"""
Disaster Recovery Router.

Provides readiness assessments, backup status checks, and recovery
simulations for FSMA 204 traceability data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from shared.database import get_db_safe
from shared.tenant_context import TenantContext
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .compliance_score import _query_required_kde_coverage
from .webhook_compat import require_tenant_context

logger = logging.getLogger("disaster-recovery")


router = APIRouter(
    prefix="/api/v1/dr",
    tags=["Disaster Recovery"],
)

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class DRCheck(BaseModel):
    """A single disaster-recovery readiness check."""

    name: str
    status: str = Field(..., description="pass | fail | warn")
    details: str
    checked_at: str


class DRReport(BaseModel):
    """Aggregate DR readiness report."""

    tenant_id: str
    overall_status: str = Field(..., description="ready | at_risk | critical")
    checks: list[DRCheck] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    generated_at: str
    recovery_time_estimate: str = Field(..., description="Estimated time to recover, e.g. '2h 15m'")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_db_connectivity() -> DRCheck:
    """Verify database connectivity and basic replication health."""
    now = datetime.now(timezone.utc).isoformat()
    db = get_db_safe()
    if not db:
        return DRCheck(
            name="database_connectivity",
            status="fail",
            details="Unable to connect to database",
            checked_at=now,
        )
    try:
        result = db.execute(text("SELECT 1")).fetchone()
        if result and result[0] == 1:
            # Attempt a lightweight replication check (Supabase/Postgres)
            try:
                rep = db.execute(text("SELECT state FROM pg_stat_replication LIMIT 1")).fetchone()
                if rep:
                    return DRCheck(
                        name="database_connectivity",
                        status="pass",
                        details=f"Database connected, replication state: {rep[0]}",
                        checked_at=now,
                    )
            except SQLAlchemyError:
                pass  # no replication info available — still a pass for connectivity
            return DRCheck(
                name="database_connectivity",
                status="pass",
                details="Database connected (replication status unavailable)",
                checked_at=now,
            )
        return DRCheck(
            name="database_connectivity",
            status="fail",
            details="Database query returned unexpected result",
            checked_at=now,
        )
    except SQLAlchemyError as exc:
        return DRCheck(
            name="database_connectivity",
            status="fail",
            details=f"Database query failed: {exc}",
            checked_at=now,
        )
    finally:
        db.close()


def _chain_row_is_broken(index: int, row, rows) -> bool:
    """True when this chain row is not a valid link in position ``index``.

    The old readiness query only counted rows whose previous hash was null
    and whose sequence was above 1. A flipped chain hash, a sequence hole
    left by a truncate, or a previous hash that points at the wrong row all
    passed that query.
    """
    from shared.cte_persistence import compute_chain_hash

    seq, event_hash, stored_prev, stored_chain = row[0], row[1], row[2], row[3]
    try:
        seq_num = int(seq)
    except (TypeError, ValueError):
        return True
    if seq_num != index + 1:
        return True
    if not isinstance(event_hash, str) or not event_hash:
        return True
    if not isinstance(stored_chain, str) or not stored_chain:
        return True
    if index == 0:
        if stored_prev is not None:
            return True
    elif stored_prev != rows[index - 1][3]:
        return True
    previous = stored_prev if isinstance(stored_prev, str) or stored_prev is None else str(stored_prev)
    return compute_chain_hash(event_hash, previous) != stored_chain


def _check_hash_chain_integrity(tenant_id: str) -> DRCheck:
    """Verify that the SHA-256 hash chain has no gaps and each hash recomputes."""
    now = datetime.now(timezone.utc).isoformat()
    db = get_db_safe()
    if not db:
        return DRCheck(
            name="hash_chain_integrity",
            status="warn",
            details="Cannot verify hash chain — database unavailable",
            checked_at=now,
        )
    try:
        rows = (
            db.execute(
                text(
                    "SELECT sequence_num, event_hash, previous_chain_hash, chain_hash "
                    "FROM fsma.hash_chain WHERE tenant_id = :tid "
                    "ORDER BY sequence_num ASC"
                ),
                {"tid": tenant_id},
            ).fetchall()
            or []
        )

        if not rows:
            count_row = db.execute(
                text("SELECT COUNT(*) FROM fsma.traceability_events WHERE tenant_id = :tid AND status != 'rejected'"),
                {"tid": tenant_id},
            ).fetchone()
            event_count = int(count_row[0]) if count_row and count_row[0] else 0
            if event_count:
                return DRCheck(
                    name="hash_chain_integrity",
                    status="fail",
                    details=f"Hash chain is missing while {event_count} event(s) exist",
                    checked_at=now,
                )
            return DRCheck(
                name="hash_chain_integrity",
                status="warn",
                details="No hash chain records found for tenant",
                checked_at=now,
            )

        gaps = sum(1 for index, row in enumerate(rows) if _chain_row_is_broken(index, row, rows))
        if gaps == 0:
            return DRCheck(
                name="hash_chain_integrity",
                status="pass",
                details=f"Hash chain intact — {len(rows)} entries, 0 gaps",
                checked_at=now,
            )
        return DRCheck(
            name="hash_chain_integrity",
            status="fail",
            details=f"Hash chain has {gaps} gap(s) in {len(rows)} entries",
            checked_at=now,
        )
    except SQLAlchemyError as exc:
        logger.debug("hash_chain_check_failed error=%s", str(exc))
        return DRCheck(
            name="hash_chain_integrity",
            status="warn",
            details=f"Hash chain check error: {exc}",
            checked_at=now,
        )
    finally:
        db.close()


def _check_export_completeness(tenant_id: str) -> DRCheck:
    """Check that recent FDA exports exist."""
    now = datetime.now(timezone.utc).isoformat()
    db = get_db_safe()
    if not db:
        return DRCheck(
            name="export_completeness",
            status="warn",
            details="Cannot verify exports — database unavailable",
            checked_at=now,
        )
    try:
        row = db.execute(
            text(
                "SELECT COUNT(*), MAX(generated_at) FROM fsma.fda_export_log "
                "WHERE tenant_id = :tid AND generated_at > now() - interval '7 days'"
            ),
            {"tid": tenant_id},
        ).fetchone()

        if not row or row[0] == 0:
            return DRCheck(
                name="export_completeness",
                status="warn",
                details="No exports in the last 7 days",
                checked_at=now,
            )
        return DRCheck(
            name="export_completeness",
            status="pass",
            details=f"{row[0]} export(s) in last 7 days, latest: {row[1]}",
            checked_at=now,
        )
    except SQLAlchemyError as exc:
        logger.debug("export_check_failed error=%s", str(exc))
        return DRCheck(
            name="export_completeness",
            status="warn",
            details=f"Export check error: {exc}",
            checked_at=now,
        )
    finally:
        db.close()


def _check_data_volume(tenant_id: str) -> tuple[DRCheck, dict]:
    """Assess data volume for recovery time estimation."""
    now = datetime.now(timezone.utc).isoformat()
    volume_info: dict = {"total_events": 0, "total_tlcs": 0, "date_range_days": 0}
    db = get_db_safe()
    if not db:
        return (
            DRCheck(
                name="data_volume",
                status="warn",
                details="Cannot assess data volume — database unavailable",
                checked_at=now,
            ),
            volume_info,
        )
    try:
        row = db.execute(
            text(
                "SELECT COUNT(*) AS events, "
                "COUNT(DISTINCT traceability_lot_code) AS tlcs, "
                "EXTRACT(EPOCH FROM (MAX(event_timestamp) - MIN(event_timestamp))) / 86400 AS days_range "
                "FROM fsma.traceability_events WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        ).fetchone()

        if not row or row[0] == 0:
            return (
                DRCheck(
                    name="data_volume",
                    status="warn",
                    details="No events found for tenant",
                    checked_at=now,
                ),
                volume_info,
            )

        events = int(row[0])
        tlcs = int(row[1])
        days = int(row[2]) if row[2] else 0
        volume_info = {"total_events": events, "total_tlcs": tlcs, "date_range_days": days}

        return (
            DRCheck(
                name="data_volume",
                status="pass",
                details=f"{events} events, {tlcs} unique TLCs, spanning {days} days",
                checked_at=now,
            ),
            volume_info,
        )
    except SQLAlchemyError as exc:
        logger.debug("data_volume_check_failed error=%s", str(exc))
        return (
            DRCheck(
                name="data_volume",
                status="warn",
                details=f"Data volume check error: {exc}",
                checked_at=now,
            ),
            volume_info,
        )
    finally:
        db.close()


def _check_supplier_health(tenant_id: str) -> DRCheck:
    """Check active supplier percentage."""
    now = datetime.now(timezone.utc).isoformat()
    db = get_db_safe()
    if not db:
        return DRCheck(
            name="supplier_network_health",
            status="warn",
            details="Cannot check supplier health — database unavailable",
            checked_at=now,
        )
    try:
        row = db.execute(
            text(
                "SELECT COUNT(*), "
                "SUM(CASE WHEN portal_status = 'active' THEN 1 ELSE 0 END) "
                "FROM fsma.tenant_suppliers WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        ).fetchone()

        if not row or row[0] == 0:
            return DRCheck(
                name="supplier_network_health",
                status="warn",
                details="No suppliers registered for tenant",
                checked_at=now,
            )

        total, active = int(row[0]), int(row[1]) if row[1] else 0
        pct = round(active / total * 100, 1)
        status = "pass" if pct >= 80 else ("warn" if pct >= 50 else "fail")

        return DRCheck(
            name="supplier_network_health",
            status=status,
            details=f"{active}/{total} suppliers active ({pct}%)",
            checked_at=now,
        )
    except SQLAlchemyError as exc:
        logger.debug("supplier_health_check_failed error=%s", str(exc))
        return DRCheck(
            name="supplier_network_health",
            status="warn",
            details=f"Supplier health check error: {exc}",
            checked_at=now,
        )
    finally:
        db.close()


def _estimate_recovery_time(volume: dict) -> str:
    """Estimate recovery time based on data volume."""
    events = volume.get("total_events", 0)
    # Rough heuristic: ~10k events/min for re-export/rebuild
    if events == 0:
        return "< 5m"
    minutes = max(5, events / 10_000)
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = int(minutes // 60)
    remaining_minutes = int(minutes % 60)
    return f"{hours}h {remaining_minutes}m"


def _compile_recommendations(checks: list[DRCheck]) -> list[str]:
    """Generate actionable recommendations from failed/warned checks."""
    recs: list[str] = []
    for check in checks:
        if check.status == "fail":
            if "database" in check.name:
                recs.append("Restore database connectivity and verify replication is running")
            elif "hash_chain" in check.name:
                recs.append("Investigate and repair hash chain gaps before next audit window")
            elif "supplier" in check.name:
                recs.append("Re-engage inactive suppliers and renew expired portal links")
        elif check.status == "warn":
            if "export" in check.name:
                recs.append("Schedule regular data exports to ensure recovery baseline exists")
            if "data_volume" in check.name:
                recs.append("Verify event ingestion pipeline is operational")
            if "hash_chain" in check.name:
                recs.append("Run hash chain audit when database is available")
            if "supplier" in check.name:
                recs.append("Increase active supplier participation rate")
    if not recs:
        recs.append("All checks passed — maintain current backup and monitoring schedule")
    return recs


def _overall_status(checks: list[DRCheck]) -> str:
    """Derive overall DR status from individual checks."""
    fail_count = sum(1 for c in checks if c.status == "fail")
    warn_count = sum(1 for c in checks if c.status == "warn")
    if fail_count >= 2:
        return "critical"
    if fail_count >= 1 or warn_count >= 3:
        return "at_risk"
    return "ready"


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{tenant_id}/readiness",
    response_model=DRReport,
    summary="DR readiness assessment",
)
async def dr_readiness(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
) -> DRReport:
    """Run a full disaster-recovery readiness assessment for a tenant."""
    tenant_id = ctx.tenant_id
    checks: list[DRCheck] = []

    checks.append(_check_db_connectivity())
    checks.append(_check_hash_chain_integrity(tenant_id))
    checks.append(_check_export_completeness(tenant_id))

    volume_check, volume_info = _check_data_volume(tenant_id)
    checks.append(volume_check)
    checks.append(_check_supplier_health(tenant_id))

    rte = _estimate_recovery_time(volume_info)
    recommendations = _compile_recommendations(checks)
    status = _overall_status(checks)

    report = DRReport(
        tenant_id=tenant_id,
        overall_status=status,
        checks=checks,
        recommendations=recommendations,
        generated_at=datetime.now(timezone.utc).isoformat(),
        recovery_time_estimate=rte,
    )
    logger.info(
        "dr_readiness_complete tenant=%s status=%s rte=%s",
        tenant_id,
        status,
        rte,
    )
    return report


@router.get(
    "/{tenant_id}/backup-status",
    summary="Check data backup / replication status",
)
async def backup_status(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Check backup and replication health for tenant data."""
    tenant_id = ctx.tenant_id
    now = datetime.now(timezone.utc)
    db_check = _check_db_connectivity()
    export_check = _check_export_completeness(tenant_id)
    volume_check, volume_info = _check_data_volume(tenant_id)

    return {
        "tenant_id": tenant_id,
        "database": {
            "status": db_check.status,
            "details": db_check.details,
        },
        "exports": {
            "status": export_check.status,
            "details": export_check.details,
        },
        "data_volume": volume_info,
        "checked_at": now.isoformat(),
    }


@router.post(
    "/{tenant_id}/test-recovery",
    response_model=DRReport,
    summary="Simulate recovery (dry run)",
)
async def test_recovery(
    tenant_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
) -> DRReport:
    """Simulate a disaster-recovery scenario and estimate recovery time."""
    tenant_id = ctx.tenant_id
    now_str = datetime.now(timezone.utc).isoformat()
    checks: list[DRCheck] = []

    # 1. Estimate time to re-export all data
    volume_check, volume_info = _check_data_volume(tenant_id)
    checks.append(volume_check)
    rte = _estimate_recovery_time(volume_info)
    checks.append(
        DRCheck(
            name="re_export_estimate",
            status="pass" if volume_info["total_events"] > 0 else "warn",
            details=f"Estimated re-export time: {rte} for {volume_info['total_events']} events",
            checked_at=now_str,
        )
    )

    # 2. Check if hash chain can be rebuilt from events.
    # A warning that the chain could not be read is not evidence that a
    # rebuild will succeed. An empty chain while events remain is a failed
    # integrity check, and those events are what a rebuild would use.
    chain_check = _check_hash_chain_integrity(tenant_id)
    checks.append(chain_check)
    if chain_check.status == "fail" and "missing while" in chain_check.details:
        rebuild_status = "pass"
        rebuild_details = "Hash chain can be rebuilt from event data"
    elif chain_check.status == "fail":
        rebuild_status = "fail"
        rebuild_details = "Hash chain rebuild may not be possible — gaps detected"
    elif chain_check.status == "warn" and not chain_check.details.startswith("No hash chain records"):
        rebuild_status = "warn"
        rebuild_details = "Hash chain could not be read, so rebuild feasibility is unknown"
    else:
        rebuild_status = "pass"
        rebuild_details = "Hash chain can be rebuilt from event data"
    checks.append(
        DRCheck(
            name="chain_rebuild_feasibility",
            status=rebuild_status,
            details=rebuild_details,
            checked_at=now_str,
        )
    )

    # 3. KDE completeness for recovery
    db = get_db_safe()
    kde_status = "warn"
    kde_details = "Cannot verify KDE completeness — database unavailable"
    if db:
        try:
            # Same measure the compliance score reports (#2962): required KDE
            # fields present over required KDE fields, per CTE type.
            coverage = _query_required_kde_coverage(db, tenant_id)
            total = coverage["required_kde_checks_total"]
            passed = coverage["required_kde_checks_passed"]
            unchecked = coverage["events_unchecked_type"]
            unchecked_note = f"; {unchecked} event(s) have no required-KDE checklist" if unchecked else ""
            if total:
                pct = passed / total * 100
                kde_status = "pass" if pct >= 80 else "warn"
                kde_details = f"Required KDE completeness: {pct:.1f}% ({passed}/{total} fields present){unchecked_note}"
            else:
                kde_details = f"No KDE completeness data available{unchecked_note}"
        except SQLAlchemyError as exc:
            logger.debug("kde_recovery_check_failed error=%s", str(exc))
            kde_details = f"KDE check error: {exc}"
        finally:
            db.close()

    checks.append(
        DRCheck(
            name="kde_recovery_completeness",
            status=kde_status,
            details=kde_details,
            checked_at=now_str,
        )
    )

    recommendations = _compile_recommendations(checks)
    status = _overall_status(checks)

    report = DRReport(
        tenant_id=tenant_id,
        overall_status=status,
        checks=checks,
        recommendations=recommendations,
        generated_at=now_str,
        recovery_time_estimate=rte,
    )
    logger.info(
        "recovery_simulation_complete tenant=%s status=%s rte=%s",
        tenant_id,
        status,
        rte,
    )
    return report
