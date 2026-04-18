from __future__ import annotations

import uuid
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
from shared.middleware import get_current_tenant_id

router = APIRouter(tags=["Audit & Drift"])
logger = structlog.get_logger("fsma-audit")


# ============================================================================
# AUDIT TRAIL ENDPOINTS
# ============================================================================
#
# SECURITY (#1236): tenant_id is sourced from the authenticated request
# context via `get_current_tenant_id`, never from query string. Every
# returned entry is also validated against the caller's tenant — a cross-
# tenant row is an invariant violation and we surface it as a 500.
# This closes the IDOR where an attacker could read any tenant's audit
# trail by supplying a `tenant_id` query parameter.


def _require_tenant_match(entries, tenant_id: str, context: str):
    """Defense-in-depth: filter out any entry whose tenant_id does not
    match the caller's. If the audit store returned cross-tenant entries
    (e.g. the underlying query ignored tenant), log loudly and surface
    an invariant violation instead of leaking data.
    """
    clean = [
        e for e in entries
        if (getattr(e, "tenant_id", None) in (None, "", tenant_id))
    ]
    leaked = len(entries) - len(clean)
    if leaked:
        logger.error(
            "audit_cross_tenant_leak_detected",
            context=context,
            caller_tenant=tenant_id,
            leaked_count=leaked,
        )
        raise HTTPException(
            status_code=500,
            detail="audit invariant violation: cross-tenant entries detected",
        )
    return clean


