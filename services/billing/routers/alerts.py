"""
Alerts Router — Billing notifications and webhook API.

Endpoints for managing alert rules, viewing events,
acknowledging alerts, and monitoring webhooks.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel
from typing import Optional

from alerts_engine import alerts_engine, AlertType, AlertSeverity, AlertChannel, WebhookStatus
from utils import paginate

router = APIRouter(prefix="/v1/billing/alerts", tags=["Alerts"])


# ── Request Models ─────────────────────────────────────────────────

class CreateRuleRequest(BaseModel):
    name: str
    alert_type: AlertType
    severity: AlertSeverity
    channels: list[AlertChannel]
    threshold: Optional[float] = None
    recipient_emails: list[str] = []
    webhook_url: str = ""


class FireAlertRequest(BaseModel):
    alert_type: AlertType
    title: str
    message: str
    tenant_id: str = ""
    tenant_name: str = ""
    severity: AlertSeverity = AlertSeverity.INFO


# ── Endpoints ──────────────────────────────────────────────────────

@router.get("/rules")
async def list_rules():
    """List alert rules."""
    rules = alerts_engine.list_rules()
    return {"rules": [r.model_dump() for r in rules], "total": len(rules)}


@router.post("/rules")
async def create_rule(request: CreateRuleRequest):
    """Create an alert rule."""
    rule = alerts_engine.create_rule(
        name=request.name, alert_type=request.alert_type,
        severity=request.severity, channels=request.channels,
        threshold=request.threshold, recipient_emails=request.recipient_emails,
        webhook_url=request.webhook_url,
    )
    return {"rule": rule.model_dump(), "message": f"Rule '{request.name}' created"}


@router.post("/rules/{rule_id}/toggle")
async def toggle_rule(rule_id: str = Path(...)):
    """Enable/disable an alert rule."""
    try:
        rule = alerts_engine.toggle_rule(rule_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"rule": rule.model_dump(), "enabled": rule.enabled}


@router.get("/events")
async def list_events(
    alert_type: Optional[AlertType] = Query(None),
    severity: Optional[AlertSeverity] = Query(None),
    unacknowledged: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List alert events with pagination."""
    events = alerts_engine.list_events(
        alert_type=alert_type, severity=severity,
        unacknowledged_only=unacknowledged,
    )
    result = paginate([e.model_dump() for e in events], page=page, page_size=page_size)
    return {
        "events": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
        "has_next": result["has_next"],
        "has_prev": result["has_prev"],
    }


@router.post("/events/{event_id}/acknowledge")
async def acknowledge_event(event_id: str = Path(...)):
    """Acknowledge an alert event."""
    try:
        event = alerts_engine.acknowledge_event(event_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"event": event.model_dump(), "message": "Event acknowledged"}


@router.post("/fire")
async def fire_alert(request: FireAlertRequest):
    """Manually fire an alert."""
    event = alerts_engine.fire_alert(
        alert_type=request.alert_type, title=request.title,
        message=request.message, tenant_id=request.tenant_id,
        tenant_name=request.tenant_name, severity=request.severity,
    )
    return {"event": event.model_dump(), "channels": [c.value for c in event.channels_notified]}


@router.get("/webhooks")
async def list_webhooks(
    status: Optional[WebhookStatus] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List webhook delivery log with pagination."""
    webhooks = alerts_engine.list_webhooks(status=status)
    result = paginate([w.model_dump() for w in webhooks], page=page, page_size=page_size)
    return {
        "webhooks": result["items"],
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "total_pages": result["total_pages"],
        "has_next": result["has_next"],
        "has_prev": result["has_prev"],
    }


@router.get("/summary")
async def alerts_summary():
    """Alerts program overview."""
    return alerts_engine.get_summary()
