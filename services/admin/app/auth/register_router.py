"""Bootstrap /register route — extracted from auth_routes.py (Phase 1 sub-split 8/N).

Exposes:
  router                 — APIRouter with /register registered
  register_initial_admin — handler (re-exported from auth_routes for compat)
"""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import AuditLogger
from ..auth_utils import get_password_hash
from ..database import get_session
from ..models import RegisterAdminResponse
from ..password_policy import validate_password, PasswordPolicyError
from ..sqlalchemy_models import MembershipModel, RoleModel, TenantModel, UserModel
from .schemas import RegisterRequest
from shared.rate_limit import limiter

router = APIRouter()
logger = structlog.get_logger("auth")


@router.post("/register", response_model=RegisterAdminResponse)
@limiter.limit("3/minute")
def register_initial_admin(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_session),
):
    """Bootstrapping endpoint to create the first admin and tenant."""
    if db.execute(select(UserModel)).first():
        raise HTTPException(status_code=403, detail="Registration disabled. Use invites.")

    try:
        validate_password(payload.password, user_context={"email": payload.email})
    except PasswordPolicyError as e:
        raise HTTPException(status_code=400, detail=e.message)

    new_user = UserModel(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        is_sysadmin=True,
        status="active",
    )
    db.add(new_user)
    db.flush()

    new_tenant = TenantModel(
        name=payload.tenant_name,
        slug=payload.tenant_name.lower().replace(" ", "-"),
        status="active",
    )
    db.add(new_tenant)
    db.flush()

    owner_role = RoleModel(
        tenant_id=new_tenant.id,
        name="Owner",
        permissions=["*"],
    )
    db.add(owner_role)
    db.flush()

    membership = MembershipModel(
        user_id=new_user.id,
        tenant_id=new_tenant.id,
        role_id=owner_role.id,
    )
    db.add(membership)

    AuditLogger.log_event(
        db,
        tenant_id=new_tenant.id,
        event_type="tenant.create",
        action="tenant.create",
        event_category="tenant_management",
        actor_id=new_user.id,
        resource_type="tenant",
        resource_id=str(new_tenant.id),
        metadata={"tenant_name": new_tenant.name},
    )
    db.commit()

    return {"message": "Admin created", "user_id": str(new_user.id), "tenant_id": str(new_tenant.id)}
