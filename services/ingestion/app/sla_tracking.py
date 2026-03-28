"""
FDA 24-Hour SLA Tracking.

FSMA 204 (21 CFR 1.1455) requires responding to FDA records requests
within 24 hours. This module tracks request lifecycle, computes SLA
compliance metrics, and generates deadline alerts.

Endpoints:
    POST  /api/v1/sla/requests                     — Create a new FDA records request
    GET   /api/v1/sla/requests/{tenant_id}          — List requests for a tenant
    PATCH /api/v1/sla/requests/{request_id}/complete — Mark request completed
    GET   /api/v1/sla/dashboard/{tenant_id}         — SLA compliance dashboard
    GET   /api/v1/sla/alerts/{tenant_id}            — Active SLA alerts
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("sla-tracking")

router = APIRouter(prefix="/api/v1/sla", tags=["SLA Tracking"])

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

RequestType = Literal["records_request", "inspection", "recall"]
RequestStatus = Literal["open", "in_progress", "completed", "overdue"]
AlertType = Literal["deadline_approaching", "overdue", "completed"]

SLA_HOURS = 24
ALERT_THRESHOLD_HOURS = 4  # alert when < 4 hours remain


class FDARequestCreate(BaseModel):
    """Payload for creating a new FDA records request."""
    tenant_id: str
    request_type: RequestType = "records_request"
    notes: Optional[str] = None


class FDARequest(BaseModel):
    """A tracked FDA records request with SLA deadline."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    request_type: RequestType = "records_request"
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deadline_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=SLA_HOURS))
    status: RequestStatus = "open"
    completed_at: Optional[datetime] = None
    export_ids: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @property
    def time_remaining(self) -> Optional[timedelta]:
        if self.status == "completed":
            return None
        return self.deadline_at - datetime.now(timezone.utc)

    @property
    def is_overdue(self) -> bool:
        return self.status != "completed" and datetime.now(timezone.utc) > self.deadline_at

    @property
    def response_hours(self) -> Optional[float]:
        if self.completed_at is None:
            return None
        delta = self.completed_at - self.requested_at
        return delta.total_seconds() / 3600


class SLADashboard(BaseModel):
    """Aggregated SLA compliance metrics for a tenant."""
    tenant_id: str
    open_requests: int = 0
    overdue_requests: int = 0
    avg_response_hours: Optional[float] = None
    compliance_rate_pct: Optional[float] = None
    requests: List[dict] = Field(default_factory=list)


