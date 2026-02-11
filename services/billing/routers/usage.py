"""
Usage Router — Resource metering and overage tracking API.

Endpoints for recording usage events, retrieving summaries,
breakdowns, and overage notifications.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Path, Query
from pydantic import BaseModel
from typing import Optional

from usage_meter import usage_meter

router = APIRouter(prefix="/v1/billing/usage", tags=["Usage"])


# ── Request Models ─────────────────────────────────────────────────

class RecordUsageRequest(BaseModel):
    resource: str  # document_processing | api_calls | storage_gb
    quantity: int = 1
    metadata: dict = {}


# ── Endpoints ──────────────────────────────────────────────────────

@router.post("/record")
async def record_usage(
    request: RecordUsageRequest,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """Record a usage event for the current tenant."""
    tenant_id = x_tenant_id or "anonymous"

    try:
        event = usage_meter.record(
            tenant_id=tenant_id,
            resource=request.resource,
            quantity=request.quantity,
            metadata=request.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "event_id": event.id,
        "tenant_id": tenant_id,
        "resource": request.resource,
        "quantity": request.quantity,
        "recorded_at": event.recorded_at.isoformat(),
    }


@router.get("/{tenant_id}/summary")
async def usage_summary(
    tenant_id: str = Path(...),
    tier_id: str = Query("growth", description="Subscription tier for allocation lookup"),
):
    """Current billing period usage summary with overage calculations."""
    summary = usage_meter.get_summary(tenant_id, tier_id)
    return {
        "tenant_id": summary.tenant_id,
        "period": {
            "start": summary.period_start.isoformat(),
            "end": summary.period_end.isoformat(),
        },
        "resources": summary.resources,
        "total_overage_cents": summary.total_overage_cents,
        "total_overage_display": summary.total_overage_display,
    }


@router.get("/{tenant_id}/breakdown")
async def usage_breakdown(
    tenant_id: str = Path(...),
    tier_id: str = Query("growth"),
):
    """Detailed per-resource usage breakdown with pricing tiers."""
    return usage_meter.get_breakdown(tenant_id, tier_id)


@router.get("/overage-alerts")
async def overage_alerts():
    """All tenants approaching or exceeding usage limits (≥80%)."""
    alerts = usage_meter.get_overage_alerts()
    return {
        "alerts": alerts,
        "total_alerts": len(alerts),
        "critical_count": sum(1 for a in alerts if a["severity"] == "critical"),
        "warning_count": sum(1 for a in alerts if a["severity"] == "warning"),
    }