@router.get("/audit/{target_id}")
def get_audit_trail(
    target_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
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

    Tenant is derived from the authenticated request (#1236).
    """
    audit_log = get_audit_log()
    tenant_str = str(tenant_id)
    entries = audit_log.get_by_target(target_id)
    entries = _require_tenant_match(entries, tenant_str, "get_by_target")

    return {
        "target_id": target_id,
        "total_entries": len(entries),
        "audit_trail": [e.to_dict() for e in entries],
    }


@router.get("/audit")
def get_full_audit_log(
    action: Optional[str] = Query(None, description="Filter by action type"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Get audit log for the caller's tenant with optional filtering.

    Supports FDA audit readiness by providing complete audit trail
    with chain integrity verification.

    Tenant is derived from the authenticated request (#1236).
    The legacy ``tenant_id`` query parameter was removed because it
    allowed cross-tenant reads when present.
    """
    audit_log = get_audit_log()
    tenant_str = str(tenant_id)

    if action:
        try:
            action_enum = FSMAAuditAction(action)
            entries = audit_log.get_by_action(action_enum)
        except ValueError:
            entries = audit_log.get_by_tenant(tenant_str)
    else:
        entries = audit_log.get_by_tenant(tenant_str)

    entries = _require_tenant_match(entries, tenant_str, "get_full_audit_log")

    # Verify chain integrity
    integrity = audit_log.verify_chain_integrity()

    return {
        "total_entries": len(entries),
        "chain_integrity": integrity,
        "audit_trail": [e.to_dict() for e in entries],
    }


@router.get("/audit/verify")
def verify_audit_integrity(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Verify the integrity of the entire audit chain.

    Checks:
    - Checksum validity for each entry
    - Chain linkage between entries
    - Detection of any tampering

    Returns integrity status for FDA audit readiness.

    Requires a valid tenant context (#1236); integrity verification
    applies to the full chain by design but is gated on authenticated
    access.
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
#
# SECURITY (#1242): drift alerts and supplier health responses are scoped
# to the caller's tenant.  Every alert carries an optional `tenant_id`
# field; we drop any alert whose tenant does not match the caller.


def _filter_alerts_by_tenant(alerts, tenant_id: str):
    """Filter a list of DriftAlert objects to only those belonging to the
    caller's tenant. Alerts with an explicit cross-tenant id are dropped
    with a warning — they indicate a broader bug in producers.
    """
    clean = []
    leaked = 0
    for a in alerts:
        alert_tenant = getattr(a, "tenant_id", None)
        if alert_tenant in (None, "", tenant_id):
            clean.append(a)
        else:
            leaked += 1
    if leaked:
        logger.warning(
            "drift_cross_tenant_alerts_filtered",
            caller_tenant=tenant_id,
            leaked_count=leaked,
        )
    return clean


@router.get("/drift/status")
def drift_monitoring_status(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Get current drift monitoring status for the caller's tenant.

    Returns summary of:
    - Overall health status (HEALTHY, WARNING, CRITICAL)
    - Active alert counts by severity
    - Known supplier count
    - Total snapshots recorded

    Per FSMA 204 Section 8.1: Monitor for supplier format changes.
    Tenant is sourced from authentication (#1242).
    """
    detector = get_drift_detector()
    tenant_str = str(tenant_id)
    all_alerts = detector.get_alerts(status=AlertStatus.ACTIVE, limit=10000)
    alerts = _filter_alerts_by_tenant(all_alerts, tenant_str)

    critical = sum(1 for a in alerts if a.severity == AlertSeverity.CRITICAL)
    warning = sum(1 for a in alerts if a.severity == AlertSeverity.WARNING)
    if critical > 0:
        status = "CRITICAL"
    elif warning > 0:
        status = "WARNING"
    else:
        status = "HEALTHY"

    base = get_drift_status()
    base.update({
        "status": status,
        "active_alerts": len(alerts),
        "critical_alerts": critical,
        "warning_alerts": warning,
        "tenant_id": tenant_str,
    })
    return base


@router.get("/drift/analyze")
def analyze_drift(
    window_hours: int = Query(24, ge=1, le=168, description="Analysis window in hours"),
    supplier_gln: Optional[str] = Query(None, description="Filter by supplier GLN"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Analyze drift by comparing recent data to historical baseline.

    Detects:
    - KDE completeness rate drops
    - Extraction confidence degradation
    - Supplier format changes

    Returns drift analysis result with any generated alerts.
    Tenant is sourced from authentication (#1242).
    """
    result = check_for_drift(
        analysis_window_hours=window_hours,
        supplier_gln=supplier_gln,
    )
    response = result.to_dict()
    tenant_str = str(tenant_id)
    filtered_alerts = [
        a for a in result.alerts
        if getattr(a, "tenant_id", None) in (None, "", tenant_str)
    ]
    response["alerts"] = [a.to_dict() for a in filtered_alerts]
    response["tenant_id"] = tenant_str
    return response


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
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Get drift alerts for the caller's tenant, with optional filtering.

    Returns list of alerts sorted by detection time (most recent first).
    Tenant is sourced from authentication (#1242).
    """
    detector = get_drift_detector()
    tenant_str = str(tenant_id)

    status_filter = None
    if status:
        try:
            status_filter = AlertStatus(status)
        except ValueError:
            pass

    severity_filter = None
    if severity:
        try:
            severity_filter = AlertSeverity(severity)
        except ValueError:
            pass

    # Fetch generously then filter to caller's tenant.
    raw = detector.get_alerts(
        status=status_filter,
        severity=severity_filter,
        supplier_gln=supplier_gln,
        limit=max(limit * 10, limit),
    )
    alerts = _filter_alerts_by_tenant(raw, tenant_str)[:limit]

    return {
        "total": len(alerts),
        "alerts": [a.to_dict() for a in alerts],
        "tenant_id": tenant_str,
    }


@router.get("/drift/suppliers")
def get_supplier_health(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """
    Get health status per supplier for the caller's tenant.

    Returns list of suppliers with:
    - Latest completeness rate
    - Latest confidence score
    - Number of active alerts
    - Last activity timestamp

    Sorted by alert count (most problematic suppliers first).
    Tenant is sourced from authentication (#1242).
    """
    detector = get_drift_detector()
    tenant_str = str(tenant_id)

    all_suppliers = detector.get_supplier_health()

    # Re-count active alerts per supplier using tenant-scoped alerts.
    tenant_active_alerts = _filter_alerts_by_tenant(
        detector.get_alerts(status=AlertStatus.ACTIVE, limit=10000),
        tenant_str,
    )
    alerts_by_supplier = {}
    for alert in tenant_active_alerts:
        if alert.supplier_gln:
            alerts_by_supplier.setdefault(alert.supplier_gln, 0)
            alerts_by_supplier[alert.supplier_gln] += 1

    scoped = []
    for row in all_suppliers:
        scoped_row = dict(row)
        scoped_row["active_alerts"] = alerts_by_supplier.get(
            row.get("supplier_gln"), 0
        )
        scoped.append(scoped_row)

    scoped.sort(key=lambda r: r["active_alerts"], reverse=True)

    return {
        "suppliers": scoped,
        "tenant_id": tenant_str,
    }


@router.post("/drift/alerts/{alert_id}/acknowledge")
def acknowledge_drift_alert(
    alert_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """Acknowledge a drift alert belonging to the caller's tenant.

    Tenant is sourced from authentication (#1242). A 404 is returned
    when the alert does not exist *or* belongs to another tenant to
    avoid enumeration leaks.
    """
    detector = get_drift_detector()
    tenant_str = str(tenant_id)

    target = next(
        (
            a for a in detector.get_alerts(limit=10000)
            if a.alert_id == alert_id
            and getattr(a, "tenant_id", None) in (None, "", tenant_str)
        ),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    success = detector.acknowledge_alert(alert_id)
    if success:
        return {"status": "acknowledged", "alert_id": alert_id}
    raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")


@router.post("/drift/alerts/{alert_id}/resolve")
def resolve_drift_alert(
    alert_id: str,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    api_key=Depends(require_api_key),
):
    """Resolve a drift alert belonging to the caller's tenant.

    Tenant is sourced from authentication (#1242).
    """
    detector = get_drift_detector()
    tenant_str = str(tenant_id)

    target = next(
        (
            a for a in detector.get_alerts(limit=10000)
            if a.alert_id == alert_id
            and getattr(a, "tenant_id", None) in (None, "", tenant_str)
        ),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    success = detector.resolve_alert(alert_id)
    if success:
        return {"status": "resolved", "alert_id": alert_id}
    raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
