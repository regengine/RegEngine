"""
Incident Command Router — Real-Time Recall Coordination.

Goes beyond the request-response workflow with real-time operational
coordination during active recall events. This is the "war room" layer.

Concepts:
    Incident: An active recall event that may span multiple request cases,
              facilities, and products. Has a commander, status timeline,
              and coordinated actions across teams.

    Action Item: A discrete task within an incident (e.g., "contact supplier X",
                 "pull lot Y from shelf Z", "notify retailer W").

    Status Update: Timestamped progress note visible to all incident participants.

Endpoints:
    GET    /api/v1/incidents                       — List active incidents
    POST   /api/v1/incidents                       — Open incident
    GET    /api/v1/incidents/{id}                   — Incident detail + timeline
    PATCH  /api/v1/incidents/{id}/status            — Update incident status
    POST   /api/v1/incidents/{id}/actions           — Add action item
    PATCH  /api/v1/incidents/{id}/actions/{aid}      — Update action item
    POST   /api/v1/incidents/{id}/updates           — Post status update
    GET    /api/v1/incidents/{id}/impact             — Impact assessment
    POST   /api/v1/incidents/{id}/close              — Close incident
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from shared.pagination import PaginationParams
from app.authz import require_permission, IngestionPrincipal
from app.tenant_validation import validate_tenant_id
from shared.database import get_db_session

logger = logging.getLogger("incident-command")

router = APIRouter(prefix="/api/v1/incidents", tags=["Incident Command"])

# Defense-in-depth: whitelist of columns allowed in dynamic WHERE clauses.
# All filter columns are hardcoded in endpoint logic below — this assertion
# catches regressions if a future change introduces an unsafe column reference.
_ALLOWED_WHERE_FRAGMENTS = frozenset({
    "tenant_id = :tid",
    "data->>'status' = :status",
})


def _resolve_tenant(tenant_id: Optional[str], principal: IngestionPrincipal) -> str:
    tid = tenant_id or principal.tenant_id
    if not tid:
        raise HTTPException(status_code=400, detail="Tenant context required")
    validate_tenant_id(tid)
    return tid


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class OpenIncidentRequest(BaseModel):
    title: str
    severity: str = "critical"  # critical, major, minor
    incident_type: str = "recall"  # recall, contamination, allergen, foreign_object
    commander: str
    description: Optional[str] = None
    affected_products: List[str] = Field(default_factory=list)
    affected_lots: List[str] = Field(default_factory=list)
    affected_facilities: List[str] = Field(default_factory=list)
    linked_request_case_ids: List[str] = Field(default_factory=list)


class UpdateStatusRequest(BaseModel):
    status: str  # active, contained, monitoring, resolved, closed


class AddActionRequest(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_to: str
    priority: str = "high"  # critical, high, medium, low
    due_hours: Optional[int] = None


class UpdateActionRequest(BaseModel):
    status: Optional[str] = None  # pending, in_progress, completed, blocked
    notes: Optional[str] = None


class PostUpdateRequest(BaseModel):
    author: str
    message: str
    update_type: str = "progress"  # progress, escalation, resolution, external_comms


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    summary="List incidents",
)
async def list_incidents(
    tenant_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    pagination: PaginationParams = Depends(),
    principal: IngestionPrincipal = Depends(require_permission("incidents.read")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)

    # Use JSONB storage in a general-purpose table for incident data
    # This avoids adding another migration — incidents are stored as JSONB
    # in a lightweight incidents table (created on first use)
    _ensure_incidents_table(db_session)

    where_parts = ["tenant_id = :tid"]
    params: Dict[str, Any] = {"tid": tid}
    if status:
        where_parts.append("data->>'status' = :status")
        params["status"] = status

    assert all(p in _ALLOWED_WHERE_FRAGMENTS for p in where_parts), (
        f"Unexpected WHERE fragment in incident query: {where_parts}"
    )
    where = " AND ".join(where_parts)

    # WHERE clause is built from _ALLOWED_WHERE_FRAGMENTS only (asserted above)
    count_row = db_session.execute(
        text("SELECT COUNT(*) FROM fsma.incidents WHERE " + where),
        params,
    ).fetchone()
    total = count_row[0] if count_row else 0

    params["lim"] = pagination.limit
    params["off"] = pagination.skip

    rows = db_session.execute(
        text(
            "SELECT id, data, created_at, updated_at"
            " FROM fsma.incidents"
            " WHERE " + where +
            " ORDER BY created_at DESC"
            " LIMIT :lim OFFSET :off"
        ),
        params,
    ).fetchall()

    incidents = []
    for r in rows:
        data = r[1] if isinstance(r[1], dict) else json.loads(r[1] or "{}")
        data["incident_id"] = str(r[0])
        data["created_at"] = r[2].isoformat() if r[2] else None
        data["updated_at"] = r[3].isoformat() if r[3] else None
        incidents.append(data)

    return {"tenant_id": tid, "incidents": incidents, "total": total, "skip": pagination.skip, "limit": pagination.limit}


@router.post(
    "",
    summary="Open new incident",
    status_code=201,
)
async def open_incident(
    body: OpenIncidentRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("incidents.write")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    _ensure_incidents_table(db_session)

    incident_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()

    data = {
        "title": body.title,
        "severity": body.severity,
        "incident_type": body.incident_type,
        "status": "active",
        "commander": body.commander,
        "description": body.description,
        "affected_products": body.affected_products,
        "affected_lots": body.affected_lots,
        "affected_facilities": body.affected_facilities,
        "linked_request_case_ids": body.linked_request_case_ids,
        "opened_at": now,
        "actions": [],
        "updates": [
            {
                "id": str(uuid4()),
                "timestamp": now,
                "author": body.commander,
                "message": f"Incident opened: {body.title}",
                "update_type": "progress",
            }
        ],
    }

    db_session.execute(
        text("""
            INSERT INTO fsma.incidents (id, tenant_id, data)
            VALUES (:id, :tid, :data::jsonb)
        """),
        {"id": incident_id, "tid": tid, "data": json.dumps(data, default=str)},
    )

    return {"incident_id": incident_id, "status": "active"}


@router.get(
    "/{incident_id}",
    summary="Incident detail with timeline",
)
async def get_incident(
    incident_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("incidents.read")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    _ensure_incidents_table(db_session)

    row = db_session.execute(
        text("SELECT id, data, created_at, updated_at FROM fsma.incidents WHERE id = :id AND tenant_id = :tid"),
        {"id": incident_id, "tid": tid},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")

    data = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
    data["incident_id"] = str(row[0])
    data["created_at"] = row[2].isoformat() if row[2] else None
    data["updated_at"] = row[3].isoformat() if row[3] else None

    return data


@router.patch(
    "/{incident_id}/status",
    summary="Update incident status",
)
async def update_status(
    incident_id: str,
    body: UpdateStatusRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("incidents.write")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    data = _get_incident_data(db_session, incident_id, tid)

    data["status"] = body.status
    data["updates"].append({
        "id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "author": "system",
        "message": f"Status changed to: {body.status}",
        "update_type": "progress",
    })

    _save_incident_data(db_session, incident_id, tid, data)
    return {"incident_id": incident_id, "status": body.status}


@router.post(
    "/{incident_id}/actions",
    summary="Add action item",
    status_code=201,
)
async def add_action(
    incident_id: str,
    body: AddActionRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("incidents.write")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    data = _get_incident_data(db_session, incident_id, tid)

    action_id = str(uuid4())
    now = datetime.now(timezone.utc)

    action = {
        "id": action_id,
        "title": body.title,
        "description": body.description,
        "assigned_to": body.assigned_to,
        "priority": body.priority,
        "status": "pending",
        "created_at": now.isoformat(),
        "due_at": (now.replace(hour=now.hour + (body.due_hours or 4))).isoformat() if body.due_hours else None,
        "notes": [],
    }

    data["actions"].append(action)
    data["updates"].append({
        "id": str(uuid4()),
        "timestamp": now.isoformat(),
        "author": "system",
        "message": f"Action added: {body.title} (assigned to {body.assigned_to})",
        "update_type": "progress",
    })

    _save_incident_data(db_session, incident_id, tid, data)
    return {"action_id": action_id, "status": "pending"}


@router.patch(
    "/{incident_id}/actions/{action_id}",
    summary="Update action item",
)
async def update_action(
    incident_id: str,
    action_id: str,
    body: UpdateActionRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("incidents.write")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    data = _get_incident_data(db_session, incident_id, tid)

    action = next((a for a in data.get("actions", []) if a["id"] == action_id), None)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    if body.status:
        action["status"] = body.status
    if body.notes:
        action.setdefault("notes", []).append({
            "text": body.notes,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    _save_incident_data(db_session, incident_id, tid, data)
    return {"action_id": action_id, "status": action["status"]}


@router.post(
    "/{incident_id}/updates",
    summary="Post status update",
    status_code=201,
)
async def post_update(
    incident_id: str,
    body: PostUpdateRequest,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("incidents.write")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    data = _get_incident_data(db_session, incident_id, tid)

    update_id = str(uuid4())
    data["updates"].append({
        "id": update_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "author": body.author,
        "message": body.message,
        "update_type": body.update_type,
    })

    _save_incident_data(db_session, incident_id, tid, data)
    return {"update_id": update_id}


@router.get(
    "/{incident_id}/impact",
    summary="Impact assessment",
    description="Cross-reference incident scope against canonical records to assess impact breadth.",
)
async def impact_assessment(
    incident_id: str,
    tenant_id: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("incidents.read")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    data = _get_incident_data(db_session, incident_id, tid)

    affected_lots = data.get("affected_lots", [])
    affected_facilities = data.get("affected_facilities", [])

    # Count affected records
    record_count = 0
    if affected_lots:
        if len(affected_lots) > 1000:
            raise HTTPException(status_code=400, detail="Too many affected lots for impact query")
        placeholders = ", ".join(f":lot_{i}" for i in range(len(affected_lots)))
        params = {f"lot_{i}": lot for i, lot in enumerate(affected_lots)}
        params["tid"] = tid
        # placeholders are ":lot_0, :lot_1, ..." — parameterized, not user input
        record_count = db_session.execute(
            text(
                "SELECT COUNT(*) FROM fsma.traceability_events"
                " WHERE tenant_id = :tid AND traceability_lot_code IN (" + placeholders + ")"
            ),
            params,
        ).scalar() or 0

    # Count affected exceptions
    exception_count = 0
    if affected_lots:
        exception_count = db_session.execute(
            text("""
                SELECT COUNT(*) FROM fsma.exception_cases
                WHERE tenant_id = :tid AND status NOT IN ('resolved', 'waived')
            """),
            {"tid": tid},
        ).scalar() or 0

    actions = data.get("actions", [])
    completed_actions = sum(1 for a in actions if a.get("status") == "completed")

    return {
        "incident_id": incident_id,
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "impact": {
            "affected_lots": len(affected_lots),
            "affected_facilities": len(affected_facilities),
            "affected_products": len(data.get("affected_products", [])),
            "affected_records": record_count,
            "open_exceptions": exception_count,
        },
        "response": {
            "total_actions": len(actions),
            "completed_actions": completed_actions,
            "pending_actions": len(actions) - completed_actions,
            "status_updates": len(data.get("updates", [])),
        },
        "status": data.get("status", "unknown"),
    }


@router.post(
    "/{incident_id}/close",
    summary="Close incident",
)
async def close_incident(
    incident_id: str,
    tenant_id: Optional[str] = Query(None),
    closed_by: str = Query("system"),
    closure_notes: Optional[str] = Query(None),
    principal: IngestionPrincipal = Depends(require_permission("incidents.write")),
    db_session=Depends(get_db_session),
):
    if db_session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")

    tid = _resolve_tenant(tenant_id, principal)
    data = _get_incident_data(db_session, incident_id, tid)

    now = datetime.now(timezone.utc).isoformat()
    data["status"] = "closed"
    data["closed_at"] = now
    data["closed_by"] = closed_by
    data["closure_notes"] = closure_notes
    data["updates"].append({
        "id": str(uuid4()),
        "timestamp": now,
        "author": closed_by,
        "message": f"Incident closed. {closure_notes or ''}".strip(),
        "update_type": "resolution",
    })

    _save_incident_data(db_session, incident_id, tid, data)
    return {"incident_id": incident_id, "status": "closed"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_incidents_table(db_session) -> None:
    """Create the incidents table if it doesn't exist (lightweight, JSONB-based)."""
    db_session.execute(text("""
        CREATE TABLE IF NOT EXISTS fsma.incidents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))
    db_session.execute(text("""
        CREATE INDEX IF NOT EXISTS idx_incidents_tenant
            ON fsma.incidents (tenant_id)
    """))


def _get_incident_data(db_session, incident_id: str, tenant_id: str) -> dict:
    _ensure_incidents_table(db_session)
    row = db_session.execute(
        text("SELECT data FROM fsma.incidents WHERE id = :id AND tenant_id = :tid"),
        {"id": incident_id, "tid": tenant_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Incident not found")
    return row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")


def _save_incident_data(db_session, incident_id: str, tenant_id: str, data: dict) -> None:
    db_session.execute(
        text("""
            UPDATE fsma.incidents
            SET data = :data::jsonb, updated_at = NOW()
            WHERE id = :id AND tenant_id = :tid
        """),
        {"id": incident_id, "tid": tenant_id, "data": json.dumps(data, default=str)},
    )