class SLAAlert(BaseModel):
    """An SLA alert for a request approaching or past deadline."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    request_id: str
    alert_type: AlertType
    message: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = False


# ---------------------------------------------------------------------------
# In-memory store (DB fallback pattern)
# ---------------------------------------------------------------------------

_requests_store: Dict[str, FDARequest] = {}
_alerts_store: Dict[str, SLAAlert] = {}


def _refresh_overdue_statuses() -> None:
    """Mark any open/in_progress requests as overdue if deadline has passed."""
    now = datetime.now(timezone.utc)
    for req in _requests_store.values():
        if req.status in ("open", "in_progress") and now > req.deadline_at:
            req.status = "overdue"


def _generate_alerts_for_request(req: FDARequest) -> List[SLAAlert]:
    """Generate alerts for a single request based on its deadline status."""
    alerts: List[SLAAlert] = []
    now = datetime.now(timezone.utc)

    if req.status == "completed":
        return alerts

    remaining = req.deadline_at - now

    if remaining <= timedelta(0):
        # Overdue
        alert = SLAAlert(
            tenant_id=req.tenant_id,
            request_id=req.id,
            alert_type="overdue",
            message=f"FDA {req.request_type} request {req.id} is OVERDUE. "
                    f"Deadline was {req.deadline_at.isoformat()}.",
        )
        alerts.append(alert)
    elif remaining <= timedelta(hours=ALERT_THRESHOLD_HOURS):
        # Approaching deadline
        hours_left = remaining.total_seconds() / 3600
        alert = SLAAlert(
            tenant_id=req.tenant_id,
            request_id=req.id,
            alert_type="deadline_approaching",
            message=f"FDA {req.request_type} request {req.id} deadline in "
                    f"{hours_left:.1f} hours ({req.deadline_at.isoformat()}).",
        )
        alerts.append(alert)

    return alerts


def _request_to_dict(req: FDARequest) -> dict:
    """Serialize request to dict including computed fields."""
    now = datetime.now(timezone.utc)
    remaining = None
    if req.status != "completed":
        remaining_td = req.deadline_at - now
        remaining = max(remaining_td.total_seconds(), 0)

    return {
        "id": req.id,
        "tenant_id": req.tenant_id,
        "request_type": req.request_type,
        "requested_at": req.requested_at.isoformat(),
        "deadline_at": req.deadline_at.isoformat(),
        "status": req.status,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
        "export_ids": req.export_ids,
        "notes": req.notes,
        "time_remaining_seconds": remaining,
        "response_hours": req.response_hours,
    }


def _try_persist_request(req: FDARequest) -> None:
    """Best-effort persist to DB; log and continue on failure."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            db.execute(
                text("""
                    INSERT INTO fsma.fda_sla_requests
                        (id, tenant_id, request_type, requested_at, deadline_at,
                         status, completed_at, export_ids, notes)
                    VALUES
                        (:id, :tenant_id, :request_type, :requested_at, :deadline_at,
                         :status, :completed_at, :export_ids, :notes)
                    ON CONFLICT (id) DO UPDATE SET
                        status = EXCLUDED.status,
                        completed_at = EXCLUDED.completed_at,
                        export_ids = EXCLUDED.export_ids,
                        notes = EXCLUDED.notes
                """),
                {
                    "id": req.id,
                    "tenant_id": req.tenant_id,
                    "request_type": req.request_type,
                    "requested_at": req.requested_at,
                    "deadline_at": req.deadline_at,
                    "status": req.status,
                    "completed_at": req.completed_at,
                    "export_ids": ",".join(req.export_ids) if req.export_ids else None,
                    "notes": req.notes,
                },
            )
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.debug("DB persist skipped (in-memory fallback): %s", exc)


