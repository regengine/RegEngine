from datetime import datetime
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from shared.pagination import PaginatedResponse, PaginationParams
from shared.permissions import can_invite_role, role_rank
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .audit import AuditLogger
from .database import get_session
from .dependencies import PermissionChecker, get_current_user
from .models import TenantContext
from .sqlalchemy_models import MembershipModel, RoleModel, UserModel

router = APIRouter()
logger = structlog.get_logger("user_routes")


# DTOs
class UserResponse(BaseModel):
    id: UUID
    email: str
    status: str
    is_sysadmin: bool
    role_id: UUID
    role_name: str
    created_at: datetime


class RoleUpdate(BaseModel):
    role_id: UUID


class RoleResponse(BaseModel):
    id: UUID
    name: str
    is_system: bool


class UserActionResponse(BaseModel):
    """Response for user action operations."""

    status: str


def _other_authenticating_owners(db: Session, tenant_id: UUID, exclude_user_id: UUID) -> list:
    """Lock and return this tenant's Owner memberships, excluding ``exclude_user_id``,
    that belong to someone who can actually authenticate.

    #2906: the last-Owner invariant used to count every Owner *row*. Deactivation
    is a soft delete (``membership.is_active = False`` below), so an already
    offboarded Owner still satisfied the guard and an admin could strip the
    tenant of every Owner who can log in — a self-sealing lockout, because
    ``reactivate_user`` is itself gated by ``users.manage_roles``.

    "Can authenticate" is taken from the auth code, not invented here:

    * ``dependencies.get_current_user`` rejects the request (logging
      ``deactivated_user_access_attempt``) when ``not membership.is_active``, so
      an inactive membership confers zero capability on any admin route.
    * every credential-establishing path — ``auth/session_auth``,
      ``auth/webauthn_router``, ``auth/challenges_router``,
      ``auth/email_code_router`` — additionally requires
      ``users.global_status == 'active'`` and ``users.status == 'active'``, so a
      globally disabled user can never obtain a new session. The scheduler's
      ``disable_inactive_accounts`` sweep sets ``users.status = 'disabled'``
      automatically after 90 days (NIST AC-2(3)) and ``invite_routes`` refuses to
      reinstate a non-active user, so that state arrives without an admin acting
      and is not repairable from this surface.

    The guard therefore fails closed. It does not wedge a tenant: the *stale*
    Owner is the excluded target, so cleaning one up is always allowed while a
    healthy Owner remains, and promoting a replacement Owner is ungated.

    ``of=MembershipModel`` keeps #1083's ``SELECT ... FOR UPDATE`` serialization
    on the membership rows only. Without it PostgreSQL would also lock the joined
    ``roles`` row (system roles are shared across every tenant) and the joined
    ``users`` rows (written by every login), turning the guard into a
    cross-tenant contention and deadlock surface.
    """
    return db.execute(
        select(MembershipModel)
        .join(RoleModel, MembershipModel.role_id == RoleModel.id)
        .join(UserModel, MembershipModel.user_id == UserModel.id)
        .where(
            MembershipModel.tenant_id == tenant_id,
            RoleModel.name == "Owner",
            MembershipModel.user_id != exclude_user_id,
            MembershipModel.is_active.is_(True),
            UserModel.status == "active",
            UserModel.global_status == "active",
        )
        .with_for_update(of=MembershipModel)
    ).all()


# --- Endpoints ---


@router.get(
    "/admin/users",
    response_model=PaginatedResponse[UserResponse],
    dependencies=[Depends(PermissionChecker("users.read"))],
)
async def list_users(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_session),
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Count total
    count_stmt = (
        select(func.count())
        .select_from(UserModel)
        .join(MembershipModel, UserModel.id == MembershipModel.user_id)
        .where(MembershipModel.tenant_id == tenant_id)
    )
    total = db.execute(count_stmt).scalar()

    # helper for explicit join
    stmt = (
        select(UserModel, MembershipModel, RoleModel)
        .join(MembershipModel, UserModel.id == MembershipModel.user_id)
        .join(RoleModel, MembershipModel.role_id == RoleModel.id)
        .where(MembershipModel.tenant_id == tenant_id)
        .offset(pagination.skip)
        .limit(pagination.limit)
    )

    rows = db.execute(stmt).all()

    results = []
    for user, membership, role in rows:
        results.append(
            UserResponse(
                id=user.id,
                email=user.email,
                status="inactive" if not membership.is_active else user.status,
                is_sysadmin=user.is_sysadmin,
                role_id=role.id,
                role_name=role.name,
                created_at=user.created_at,
            )
        )

    return PaginatedResponse(items=results, total=total, skip=pagination.skip, limit=pagination.limit)


