"""
Team Management Router.

Manages team members, roles, and invitations for multi-user
access to the compliance platform.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("team")


def _get_db():
    """Get database session. Returns None if unavailable."""
    try:
        from shared.database import SessionLocal
        return SessionLocal()
    except Exception as exc:
        logger.warning("db_unavailable error=%s", str(exc))
        return None

router = APIRouter(prefix="/api/v1/team", tags=["Team Management"])


class TeamMember(BaseModel):
    """A team member."""
    id: str
    name: str
    email: str
    role: str  # owner, admin, compliance_manager, viewer
    status: str  # active, invited, deactivated
    last_active: Optional[str] = None
    invited_at: Optional[str] = None
    avatar_initials: str = ""
    is_sample: bool = Field(
        default=False,
        description="True for auto-generated sample data. Replace with real team members.",
    )


class InviteRequest(BaseModel):
    """Request to invite a team member."""
    email: str
    name: str
    role: str = "viewer"


class TeamResponse(BaseModel):
    """Team dashboard response."""
    tenant_id: str
    total_members: int
    active_members: int
    pending_invites: int
    roles_breakdown: dict
    members: list[TeamMember]


ROLE_PERMISSIONS = {
    "owner": {
        "label": "Owner",
        "description": "Full access including billing and team management",
        "permissions": ["all"],
    },
    "admin": {
        "label": "Admin",
        "description": "Full access except billing",
        "permissions": ["data", "compliance", "suppliers", "exports", "settings", "team"],
    },
    "compliance_manager": {
        "label": "Compliance Manager",
        "description": "Manage compliance, suppliers, and exports",
        "permissions": ["data", "compliance", "suppliers", "exports"],
    },
    "viewer": {
        "label": "Viewer",
        "description": "Read-only access to dashboards and reports",
        "permissions": ["read"],
    },
}


# In-memory fallback for when DB is unavailable
_team_store: dict[str, list[TeamMember]] = {}


def _db_get_team(tenant_id: str) -> Optional[list[TeamMember]]:
    """Query team members from database."""
    db = _get_db()
    if not db:
        return None
    try:
        rows = db.execute(
            text("SELECT id, name, email, role, status, last_active, invited_at, avatar_initials FROM fsma.tenant_team_members WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        ).fetchall()
        members = []
        for row in rows:
            members.append(TeamMember(
                id=row[0],
                name=row[1],
                email=row[2],
                role=row[3],
                status=row[4],
                last_active=row[5],
                invited_at=row[6],
                avatar_initials=row[7],
                is_sample=False,
            ))
        return members
    except Exception as exc:
        logger.warning("db_read_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _db_add_team_member(tenant_id: str, member: TeamMember) -> bool:
    """Insert team member into database."""
    db = _get_db()
    if not db:
        return False
    try:
        db.execute(
            text("""
                INSERT INTO fsma.tenant_team_members 
                (id, tenant_id, name, email, role, status, last_active, invited_at, avatar_initials, is_sample, created_at, updated_at)
                VALUES (:id, :tid, :name, :email, :role, :status, :active, :invited, :initials, false, now(), now())
                ON CONFLICT (id) DO UPDATE SET 
                    name = :name, email = :email, role = :role, status = :status,
                    last_active = :active, invited_at = :invited, avatar_initials = :initials, updated_at = now()
            """),
            {
                "id": member.id,
                "tid": tenant_id,
                "name": member.name,
                "email": member.email,
                "role": member.role,
                "status": member.status,
                "active": member.last_active,
                "invited": member.invited_at,
                "initials": member.avatar_initials,
            }
        )
        db.commit()
        return True
    except Exception as exc:
        logger.warning("db_write_failed error=%s", str(exc))
        if db:
            db.rollback()
        return False
    finally:
        db.close()


@router.get(
    "/{tenant_id}",
    response_model=TeamResponse,
    summary="Get team members",
)
async def get_team(
    tenant_id: str,
    _: None = Depends(_verify_api_key),
) -> TeamResponse:
    """Get team members for a tenant."""
    # Try DB first
    members = _db_get_team(tenant_id)
    if members is None:
        if tenant_id not in _team_store:
            _team_store[tenant_id] = []
        members = _team_store[tenant_id]
    active = sum(1 for m in members if m.status == "active")
    pending = sum(1 for m in members if m.status == "invited")

    roles: dict[str, int] = {}
    for m in members:
        roles[m.role] = roles.get(m.role, 0) + 1

    return TeamResponse(
        tenant_id=tenant_id,
        total_members=len(members),
        active_members=active,
        pending_invites=pending,
        roles_breakdown=roles,
        members=members,
    )


@router.post(
    "/{tenant_id}/invite",
    summary="Invite a team member",
)
async def invite_member(
    tenant_id: str,
    request: InviteRequest,
    _: None = Depends(_verify_api_key),
):
    """Invite a new team member."""
    # Get current count from DB or memory
    members = _db_get_team(tenant_id)
    if members is None:
        if tenant_id not in _team_store:
            _team_store[tenant_id] = []
        members = _team_store[tenant_id]

    now = datetime.now(timezone.utc)
    member = TeamMember(
        id=f"{tenant_id}-user-{len(members) + 1:03d}",
        name=request.name,
        email=request.email,
        role=request.role,
        status="invited",
        invited_at=now.isoformat(),
        avatar_initials="".join(w[0].upper() for w in request.name.split()[:2]),
    )

    # Try DB first, fall back to memory
    db_success = _db_add_team_member(tenant_id, member)
    if not db_success:
        if tenant_id not in _team_store:
            _team_store[tenant_id] = []
        _team_store[tenant_id].append(member)

    return {"invited": True, "member": member.model_dump()}


@router.put(
    "/{tenant_id}/{member_id}/role",
    summary="Update member role",
)
async def update_role(
    tenant_id: str,
    member_id: str,
    role: str,
    _: None = Depends(_verify_api_key),
):
    """Update a team member's role."""
    # Try DB first
    members = _db_get_team(tenant_id)
    if members is None:
        members = _team_store.get(tenant_id, [])
    
    for member in members:
        if member.id == member_id:
            member.role = role
            
            # Update in DB or memory
            db_success = _db_add_team_member(tenant_id, member)
            if not db_success:
                if tenant_id in _team_store:
                    for mem in _team_store[tenant_id]:
                        if mem.id == member_id:
                            mem.role = role
            
            return {"updated": True, "member_id": member_id, "new_role": role}

    return {"error": "Member not found"}


@router.get(
    "/roles/definitions",
    summary="Get role definitions",
)
async def get_roles():
    """Get role definitions and permissions."""
    return {"roles": ROLE_PERMISSIONS}
