"""Compliance API routes for the 2am Alert feature.

Provides endpoints for:
- GET /v1/compliance/status - The "big status widget"
- GET /v1/compliance/alerts - List all alerts
- POST /v1/compliance/alerts/{id}/acknowledge - Mark as seen
- POST /v1/compliance/alerts/{id}/resolve - Complete action
- GET/PUT /v1/compliance/profile - Product profile for matching
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .compliance_models import AlertSeverity, AlertSourceType
from .compliance_service_sync import ComplianceServiceSync
from .database import get_session
from .dependencies import get_current_user, PermissionChecker

logger = structlog.get_logger("compliance.routes")

router = APIRouter(prefix="/v1/compliance", tags=["compliance"])


# ===========================================================================
# Request/Response Models
# ===========================================================================


class ComplianceStatusResponse(BaseModel):
    """Response for compliance status endpoint."""

    tenant_id: str
    status: str
    status_emoji: str
    status_label: str
    last_status_change: Optional[str]
    active_alert_count: int
    critical_alert_count: int
    completeness_score: Optional[float]
    next_deadline: Optional[str]
    next_deadline_description: Optional[str]
    countdown_seconds: Optional[int]
    countdown_display: Optional[str]
    active_alerts: List[Dict[str, Any]] = Field(default_factory=list)


class AlertResponse(BaseModel):
    """Response for a single alert."""

    id: str
    tenant_id: str
    source_type: str
    source_id: str
    title: str
    summary: Optional[str]
    severity: str
    severity_emoji: str
    countdown_start: Optional[str]
    countdown_end: Optional[str]
    countdown_hours: int
    countdown_seconds: int
    countdown_display: str
    is_expired: bool
    required_actions: List[Dict[str, Any]]
    status: str
    acknowledged_at: Optional[str]
    acknowledged_by: Optional[str]
    resolved_at: Optional[str]
    resolved_by: Optional[str]
    match_reason: Optional[Dict[str, Any]]
    created_at: Optional[str]


class AlertActionRequest(BaseModel):
    """Request for alert actions (acknowledge/resolve)."""

    user_id: str = Field(..., description="ID of user performing action")
    notes: Optional[str] = Field(None, description="Optional notes")


class CreateAlertRequest(BaseModel):
    """Request to manually create an alert."""

    tenant_id: str
    source_type: str = "MANUAL"
    source_id: Optional[str] = None
    title: str
    summary: Optional[str] = None
    severity: str = "MEDIUM"
    countdown_hours: int = 24
    required_actions: List[Dict[str, Any]] = Field(default_factory=list)


class ProductProfileRequest(BaseModel):
    """Request to update product profile."""

    product_categories: Optional[List[str]] = None
    supply_regions: Optional[List[str]] = None
    supplier_identifiers: Optional[List[str]] = None
    fda_product_codes: Optional[List[str]] = None
    retailer_relationships: Optional[List[str]] = None


class CreateSnapshotRequest(BaseModel):
    """Request to create a compliance snapshot."""

    snapshot_name: str = Field(..., description="Name for this snapshot (e.g., 'Pre-Audit Q1 2026')")
    snapshot_reason: Optional[str] = Field(None, description="Reason for creating snapshot")
    created_by: str = Field(..., description="User ID creating the snapshot")


class SnapshotResponse(BaseModel):
    """Response for snapshot endpoints."""

    id: str
    tenant_id: str
    snapshot_name: str
    snapshot_reason: Optional[str]
    created_by: str
    compliance_status: str
    compliance_status_emoji: str
    active_alert_count: int
    critical_alert_count: int
    completeness_score: Optional[float]
    content_hash: str
    hash_algorithm: str
    integrity_verified: bool
    is_verified: bool
    verified_at: Optional[str]
    verified_by: Optional[str]
    captured_at: str
    created_at: str


class SnapshotSummaryResponse(BaseModel):
    """Summary response for snapshot list."""

    id: str
    tenant_id: str
    snapshot_name: str
    compliance_status: str
    compliance_status_emoji: str
    active_alert_count: int
    critical_alert_count: int
    content_hash: str
    integrity_verified: bool
    captured_at: str
    created_by: str


class AttestSnapshotRequest(BaseModel):
    """Request to attest to a compliance snapshot."""

    attested_by: str = Field(..., description="Full name of the person attesting (e.g., 'Jane Smith')")
    attestation_title: str = Field(..., description="Title/role of the attesting person (e.g., 'VP Operations')")


# ===========================================================================
# Endpoints
# ===========================================================================


@router.get("/status/{tenant_id}", response_model=ComplianceStatusResponse, dependencies=[Depends(PermissionChecker("analysis.read"))])
def get_compliance_status(
    tenant_id: str,
    session=Depends(get_session),
) -> ComplianceStatusResponse:
    """Get current compliance status for a tenant.

    This is the "big status widget" that shows:
    - ✅ COMPLIANT / ⚠️ AT_RISK / 🚨 NON_COMPLIANT
    - Active alert count
    - Countdown to next deadline
    - List of active alerts

    This is what an executive looks at to answer:
    "Are we safe right now?"
    """
    try:
        service = ComplianceServiceSync(session)
        status = service.get_status(UUID(tenant_id))
        return ComplianceStatusResponse(**status)
    except Exception as e:
        logger.error("get_status_failed", tenant_id=tenant_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/alerts/{tenant_id}", dependencies=[Depends(PermissionChecker("analysis.read"))])
def list_alerts(
    tenant_id: str,
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE, ACKNOWLEDGED, RESOLVED"),
    limit: int = Query(50, ge=1, le=200),
    session=Depends(get_session),
) -> List[AlertResponse]:
    """List alerts for a tenant.

    Returns alerts ordered by creation date (newest first).
    Filter by status to see only active alerts.
    """
    try:
        service = ComplianceServiceSync(session)
        alerts = service.get_alerts(
            UUID(tenant_id),
            status_filter=status,
            limit=limit,
        )
        return [AlertResponse(**alert.to_dict()) for alert in alerts]
    except Exception as e:
        logger.error("list_alerts_failed", tenant_id=tenant_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/alerts/{tenant_id}/{alert_id}", dependencies=[Depends(PermissionChecker("analysis.read"))])
def get_alert(
    tenant_id: str,
    alert_id: str,
    session=Depends(get_session),
) -> AlertResponse:
    """Get a single alert by ID."""
    try:
        service = ComplianceServiceSync(session)
        alert = service.get_alert(UUID(alert_id))
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        if str(alert.tenant_id) != tenant_id:
            raise HTTPException(status_code=403, detail="Alert belongs to different tenant")
        return AlertResponse(**alert.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_alert_failed", alert_id=alert_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/alerts/{tenant_id}/{alert_id}/acknowledge", dependencies=[Depends(PermissionChecker("analysis.create"))])
def acknowledge_alert(
    tenant_id: str,
    alert_id: str,
    request: AlertActionRequest,
    session=Depends(get_session),
) -> AlertResponse:
    """Mark an alert as acknowledged.

    This indicates the user has seen the alert but hasn't completed
    the required action yet. The countdown continues.
    """
    try:
        service = ComplianceServiceSync(session)
        alert = service.acknowledge_alert(UUID(alert_id), request.user_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return AlertResponse(**alert.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("acknowledge_alert_failed", alert_id=alert_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/alerts/{tenant_id}/{alert_id}/resolve", dependencies=[Depends(PermissionChecker("analysis.create"))])
def resolve_alert(
    tenant_id: str,
    alert_id: str,
    request: AlertActionRequest,
    session=Depends(get_session),
) -> AlertResponse:
    """Resolve an alert.

    This indicates the required action has been completed.
    The alert is marked as resolved and the tenant's status is recalculated.
    """
    try:
        service = ComplianceServiceSync(session)
        alert = service.resolve_alert(
            UUID(alert_id),
            request.user_id,
            request.notes,
        )
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return AlertResponse(**alert.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("resolve_alert_failed", alert_id=alert_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/alerts", dependencies=[Depends(PermissionChecker("analysis.create"))])
def create_alert(
    request: CreateAlertRequest,
    session=Depends(get_session),
) -> AlertResponse:
    """Manually create a compliance alert.

    Typically alerts are created automatically by the scheduler
    when external events are detected. This endpoint allows manual
    alert creation for testing or ad-hoc situations.
    """
    try:
        # Map string to enum
        source_type = AlertSourceType[request.source_type]
        severity = AlertSeverity[request.severity]

        service = ComplianceServiceSync(session)
        alert = service.create_alert(
            tenant_id=UUID(request.tenant_id),
            source_type=source_type,
            source_id=request.source_id or f"manual-{datetime.now(timezone.utc).isoformat()}",
            title=request.title,
            summary=request.summary,
            severity=severity,
            countdown_hours=request.countdown_hours,
            required_actions=request.required_actions,
        )
        return AlertResponse(**alert.to_dict())
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Invalid enum value: {e}")
    except Exception as e:
        logger.error("create_alert_failed", error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/profile/{tenant_id}", dependencies=[Depends(PermissionChecker("analysis.read"))])
def get_product_profile(
    tenant_id: str,
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Get tenant's product profile for alert matching.

    The product profile determines which external events
    (recalls, warnings, etc.) apply to this tenant.
    """
    try:
        service = ComplianceServiceSync(session)
        profile = service.get_product_profile(UUID(tenant_id))
        if not profile:
            return {
                "tenant_id": tenant_id,
                "product_categories": [],
                "supply_regions": [],
                "supplier_identifiers": [],
                "fda_product_codes": [],
                "retailer_relationships": [],
            }
        return profile.to_dict()
    except Exception as e:
        logger.error("get_profile_failed", tenant_id=tenant_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/profile/{tenant_id}", dependencies=[Depends(PermissionChecker("analysis.create"))])
def update_product_profile(
    tenant_id: str,
    request: ProductProfileRequest,
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Update tenant's product profile.

    Set the product categories, supply regions, and other
    attributes used to match external alerts to this tenant.

    Example:
    ```json
    {
        "product_categories": ["leafy_greens", "romaine_lettuce"],
        "supply_regions": ["CA", "AZ"],
        "retailer_relationships": ["walmart", "costco"]
    }
    ```
    """
    try:
        service = ComplianceServiceSync(session)
        profile = service.update_product_profile(
            tenant_id=UUID(tenant_id),
            product_categories=request.product_categories,
            supply_regions=request.supply_regions,
            supplier_identifiers=request.supplier_identifiers,
            fda_product_codes=request.fda_product_codes,
            retailer_relationships=request.retailer_relationships,
        )
        return profile.to_dict()
    except Exception as e:
        logger.error("update_profile_failed", tenant_id=tenant_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


# ===========================================================================
# SNAPSHOT ENDPOINTS - Proof-of-Compliance for Audit Defense
# ===========================================================================


@router.post("/snapshots/{tenant_id}", dependencies=[Depends(PermissionChecker("audit.create"))])
def create_snapshot(
    tenant_id: str,
    request: CreateSnapshotRequest,
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Create a point-in-time compliance snapshot.

    Captures the current compliance state with cryptographic hash.
    Use before audits to freeze what was true at a specific moment.

    The content_hash ensures the snapshot cannot be tampered with.
    """
    try:
        service = ComplianceServiceSync(session)
        snapshot = service.create_snapshot(
            tenant_id=UUID(tenant_id),
            snapshot_name=request.snapshot_name,
            snapshot_reason=request.snapshot_reason,
            created_by=request.created_by,
        )
        return snapshot.to_dict()
    except Exception as e:
        logger.error("create_snapshot_failed", tenant_id=tenant_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/snapshots/{tenant_id}", dependencies=[Depends(PermissionChecker("audit.read"))])
def list_snapshots(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=200),
    session=Depends(get_session),
) -> List[Dict[str, Any]]:
    """List compliance snapshots for a tenant.

    Returns snapshots in reverse chronological order (newest first).
    Use to view snapshot history and select one for verification/export.
    """
    try:
        service = ComplianceServiceSync(session)
        snapshots = service.list_snapshots(UUID(tenant_id), limit=limit)
        return [s.to_summary_dict() for s in snapshots]
    except Exception as e:
        logger.error("list_snapshots_failed", tenant_id=tenant_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/snapshots/{tenant_id}/diff", dependencies=[Depends(PermissionChecker("audit.read"))])
def diff_snapshots(
    tenant_id: str,
    snapshot_a: str = Query(..., description="ID of first (older) snapshot"),
    snapshot_b: str = Query(..., description="ID of second (newer) snapshot"),
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Compare two snapshots and return the differences.

    Shows what changed between two compliance states:
    - Status changes (COMPLIANT → NON_COMPLIANT)
    - Alert count changes
    - New alerts added
    - Alerts resolved

    Useful for audit reporting and timeline reconstruction.
    """
    try:
        service = ComplianceServiceSync(session)
        result = service.diff_snapshots(UUID(snapshot_a), UUID(snapshot_b))
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("diff_snapshots_failed", error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/snapshots/{tenant_id}/{snapshot_id}", dependencies=[Depends(PermissionChecker("audit.read"))])
def get_snapshot(
    tenant_id: str,
    snapshot_id: str,
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Get a single snapshot with full details.

    Includes all captured data: status, alerts, profile.
    """
    try:
        service = ComplianceServiceSync(session)
        snapshot = service.get_snapshot(UUID(snapshot_id))
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        if str(snapshot.tenant_id) != tenant_id:
            raise HTTPException(status_code=403, detail="Snapshot belongs to different tenant")
        return snapshot.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_snapshot_failed", snapshot_id=snapshot_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/snapshots/{tenant_id}/{snapshot_id}/verify", dependencies=[Depends(PermissionChecker("audit.read"))])
def verify_snapshot(
    tenant_id: str,
    snapshot_id: str,
    verified_by: str = Query(..., description="User ID performing verification"),
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Verify snapshot integrity.

    Recomputes the SHA-256 hash and compares to stored hash.
    If valid, marks the snapshot as verified with timestamp.

    Returns:
    - is_valid: whether the hash matches
    - stored_hash: the original hash
    - computed_hash: the recomputed hash
    """
    try:
        service = ComplianceServiceSync(session)
        result = service.verify_snapshot_integrity(UUID(snapshot_id), verified_by)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("verify_snapshot_failed", snapshot_id=snapshot_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/snapshots/{tenant_id}/{snapshot_id}/export", dependencies=[Depends(PermissionChecker("audit.export"))])
def export_snapshot(
    tenant_id: str,
    snapshot_id: str,
    format: str = Query("json", description="Export format: json"),
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Export snapshot in audit-ready format.

    Returns a complete export package with:
    - Snapshot metadata
    - Compliance state at time of capture
    - All captured data (status, alerts, profile)
    - Integrity verification with hash
    """
    try:
        service = ComplianceServiceSync(session)
        result = service.export_snapshot(UUID(snapshot_id), format)
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("export_snapshot_failed", snapshot_id=snapshot_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/snapshots/{tenant_id}/{snapshot_id}/audit-pack", dependencies=[Depends(PermissionChecker("audit.read"))])
def get_audit_pack(
    tenant_id: str,
    snapshot_id: str,
    session=Depends(get_session),
) -> Response:
    """Generate and return a Zero-Trust Audit Pack ZIP."""
    service = ComplianceServiceSync(session)
    try:
        content, filename = service.generate_audit_pack(UUID(snapshot_id))
        return Response(
            content=content,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("audit_pack_generation_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/snapshots/{tenant_id}/{snapshot_id}/attest", dependencies=[Depends(PermissionChecker("audit.create"))])
def attest_snapshot(
    tenant_id: str,
    snapshot_id: str,
    request: AttestSnapshotRequest,
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Attest to a snapshot, taking owner accountability.

    This creates a legal binding between the person and the compliance state.
    Once attested:
    - The snapshot becomes a commitment
    - The user's name is permanently attached
    - Alerts bound to this snapshot can be resolved

    Use this ONLY when ready to take personal responsibility for the
    compliance state at the time of capture.
    """
    try:
        service = ComplianceServiceSync(session)
        result = service.attest_snapshot(
            snapshot_id=UUID(snapshot_id),
            attested_by=request.attested_by,
            attestation_title=request.attestation_title,
        )
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("attest_snapshot_failed", snapshot_id=snapshot_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


class RefreezeRequest(BaseModel):
    """Request to re-freeze a stale/invalid snapshot."""
    created_by: str = Field(..., description="User email performing the re-freeze")


@router.post("/snapshots/{tenant_id}/{snapshot_id}/refreeze", dependencies=[Depends(PermissionChecker("audit.create"))])
def refreeze_snapshot(
    tenant_id: str,
    snapshot_id: str,
    request: RefreezeRequest,
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Re-freeze a stale or invalid snapshot.

    Creates a fresh snapshot with current compliance state,
    inheriting the original's trigger alert and regulatory citation.
    Use when a snapshot has degraded but you need fresh evidence.
    """
    try:
        service = ComplianceServiceSync(session)
        snapshot = service.refreeze_snapshot(
            original_snapshot_id=UUID(snapshot_id),
            created_by=request.created_by,
        )
        return snapshot.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("refreeze_snapshot_failed", snapshot_id=snapshot_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/snapshots/{tenant_id}/{snapshot_id}/fda-response", dependencies=[Depends(PermissionChecker("audit.export"))])
def get_fda_response(
    tenant_id: str,
    snapshot_id: str,
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Generate a regulator-grade explanation for FDA response.

    Returns pre-formatted text that can be directly copied
    into a regulatory response document.

    Includes:
    - Formal header with snapshot ID and hash
    - Compliance status at time of capture
    - Alert details
    - Attestation information (if attested)
    - Cryptographic verification statement
    """
    try:
        service = ComplianceServiceSync(session)
        result = service.generate_fda_response(UUID(snapshot_id))
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("generate_fda_response_failed", snapshot_id=snapshot_id, error=str(e))
        logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, detail="Internal server error")