@router.patch(
    "/admin/users/{user_id}/role",
    response_model=UserActionResponse,
    dependencies=[Depends(PermissionChecker("users.manage_roles"))],
)
async def update_user_role(
    user_id: UUID,
    update: RoleUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # #1083: lock the target membership AND all Owner memberships for
    # this tenant in the same transaction. Two concurrent demotion
    # requests used to each observe the other Owner still present,
    # each pass the "last Owner" check, and each commit — leaving the
    # tenant with zero Owners. SELECT ... FOR UPDATE serializes them.
    membership = db.execute(
        select(MembershipModel)
        .where(
            MembershipModel.user_id == user_id,
            MembershipModel.tenant_id == tenant_id,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    target_role = db.get(RoleModel, update.role_id)
    if not target_role or (
        target_role.tenant_id is not None and target_role.tenant_id != tenant_id
    ):
        # Treat a cross-tenant custom role exactly like an unknown role. A
        # caller must never be able to attach another tenant's permissions to
        # a membership or use this response as a role-enumeration oracle.
        raise HTTPException(status_code=400, detail="Role not found")

    current_role = db.get(RoleModel, membership.role_id)
    if current_role.name == "Owner" and target_role.name != "Owner":
        # Lock every Owner membership for this tenant so another
        # concurrent demotion can't commit in parallel, and count only
        # the Owners who can actually authenticate (#2906).
        if not _other_authenticating_owners(db, tenant_id, user_id):
            raise HTTPException(status_code=400, detail="Cannot remove the last Owner")

    # Privilege-escalation guard, mirroring invite creation (#1387). Holding
    # users.manage_roles lets an admin change roles, but they may NOT assign
    # a role of higher rank than their own: without this a compromised
    # low-privilege key with role-management permission self-promotes to
    # Owner. Sysadmins bypass (platform-level role, same as invites).
    if not current_user.is_sysadmin:
        caller_role = db.execute(
            select(RoleModel)
            .join(MembershipModel, MembershipModel.role_id == RoleModel.id)
            .where(
                MembershipModel.user_id == current_user.id,
                MembershipModel.tenant_id == tenant_id,
                MembershipModel.is_active == True,  # noqa: E712
            )
        ).scalar_one_or_none()
        if caller_role is None:
            logger.warning(
                "role_change_no_caller_role",
                user_id=str(current_user.id),
                tenant_id=str(tenant_id),
            )
            raise HTTPException(status_code=403, detail="No active role in this tenant")
        # The grant_owner hatch is for inviting outsiders, not for promoting
        # current members in place: a non-Owner holding
        # users.invite.grant_owner must not be able to make anyone,
        # self included, an Owner through this route.
        if not can_invite_role(
            caller_role_name=getattr(caller_role, "name", None),
            caller_permissions=getattr(caller_role, "permissions", None) or [],
            target_role_name=getattr(target_role, "name", None),
            target_permissions=getattr(target_role, "permissions", None) or [],
            honor_grant_owner=False,
        ):
            logger.warning(
                "role_change_escalation_blocked",
                user_id=str(current_user.id),
                tenant_id=str(tenant_id),
                caller_role=getattr(caller_role, "name", None),
                target_role=getattr(target_role, "name", None),
            )
            # Opaque 403 so an attacker can't enumerate role tiers by response.
            raise HTTPException(status_code=403, detail="Insufficient privilege to assign this role")
        # A caller may not move a member whose current role outranks their
        # own: without this an Admin could demote another Owner, leaving
        # only the last-Owner backstop, which keys off the exact name.
        current_rank = role_rank(
            getattr(current_role, "name", None),
            getattr(current_role, "permissions", None) or [],
        )
        caller_rank = role_rank(
            getattr(caller_role, "name", None),
            getattr(caller_role, "permissions", None) or [],
        )
        if current_rank > caller_rank:
            logger.warning(
                "role_change_demotion_blocked",
                user_id=str(current_user.id),
                tenant_id=str(tenant_id),
                caller_role=getattr(caller_role, "name", None),
                current_role=getattr(current_role, "name", None),
            )
            raise HTTPException(status_code=403, detail="Insufficient privilege to assign this role")

    # Update
    old_role_id = membership.role_id
    membership.role_id = target_role.id

    AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="membership.role_change",
        event_category="identity_access",
        actor_id=current_user.id,
        action="membership.role_change",
        resource_type="membership",
        resource_id=str(user_id),
        metadata={"old_role": str(old_role_id), "new_role": str(target_role.id)},
    )

    db.commit()
    return {"status": "updated"}


@router.post(
    "/admin/users/{user_id}/deactivate",
    response_model=UserActionResponse,
    dependencies=[Depends(PermissionChecker("users.disable"))],
)
async def deactivate_user(
    user_id: UUID, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # #1083: lock target membership + Owner rows. Same race as
    # update_user_role — concurrent deactivations of two Owners could
    # zero out the tenant before the invariant check fires.
    membership = db.execute(
        select(MembershipModel)
        .where(
            MembershipModel.user_id == user_id,
            MembershipModel.tenant_id == tenant_id,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=404, detail="User not found")

    current_role = db.get(RoleModel, membership.role_id)
    if current_role.name == "Owner":
        if not _other_authenticating_owners(db, tenant_id, user_id):
            raise HTTPException(status_code=400, detail="Cannot remove the last Owner")

    # Soft delete (tenant-scoped deactivation, not global user disable).
    membership.is_active = False

    AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="membership.deactivate",
        event_category="identity_access",
        actor_id=current_user.id,
        action="membership.deactivate",
        resource_type="membership",
        resource_id=str(user_id),
        metadata={"is_active": False},
    )

    db.commit()
    return {"status": "deactivated"}


@router.post(
    "/admin/users/{user_id}/reactivate",
    response_model=UserActionResponse,
    dependencies=[Depends(PermissionChecker("users.manage_roles"))],
)
async def reactivate_user(
    user_id: UUID, current_user: UserModel = Depends(get_current_user), db: Session = Depends(get_session)
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    membership = db.execute(
        select(MembershipModel).where(
            MembershipModel.user_id == user_id,
            MembershipModel.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()

    if not membership:
        raise HTTPException(status_code=404, detail="User not found")

    # #1406: block reactivation of a sysadmin's dormant membership by a
    # tenant Owner. An engineer who debugged the tenant months ago
    # should not have cross-tenant access resurrected by a customer.
    target_user = db.get(UserModel, user_id)
    if (
        target_user is not None
        and getattr(target_user, "is_sysadmin", False)
        and not getattr(current_user, "is_sysadmin", False)
    ):
        logger.warning(
            "sysadmin_reactivation_blocked",
            target_user_id=str(user_id),
            actor_id=str(current_user.id),
            tenant_id=str(tenant_id),
        )
        AuditLogger.log_event(
            db,
            tenant_id=tenant_id,
            event_type="membership.reactivate_blocked",
            event_category="identity_access",
            severity="warning",
            actor_id=current_user.id,
            action="membership.reactivate_blocked",
            resource_type="membership",
            resource_id=str(user_id),
            metadata={"reason": "target_is_sysadmin"},
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail="Cannot reactivate sysadmin membership without sysadmin privileges",
        )

    membership.is_active = True

    AuditLogger.log_event(
        db,
        tenant_id=tenant_id,
        event_type="membership.reactivate",
        event_category="identity_access",
        actor_id=current_user.id,
        action="membership.reactivate",
        resource_type="membership",
        resource_id=str(user_id),
        metadata={"is_active": True},
    )

    db.commit()
    return {"status": "reactivated"}


@router.get(
    "/admin/roles",
    response_model=PaginatedResponse[RoleResponse],
    dependencies=[Depends(PermissionChecker("users.read"))],
)
async def list_roles(
    pagination: PaginationParams = Depends(),
    db: Session = Depends(get_session),
):
    tenant_id = TenantContext.get_tenant_context(db)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    # Count total
    count_stmt = (
        select(func.count())
        .select_from(RoleModel)
        .where((RoleModel.tenant_id == tenant_id) | (RoleModel.tenant_id.is_(None)))
    )
    total = db.execute(count_stmt).scalar()

    # Return System roles (tenant_id is NULL) AND Custom roles (tenant_id matches)
    stmt = (
        select(RoleModel)
        .where((RoleModel.tenant_id == tenant_id) | (RoleModel.tenant_id.is_(None)))
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    roles = db.execute(stmt).scalars().all()

    results = []
    for r in roles:
        results.append(RoleResponse(id=r.id, name=r.name, is_system=r.tenant_id is None))
    return PaginatedResponse(items=results, total=total, skip=pagination.skip, limit=pagination.limit)
