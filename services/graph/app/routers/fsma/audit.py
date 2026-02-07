from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from ...fsma_audit import FSMAAuditAction, get_audit_log
from ...fsma_drift import (
    AlertSeverity,
    AlertStatus,
    check_for_drift,
    get_drift_detector,
    get_drift_status,
)
from shared.auth import require_api_key

router = APIRouter(tags=["Audit & Drift"])
logger = structlog.get_logger("fsma-audit")


# ============================================================================
# AUDIT TRAIL ENDPOINTS
# ============================================================================


@router.get("/audit/{target_id}")
def get_audit_trail(
    target_id: str,
    api_key=Depends(require_api_key),
):
    """
    Get audit trail for a specific target (lot, event, facility).

    Returns all audit entries for the specified target ID, providing
    a complete history of extractions, modifications, and approvals.

    Per FSMA 204 Section 7, every write to the Graph has a corresponding
    Audit Log entry with:
    - event_id: UUID
    - actor: User ID or "System/AI"
    - action: "EXTRACTED", "MODIFIED", "APPROVED"
    - diff: Previous Value vs. New Value
    - evidence_link: S3 URI to source PDF
    """
    audit_log = get_audit_log()
    entries = audit_log.get_by_target(target_id)

    return {
        "target_id": target_id,
        "total_entries": len(entries),
        "audit_trail": [e.to_dict() for e in entries],
    }


@router.get("/audit")
def get_full_audit_log(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    action: Optional[str] = Query(None, description="Filter by action type"),
    api_key=Depends(require_api_key),
):
    """
    Get full audit log with optional filtering.

    Supports FDA audit readiness by providing complete audit trail
    with chain integrity verification.
    """
    audit_log = get_audit_log()

    if tenant_id:
        entries = audit_log.get_by_tenant(tenant_id)
    elif action:
        try:
            action_enum = FSMAAuditAction(action)
            entries = audit_log.get_by_action(action_enum)
        except ValueError:
            entries = audit_log.get_all()
    else:
        entries = audit_log.get_all()

    # Verify chain integrity
    integrity = audit_log.verify_chain_integrity()

    return {
        "total_entries": len(entries),
        "chain_integrity": integrity,
        "audit_trail": [e.to_dict() for e in entries],
    }


@router.get("/audit/verify")
def verify_audit_integrity(
    api_key=Depends(require_api_key),
):
    """
    Verify the integrity of the entire audit chain.

    Checks:
    - Checksum validity for each entry
    - Chain linkage between entries
    - Detection of any tampering

    Returns integrity status for FDA audit readiness.
    """
    audit_log = get_audit_log()
    integrity = audit_log.verify_chain_integrity()

    return {
        "status": "valid" if integrity["is_valid"] else "compromised",
        "total_entries": integrity["total_entries"],
        "violations": integrity["violations"],
        "recommendation": (
            "Audit chain is intact and FDA-ready"
            if integrity["is_valid"]
            else "Audit chain integrity compromised - investigate immediately"
        ),
    }


# ============================================================================
# DRIFT DETECTION & ALERTING ENDPOINTS
# ============================================================================


@router.get("/drift/status")
def drift_monitoring_status(
    api_key=Depends(require_api_key),
):
    """
    Get current drift monitoring status.

    Returns summary of:
    - Overall health status (HEALTHY, WARNING, CRITICAL)
    - Active alert counts by severity
    - Known supplier count
    - Total snapshots recorded

    Per FSMA 204 Section 8.1: Monitor for supplier format changes.
    """
    return get_drift_status()


@router.get("/drift/analyze")
def analyze_drift(
    window_hours: int = Query(24, ge=1, le=168, description="Analysis window in hours"),
    supplier_gln: Optional[str] = Query(None, description="Filter by supplier GLN"),
    api_key=Depends(require_api_key),
):
    """
    Analyze drift by comparing recent data to historical baseline.

    Detects:
    - KDE completeness rate drops
    - Extraction confidence degradation
    - Supplier format changes

    Returns drift analysis result with any generated alerts.
    """
    result = check_for_drift(
        analysis_window_hours=window_hours,
        supplier_gln=supplier_gln,
    )
    return result.to_dict()


@router.get("/drift/alerts")
def get_drift_alerts(
    status: Optional[str] = Query(
        None, description="Filter by status: ACTIVE, ACKNOWLEDGED, RESOLVED"
    ),
    severity: Optional[str] = Query(
        None, description="Filter by severity: INFO, WARNING, CRITICAL"
    ),
    supplier_gln: Optional[str] = Query(None, description="Filter by supplier GLN"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum alerts to return"),
    api_key=Depends(require_api_key),
):
    """
    Get drift alerts with optional filtering.

    Returns list of alerts sorted by detection time (most recent first).
    """
    detector = get_drift_detector()

    # Parse status filter
    status_filter = None
    if status:
        try:
            status_filter = AlertStatus(status)
        except ValueError:
            pass

    # Parse severity filter
    severity_filter = None
    if severity:
        try:
            severity_filter = AlertSeverity(severity)
        except ValueError:
            pass

    alerts = detector.get_alerts(
        status=status_filter,
        severity=severity_filter,
        supplier_gln=supplier_gln,
        limit=limit,
    )

    return {
        "total": len(alerts),
        "alerts": [a.to_dict() for a in alerts],
    }


@router.get("/drift/suppliers")
def get_supplier_health(
    api_key=Depends(require_api_key),
):
    """
    Get health status per supplier.

    Returns list of suppliers with:
    - Latest completeness rate
    - Latest confidence score
    - Number of active alerts
    - Last activity timestamp

    Sorted by alert count (most problematic suppliers first).
    """
    detector = get_drift_detector()
    return {
        "suppliers": detector.get_supplier_health(),
    }


@router.post("/drift/alerts/{alert_id}/acknowledge")
def acknowledge_drift_alert(
    alert_id: str,
    api_key=Depends(require_api_key),
):
    """Acknowledge a drift alert."""
    detector = get_drift_detector()
    success = detector.acknowledge_alert(alert_id)

    if success:
        return {"status": "acknowledged", "alert_id": alert_id}
    else:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")


@router.post("/drift/alerts/{alert_id}/resolve")
def resolve_drift_alert(
    alert_id: str,
    api_key=Depends(require_api_key),
):
    """Resolve a drift alert."""
    detector = get_drift_detector()
    success = detector.resolve_alert(alert_id)

    if success:
        return {"status": "resolved", "alert_id": alert_id}
    else:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
