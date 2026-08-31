"""Passwordless auth route registry."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .database import arm_global_admin_context, disarm_global_admin_context, get_session
from .dependencies import PermissionChecker, get_current_user, get_session_store  # noqa: F401
from .models import PermissionCheckResponse  # noqa: F401
from .session_store import RedisSessionStore, SessionData  # noqa: F401
from .sqlalchemy_models import (
    MembershipModel,
    OrganizationMembershipModel,
    RoleModel,
    TenantModel,
    UserModel,
)  # noqa: F401

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger("auth")

from .auth import (  # noqa: E402
    challenges_router as _challenges_router_mod,
    refresh_router as _refresh_router_mod,
    sessions_router as _sessions_router_mod,
    webauthn_router as _webauthn_router_mod,
)
from .auth.challenges_router import (  # noqa: F401,E402
    AUTH_BROWSER_NONCE_COOKIE,
    AUTH_CHALLENGE_DETAIL,
    AUTH_SESSION_COOKIE,
    create_auth_challenge,
    verify_auth_challenge,
)
from .auth.refresh_router import RefreshRequest, refresh_session  # noqa: F401,E402
from .auth.schemas import (  # noqa: F401,E402
    AuthMeResponse,
    ChallengeCreateRequest,
    ChallengeCreateResponse,
    ChallengeVerifyRequest,
    ChallengeVerifyResponse,
    TokenResponse,
    UserResponse,
)
from .auth.session_auth import ActiveSessionContext, get_scoped_active_session_context  # noqa: E402
from .auth.session_helpers import _persist_session  # noqa: F401,E402
from .auth.sessions_router import (  # noqa: F401,E402
    list_sessions,
    logout,
    revoke_all_sessions,
    revoke_session,
)

router.include_router(_challenges_router_mod.router)
router.include_router(_refresh_router_mod.router)
router.include_router(_sessions_router_mod.router)
router.include_router(_webauthn_router_mod.router)


def _load_active_organization_membership(
    *,
    context: ActiveSessionContext,
    db: Session,
) -> OrganizationMembershipModel | None:
    active_membership_id = getattr(context.session, "active_membership_id", None)
    if active_membership_id is None:
        return None

    stmt = (
        select(OrganizationMembershipModel)
        .where(
            OrganizationMembershipModel.id == active_membership_id,
            OrganizationMembershipModel.user_id == context.user.id,
        )
        .limit(1)
    )
    membership = db.execute(stmt).scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return membership


def _resolve_session_tenant_id(*, user_id, db: Session):
    """Return the tenant this session acts as, or None if ambiguous.

    Mirrors get_current_user's derivation: use the sole active row in the
    ``memberships`` table. Multiple active memberships are ambiguous without a
    tenant claim, so we refuse to guess and return None (the frontend then
    falls back to demo state rather than acting as the wrong tenant).
    """
    tenant_ids = (
        db.execute(
            select(MembershipModel.tenant_id).where(
                MembershipModel.user_id == user_id,
                MembershipModel.is_active == True,  # noqa: E712 (SQLAlchemy needs ==)
            )
        )
        .scalars()
        .all()
    )
    return tenant_ids[0] if len(tenant_ids) == 1 else None


def _resolve_session_permissions(*, user_id, tenant_id, db: Session) -> list[str]:
    """Return the active tenant role's string permissions, or fail closed."""
    if tenant_id is None:
        return []

    role = db.execute(
        select(RoleModel)
        .join(MembershipModel, MembershipModel.role_id == RoleModel.id)
        .where(
            MembershipModel.user_id == user_id,
            MembershipModel.tenant_id == tenant_id,
            MembershipModel.is_active == True,  # noqa: E712 (SQLAlchemy needs ==)
            or_(RoleModel.tenant_id.is_(None), RoleModel.tenant_id == tenant_id),
        )
        .limit(1)
    ).scalar_one_or_none()
    if role is None or not isinstance(role.permissions, list):
        return []
    return [permission for permission in role.permissions if isinstance(permission, str)]


@router.get("/me", response_model=AuthMeResponse)
def get_me(
    context: ActiveSessionContext = Depends(get_scoped_active_session_context),
    db: Session = Depends(get_session),
) -> AuthMeResponse:
    """Hydrate the current opaque browser session."""
    # Hydration is still part of the authenticated pre-tenant bootstrap.  The
    # global arm is removed before the response leaves this dependency chain.
    arm_global_admin_context(db)
    try:
        membership = _load_active_organization_membership(context=context, db=db)
        tenant_id = _resolve_session_tenant_id(user_id=context.user.id, db=db)
        permissions = _resolve_session_permissions(user_id=context.user.id, tenant_id=tenant_id, db=db)
        return AuthMeResponse(
            user_id=context.user.id,
            email=context.user.email,
            organization_id=membership.organization_id if membership is not None else None,
            tenant_id=tenant_id,
            role=membership.role if membership is not None else None,
            auth_method=context.session.auth_method,
            is_sysadmin=bool(context.user.is_sysadmin),
            permissions=permissions,
        )
    finally:
        disarm_global_admin_context(db)


@router.get("/check-permission", response_model=PermissionCheckResponse)
def check_perm(
    user: UserModel = Depends(get_current_user),
    authorized: bool = Depends(PermissionChecker("admin.read")),
):
    """Test RBAC."""
    return {"message": "Permission granted", "user": user.email}