def _try_load_requests(tenant_id: str) -> Optional[List[FDARequest]]:
    """Try loading requests from DB; return None if unavailable."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            rows = db.execute(
                text("""
                    SELECT id, tenant_id, request_type, requested_at, deadline_at,
                           status, completed_at, export_ids, notes
                    FROM fsma.fda_sla_requests
                    WHERE tenant_id = :tenant_id
                    ORDER BY requested_at DESC
                """),
                {"tenant_id": tenant_id},
            ).fetchall()

            requests = []
            for row in rows:
                export_ids = row.export_ids.split(",") if row.export_ids else []
                req = FDARequest(
                    id=row.id,
                    tenant_id=row.tenant_id,
                    request_type=row.request_type,
                    requested_at=row.requested_at,
                    deadline_at=row.deadline_at,
                    status=row.status,
                    completed_at=row.completed_at,
                    export_ids=export_ids,
                    notes=row.notes,
                )
                # Sync back to in-memory store
                _requests_store[req.id] = req
                requests.append(req)
            return requests
        finally:
            db.close()
    except Exception as exc:
        logger.debug("DB load skipped (in-memory fallback): %s", exc)
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/requests", summary="Create FDA records request")
async def create_request(
    body: FDARequestCreate,
    _auth: None = Depends(_verify_api_key),
):
    """Start the 24-hour SLA clock for a new FDA records request."""
    now = datetime.now(timezone.utc)
    req = FDARequest(
        tenant_id=body.tenant_id,
        request_type=body.request_type,
        requested_at=now,
        deadline_at=now + timedelta(hours=SLA_HOURS),
        notes=body.notes,
    )
    _requests_store[req.id] = req
    _try_persist_request(req)

    logger.info(
        "SLA request created: %s (tenant=%s, type=%s, deadline=%s)",
        req.id, req.tenant_id, req.request_type, req.deadline_at.isoformat(),
    )

    return {
        "status": "created",
        "request": _request_to_dict(req),
    }


@router.get("/requests/{tenant_id}", summary="List FDA requests for tenant")
async def list_requests(
    tenant_id: str,
    status_filter: Optional[RequestStatus] = Query(None, alias="status"),
    _auth: None = Depends(_verify_api_key),
):
    """List all FDA records requests for a tenant with current status."""
    _refresh_overdue_statuses()

    # Try DB first, fall back to in-memory
    db_requests = _try_load_requests(tenant_id)
    if db_requests is not None:
        requests = db_requests
    else:
        requests = [r for r in _requests_store.values() if r.tenant_id == tenant_id]

    if status_filter:
        requests = [r for r in requests if r.status == status_filter]

    return {
        "tenant_id": tenant_id,
        "count": len(requests),
        "requests": [_request_to_dict(r) for r in requests],
    }


@router.patch("/requests/{request_id}/complete", summary="Mark request completed")
async def complete_request(
    request_id: str,
    export_ids: Optional[List[str]] = Query(None),
    _auth: None = Depends(_verify_api_key),
):
    """Mark an FDA records request as completed, recording response time."""
    req = _requests_store.get(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"Request {request_id} not found")

    now = datetime.now(timezone.utc)
    req.status = "completed"
    req.completed_at = now
    if export_ids:
        req.export_ids.extend(export_ids)

    _try_persist_request(req)

    response_hours = req.response_hours
    met_sla = response_hours is not None and response_hours <= SLA_HOURS

    # Generate completion alert
    alert = SLAAlert(
        tenant_id=req.tenant_id,
        request_id=req.id,
        alert_type="completed",
        message=f"FDA {req.request_type} request {req.id} completed in "
                f"{response_hours:.1f}h. SLA {'MET' if met_sla else 'MISSED'}.",
    )
    _alerts_store[alert.id] = alert

    logger.info(
        "SLA request completed: %s (response_hours=%.1f, met_sla=%s)",
        req.id, response_hours or 0, met_sla,
    )

    return {
        "status": "completed",
        "request": _request_to_dict(req),
        "met_sla": met_sla,
    }


@router.get("/dashboard/{tenant_id}", summary="SLA compliance dashboard")
async def sla_dashboard(
    tenant_id: str,
    _auth: None = Depends(_verify_api_key),
):
    """Compute SLA compliance metrics for a tenant."""
    _refresh_overdue_statuses()

    # Try DB first, fall back to in-memory
    db_requests = _try_load_requests(tenant_id)
    if db_requests is not None:
        requests = db_requests
    else:
        requests = [r for r in _requests_store.values() if r.tenant_id == tenant_id]

    open_count = sum(1 for r in requests if r.status in ("open", "in_progress"))
    overdue_count = sum(1 for r in requests if r.status == "overdue")

    # Compute average response time for completed requests
    completed = [r for r in requests if r.status == "completed" and r.response_hours is not None]
    avg_hours = None
    compliance_rate = None
    if completed:
        avg_hours = sum(r.response_hours for r in completed) / len(completed)
        met_sla = sum(1 for r in completed if r.response_hours <= SLA_HOURS)
        compliance_rate = (met_sla / len(completed)) * 100

    dashboard = SLADashboard(
        tenant_id=tenant_id,
        open_requests=open_count,
        overdue_requests=overdue_count,
        avg_response_hours=round(avg_hours, 2) if avg_hours is not None else None,
        compliance_rate_pct=round(compliance_rate, 1) if compliance_rate is not None else None,
        requests=[_request_to_dict(r) for r in requests],
    )

    return dashboard.model_dump()


@router.get("/alerts/{tenant_id}", summary="Active SLA alerts")
async def list_alerts(
    tenant_id: str,
    include_acknowledged: bool = Query(False),
    _auth: None = Depends(_verify_api_key),
):
    """List active SLA alerts, generating real-time deadline alerts."""
    _refresh_overdue_statuses()

    # Generate real-time alerts from current request state
    live_alerts: List[SLAAlert] = []
    requests = [r for r in _requests_store.values() if r.tenant_id == tenant_id]
    for req in requests:
        live_alerts.extend(_generate_alerts_for_request(req))

    # Merge with stored alerts (e.g., completion alerts)
    stored = [a for a in _alerts_store.values() if a.tenant_id == tenant_id]
    if not include_acknowledged:
        stored = [a for a in stored if not a.acknowledged]

    all_alerts = live_alerts + stored

    return {
        "tenant_id": tenant_id,
        "count": len(all_alerts),
        "alerts": [a.model_dump() for a in all_alerts],
    }
