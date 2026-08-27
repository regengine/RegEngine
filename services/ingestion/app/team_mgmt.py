"""
Team Management Router.

Manages team members, roles, and invitations for multi-user
access to the compliance platform.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from shared.database import get_db_safe
from shared.tenant_context import TenantContext
from sqlalchemy import text

from .webhook_compat import require_tenant_context

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
    db = get_db_safe()
    if not db:
        return None
    try:
        rows = db.execute(
            text(
                "SELECT id, name, email, role, status, last_active, invited_at FROM fsma.tenant_team_members WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        ).fetchall()
        members = []
        for row in rows:
            name = row[1]
            initials = "".join(w[0].upper() for w in name.split()[:2]) if name else ""
            members.append(
                TeamMember(
                    id=row[0],
                    name=name,
                    email=row[2],
                    role=row[3],
                    status=row[4],
                    last_active=row[5],
                    invited_at=row[6],
                    avatar_initials=initials,
                    is_sample=False,
                )
            )

        # Auth memberships are the canonical signed-in-operator roster, but
        # they live in public.memberships — fsma.tenant_team_members only
        # holds explicitly invited/sample rows, so real accounts (including
        # the tenant's own founder login) rendered as "0 active" on the Team
        # page. Merge both sources, keyed by email; explicit team rows win.
        try:
            # fsma.get_team_roster (v109) is SECURITY DEFINER: a direct JOIN
            # to public.users returns zero rows under the enforced-RLS app
            # role because user_self_isolation keys on the regengine.user_id
            # GUC, which this service never sets. The function reads with
            # definer rights but is tenant-fail-closed (raises unless the
            # requested tenant matches the session's app.tenant_id context).
            auth_rows = db.execute(
                text("SELECT * FROM fsma.get_team_roster(CAST(:tid AS uuid))"),
                {"tid": tenant_id},
            ).fetchall()
        except Exception as exc:
            # Non-UUID tenant ids (dev slugs), a pre-v109 schema, or a
            # missing tenant context degrade to the explicit-team rows
            # rather than failing the page.
            logger.warning("membership_read_failed error=%s", str(exc))
            auth_rows = []

        seen_emails = {m.email.lower() for m in members if m.email}
        for row in auth_rows:
            email = row[1] or ""
            if email.lower() in seen_emails:
                continue
            display = email.split("@")[0].replace(".", " ").title() if email else "Member"
            initials = "".join(w[0].upper() for w in display.split()[:2]) if display else ""
            members.append(
                TeamMember(
                    id=row[0],
                    name=display,
                    email=email,
                    role=(row[2] or "Member").lower(),
                    status=row[3],
                    last_active=row[4],
                    invited_at=row[5],
                    avatar_initials=initials,
                    is_sample=False,
                )
            )
        return members
    except Exception as exc:
        logger.warning("db_read_failed error=%s", str(exc))
        return None
    finally:
        db.close()


def _db_add_team_member(tenant_id: str, member: TeamMember) -> bool:
    """Insert team member into database."""
    db = get_db_safe()
    if not db:
        return False
    try:
        db.execute(
            text("""
                INSERT INTO fsma.tenant_team_members
                (id, tenant_id, name, email, role, status, last_active, invited_at, is_sample, created_at)
                VALUES (:id, :tid, :name, :email, :role, :status, :active, :invited, false, now())
                ON CONFLICT (id) DO UPDATE SET
                    name = :name, email = :email, role = :role, status = :status,
                    last_active = :active, invited_at = :invited
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
            },
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
    ctx: TenantContext = Depends(require_tenant_context),
) -> TeamResponse:
    """Get team members for a tenant."""
    tenant_id = ctx.tenant_id
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
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Invite a new team member."""
    tenant_id = ctx.tenant_id
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
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Update a team member's role."""
    tenant_id = ctx.tenant_id
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

    # #2865: this used to ``return {"error": ...}`` with HTTP 200, so a
    # client checking ``response.ok`` recorded a role change that never
    # happened. Raise so the installed handler renders the standard
    # error envelope with a 404.
    raise HTTPException(status_code=404, detail="Member not found")


@router.get(
    "/roles/definitions",
    summary="Get role definitions",
)
async def get_roles():
    """Get role definitions and permissions."""
    return {"roles": ROLE_PERMISSIONS}
