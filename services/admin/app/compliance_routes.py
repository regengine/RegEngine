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
from fastapi import APIRouter, Depends, HTTPException, Query
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
    - COMPLIANT / AT_RISK / NON_COMPLIANT
    - Active alert count
    - Countdown to next deadline
    - List of active alerts
    """
    try:
        service = ComplianceServiceSync(session)
        status = service.get_status(UUID(tenant_id))
        return ComplianceStatusResponse(**status)
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError) as e:
        logger.exception("get_status_failed", tenant_id=tenant_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/alerts/{tenant_id}", response_model=list[AlertResponse], dependencies=[Depends(PermissionChecker("analysis.read"))])
def list_alerts(
    tenant_id: str,
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE, ACKNOWLEDGED, RESOLVED"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of alerts to return"),
    offset: int = Query(default=0, ge=0, description="Number of alerts to skip"),
    session=Depends(get_session),
) -> List[AlertResponse]:
    """List alerts for a tenant with pagination."""
    try:
        service = ComplianceServiceSync(session)
        alerts = service.get_alerts(
            UUID(tenant_id),
            status_filter=status,
            limit=limit,
            offset=offset,
        )
        return [AlertResponse(**alert.to_dict()) for alert in alerts]
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError) as e:
        logger.exception("list_alerts_failed", tenant_id=tenant_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/alerts/{tenant_id}/{alert_id}", response_model=AlertResponse, dependencies=[Depends(PermissionChecker("analysis.read"))])
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
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError) as e:
        logger.exception("get_alert_failed", alert_id=alert_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/alerts/{tenant_id}/{alert_id}/acknowledge", response_model=AlertResponse, dependencies=[Depends(PermissionChecker("analysis.create"))])
def acknowledge_alert(
    tenant_id: str,
    alert_id: str,
    request: AlertActionRequest,
    session=Depends(get_session),
) -> AlertResponse:
    """Mark an alert as acknowledged."""
    try:
        service = ComplianceServiceSync(session)
        alert = service.acknowledge_alert(UUID(alert_id), request.user_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return AlertResponse(**alert.to_dict())
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError) as e:
        logger.exception("acknowledge_alert_failed", alert_id=alert_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/alerts/{tenant_id}/{alert_id}/resolve", response_model=AlertResponse, dependencies=[Depends(PermissionChecker("analysis.create"))])
def resolve_alert(
    tenant_id: str,
    alert_id: str,
    request: AlertActionRequest,
    session=Depends(get_session),
) -> AlertResponse:
    """Resolve an alert."""
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
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError) as e:
        logger.exception("resolve_alert_failed", alert_id=alert_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/alerts", response_model=AlertResponse, status_code=201, dependencies=[Depends(PermissionChecker("analysis.create"))])
def create_alert(
    request: CreateAlertRequest,
    session=Depends(get_session),
) -> AlertResponse:
    """Manually create a compliance alert."""
    try:
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
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as e:
        logger.exception("create_alert_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/profile/{tenant_id}", response_model=dict[str, Any], dependencies=[Depends(PermissionChecker("analysis.read"))])
def get_product_profile(
    tenant_id: str,
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Get tenant's product profile for alert matching."""
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
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as e:
        logger.exception("get_profile_failed", tenant_id=tenant_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/profile/{tenant_id}", response_model=dict[str, Any], dependencies=[Depends(PermissionChecker("analysis.create"))])
def update_product_profile(
    tenant_id: str,
    request: ProductProfileRequest,
    session=Depends(get_session),
) -> Dict[str, Any]:
    """Update tenant's product profile."""
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
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as e:
        logger.exception("update_profile_failed", tenant_id=tenant_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
