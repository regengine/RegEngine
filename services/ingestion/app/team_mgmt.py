"""
Team Management Router.

Manages team members, roles, and invitations for multi-user
access to the compliance platform.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.webhook_compat import _verify_api_key

logger = logging.getLogger("team")

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


def _generate_sample_team(tenant_id: str) -> list[TeamMember]:
    now = datetime.now(timezone.utc)
    return [
        TeamMember(
            id=f"{tenant_id}-user-001", name="Jordan Smith", email="jsmith@example.com",
            role="owner", status="active", last_active=(now - timedelta(minutes=5)).isoformat(),
            avatar_initials="JS",
        ),
        TeamMember(
            id=f"{tenant_id}-user-002", name="Alex Chen", email="achen@example.com",
            role="admin", status="active", last_active=(now - timedelta(hours=2)).isoformat(),
            avatar_initials="AC",
        ),
        TeamMember(
            id=f"{tenant_id}-user-003", name="Maria Garcia", email="mgarcia@example.com",
            role="compliance_manager", status="active", last_active=(now - timedelta(days=1)).isoformat(),
            avatar_initials="MG",
        ),
        TeamMember(
            id=f"{tenant_id}-user-004", name="Taylor Williams", email="twill@example.com",
            role="viewer", status="active", last_active=(now - timedelta(days=3)).isoformat(),
            avatar_initials="TW",
        ),
        TeamMember(
            id=f"{tenant_id}-user-005", name="Chris Lee", email="clee@example.com",
            role="compliance_manager", status="invited",
            invited_at=(now - timedelta(days=1)).isoformat(),
            avatar_initials="CL",
        ),
    ]


_team_store: dict[str, list[TeamMember]] = {}


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
    if tenant_id not in _team_store:
        _team_store[tenant_id] = _generate_sample_team(tenant_id)

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
    if tenant_id not in _team_store:
        _team_store[tenant_id] = _generate_sample_team(tenant_id)

    now = datetime.now(timezone.utc)
    member = TeamMember(
        id=f"{tenant_id}-user-{len(_team_store[tenant_id]) + 1:03d}",
        name=request.name,
        email=request.email,
        role=request.role,
        status="invited",
        invited_at=now.isoformat(),
        avatar_initials="".join(w[0].upper() for w in request.name.split()[:2]),
    )

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
    if tenant_id not in _team_store:
        return {"error": "Tenant not found"}

    for member in _team_store[tenant_id]:
        if member.id == member_id:
            member.role = role
            return {"updated": True, "member_id": member_id, "new_role": role}

    return {"error": "Member not found"}


@router.get(
    "/roles/definitions",
    summary="Get role definitions",
)
async def get_roles():
    """Get role definitions and permissions."""
    return {"roles": ROLE_PERMISSIONS}
