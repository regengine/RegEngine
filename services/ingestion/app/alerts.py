"""
Alerts Router.

Automated compliance alerts and notifications system. Monitors
traceability events and triggers alerts for:
- Missing KDEs
- Overdue CTE entries
- Temperature excursions
- Chain integrity failures
- Supplier portal link expiry
- FDA records request deadline approaching
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("alerts")

router = APIRouter(prefix="/api/v1/alerts", tags=["Alerts & Notifications"])


class AlertRule(BaseModel):
    """Alert rule definition."""
    id: str
    name: str
    category: str  # compliance, temperature, chain, deadline
    severity: str  # critical, warning, info
    description: str
    enabled: bool = True
    notify_email: bool = True
    notify_webhook: bool = False
    threshold: Optional[str] = None


class Alert(BaseModel):
    """A triggered alert instance."""
    id: str
    rule_id: str
    rule_name: str
    severity: str
    category: str
    title: str
    message: str
    triggered_at: str
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class AlertsResponse(BaseModel):
    """Response with alerts list."""
    tenant_id: str
    total: int
    unacknowledged: int
    alerts: list[Alert]


# Default rules
DEFAULT_RULES: list[AlertRule] = [
    AlertRule(
        id="kde-missing",
        name="Missing Key Data Elements",
        category="compliance",
        severity="warning",
        description="Triggered when a CTE event is missing required KDEs per 21 CFR 1.1325-1.1350",
    ),
    AlertRule(
        id="cte-overdue",
        name="Overdue CTE Entry",
        category="compliance",
        severity="warning",
        description="Triggered when expected CTE entries (Shipping, Receiving) are not recorded within the configured time window",
        threshold="4 hours",
    ),
    AlertRule(
        id="temp-excursion",
        name="Temperature Excursion",
        category="temperature",
        severity="critical",
        description="Triggered when IoT temperature data exceeds safe thresholds for the product type",
        threshold="5°C",
    ),
    AlertRule(
        id="chain-integrity",
        name="Hash Chain Break",
        category="chain",
        severity="critical",
        description="Triggered when SHA-256 hash chain verification detects a gap or mismatch",
    ),
    AlertRule(
        id="portal-expiry",
        name="Supplier Portal Link Expiring",
        category="deadline",
        severity="info",
        description="Triggered 48 hours before a supplier portal link expires",
        threshold="48 hours",
    ),
    AlertRule(
        id="fda-deadline",
        name="FDA Records Request Deadline",
        category="deadline",
        severity="critical",
        description="Triggered when an active mock audit drill is within 4 hours of the 24-hour deadline",
        threshold="4 hours",
    ),
    AlertRule(
        id="compliance-drop",
        name="Compliance Score Drop",
        category="compliance",
        severity="warning",
        description="Triggered when compliance score drops below the configured threshold",
        threshold="Grade C",
    ),
    AlertRule(
        id="event-volume-spike",
        name="Event Volume Anomaly",
        category="compliance",
        severity="info",
        description="Triggered when daily event volume deviates significantly from the 7-day average",
        threshold="2x average",
    ),
]

# In-memory storage
_alerts_store: dict[str, list[Alert]] = {}


# Sample alerts for demo (generated per tenant on first request)
def _generate_sample_alerts(tenant_id: str) -> list[Alert]:
    now = datetime.now(timezone.utc)
    return [
        Alert(
            id=f"{tenant_id}-alert-001",
            rule_id="kde-missing",
            rule_name="Missing Key Data Elements",
            severity="warning",
            category="compliance",
            title="Missing GLN on Receiving CTE",
            message="Receiving event for TLC ROM-0226-A1-001 is missing the ship-from GLN. Required per 21 CFR 1.1345(a)(3).",
            triggered_at=(now - timedelta(hours=2)).isoformat(),
            metadata={"tlc": "ROM-0226-A1-001", "missing_kde": "ship_from_gln", "cte_type": "receiving"},
        ),
        Alert(
            id=f"{tenant_id}-alert-002",
            rule_id="temp-excursion",
            rule_name="Temperature Excursion",
            severity="critical",
            category="temperature",
            title="Temperature Excursion — Atlantic Salmon",
            message="IoT sensor detected temperature of 8.2°C for SAL-0226-B1-007 (threshold: 5°C). Product may need quarantine assessment.",
            triggered_at=(now - timedelta(minutes=45)).isoformat(),
            metadata={"tlc": "SAL-0226-B1-007", "temperature": 8.2, "threshold": 5.0, "sensor_id": "TT-2026-003"},
        ),
        Alert(
            id=f"{tenant_id}-alert-003",
            rule_id="cte-overdue",
            rule_name="Overdue CTE Entry",
            severity="warning",
            category="compliance",
            title="Receiving CTE Overdue — Shipment #SHP-20260226-04",
            message="Expected Receiving CTE for shipment SHP-20260226-04 (Roma Tomatoes) has not been recorded. Shipment departed 6 hours ago.",
            triggered_at=(now - timedelta(hours=1)).isoformat(),
            metadata={"shipment_id": "SHP-20260226-04", "product": "Roma Tomatoes", "departed_hours_ago": 6},
        ),
        Alert(
            id=f"{tenant_id}-alert-004",
            rule_id="compliance-drop",
            rule_name="Compliance Score Drop",
            severity="warning",
            category="compliance",
            title="Compliance Score Dropped to C",
            message="Your compliance readiness score has dropped from B (82%) to C (71%). Primary factor: KDE completeness decreased due to missing GLN records.",
            triggered_at=(now - timedelta(hours=5)).isoformat(),
            acknowledged=True,
            acknowledged_at=(now - timedelta(hours=4)).isoformat(),
            acknowledged_by="jsmith@example.com",
            metadata={"previous_grade": "B", "current_grade": "C", "primary_factor": "kde_completeness"},
        ),
        Alert(
            id=f"{tenant_id}-alert-005",
            rule_id="portal-expiry",
            rule_name="Supplier Portal Link Expiring",
            severity="info",
            category="deadline",
            title="Supplier Link Expiring — Valley Fresh Farms",
            message="Portal link for supplier 'Valley Fresh Farms' expires in 36 hours. 3 of 5 pending submissions not yet received.",
            triggered_at=(now - timedelta(hours=12)).isoformat(),
            metadata={"supplier": "Valley Fresh Farms", "hours_remaining": 36, "pending_submissions": 3},
        ),
    ]


@router.get(
    "/{tenant_id}",
    response_model=AlertsResponse,
    summary="Get alerts for a tenant",
    description="Returns all alerts for the given tenant, ordered by most recent first.",
)
async def get_alerts(
    tenant_id: str,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    _: None = Depends(_verify_api_key),
) -> AlertsResponse:
    """Get alerts for a tenant with optional filtering."""
    if tenant_id not in _alerts_store:
        _alerts_store[tenant_id] = _generate_sample_alerts(tenant_id)

    alerts = _alerts_store[tenant_id]

    # Apply filters
    if severity:
        alerts = [a for a in alerts if a.severity == severity]
    if category:
        alerts = [a for a in alerts if a.category == category]
    if acknowledged is not None:
        alerts = [a for a in alerts if a.acknowledged == acknowledged]

    # Sort by most recent first
    alerts.sort(key=lambda a: a.triggered_at, reverse=True)

    unack = sum(1 for a in _alerts_store[tenant_id] if not a.acknowledged)

    return AlertsResponse(
        tenant_id=tenant_id,
        total=len(alerts),
        unacknowledged=unack,
        alerts=alerts,
    )


@router.post(
    "/{tenant_id}/{alert_id}/acknowledge",
    summary="Acknowledge an alert",
)
async def acknowledge_alert(
    tenant_id: str,
    alert_id: str,
    _: None = Depends(_verify_api_key),
):
    """Mark an alert as acknowledged."""
    if tenant_id not in _alerts_store:
        raise HTTPException(status_code=404, detail="Tenant not found")

    for alert in _alerts_store[tenant_id]:
        if alert.id == alert_id:
            alert.acknowledged = True
            alert.acknowledged_at = datetime.now(timezone.utc).isoformat()
            return {"acknowledged": True, "alert_id": alert_id}

    raise HTTPException(status_code=404, detail="Alert not found")


@router.get(
    "/{tenant_id}/rules",
    summary="Get alert rules",
    description="Returns the alert rules configured for the tenant.",
)
async def get_alert_rules(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
):
    """Get alert rules for a tenant."""
    return {"tenant_id": tenant_id, "rules": [r.model_dump() for r in DEFAULT_RULES]}


@router.get(
    "/{tenant_id}/summary",
    summary="Get alert summary",
    description="Returns a summary of alert counts by severity and category.",
)
async def get_alert_summary(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
):
    """Get alert summary for dashboard widgets."""
    if tenant_id not in _alerts_store:
        _alerts_store[tenant_id] = _generate_sample_alerts(tenant_id)

    alerts = _alerts_store[tenant_id]

    # Count by severity
    by_severity = {}
    for a in alerts:
        by_severity[a.severity] = by_severity.get(a.severity, 0) + 1

    # Count by category
    by_category = {}
    for a in alerts:
        by_category[a.category] = by_category.get(a.category, 0) + 1

    unack = sum(1 for a in alerts if not a.acknowledged)

    return {
        "tenant_id": tenant_id,
        "total": len(alerts),
        "unacknowledged": unack,
        "by_severity": by_severity,
        "by_category": by_category,
    }
