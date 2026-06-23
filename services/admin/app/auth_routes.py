"""Passwordless auth route registry."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_session
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
    email_code_router as _email_code_router_mod,
    refresh_router as _refresh_router_mod,
    sessions_router as _sessions_router_mod,
    webauthn_router as _webauthn_router_mod,
)
from .auth.challenges_router import (  # noqa: F401,E402
    AUTH_BROWSER_NONCE_COOKIE,
    AUTH_CHALLENGE_DETAIL,
    AUTH_SESSION_COOKIE,
    AUTH_SSO_REQUIRED_MESSAGE,
    create_auth_challenge,
    verify_auth_challenge,
)
from .auth.email_code_router import (  # noqa: F401,E402
    confirm_email_login_code,
    request_email_login_code,
)
from .auth.refresh_router import RefreshRequest, refresh_session  # noqa: F401,E402
from .auth.schemas import (  # noqa: F401,E402
    AuthMeResponse,
    ChallengeCreateRequest,
    ChallengeCreateResponse,
    ChallengeVerifyRequest,
    ChallengeVerifyResponse,
    EmailCodeConfirmRequest,
    EmailCodeRequest,
    EmailCodeRequestResponse,
    TokenResponse,
    UserResponse,
)
from .auth.session_auth import ActiveSessionContext, get_current_active_session_context  # noqa: E402
from .auth.session_helpers import _persist_session  # noqa: F401,E402
from .auth.sessions_router import (  # noqa: F401,E402
    list_sessions,
    logout,
    revoke_all_sessions,
    revoke_session,
)
router.include_router(_challenges_router_mod.router)
router.include_router(_email_code_router_mod.router)
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


@router.get("/me", response_model=AuthMeResponse)
def get_me(
    context: ActiveSessionContext = Depends(get_current_active_session_context),
    db: Session = Depends(get_session),
) -> AuthMeResponse:
    """Hydrate the current opaque browser session."""
    membership = _load_active_organization_membership(context=context, db=db)
    return AuthMeResponse(
        user_id=context.user.id,
        email=context.user.email,
        organization_id=membership.organization_id if membership is not None else None,
        role=membership.role if membership is not None else None,
        auth_method=context.session.auth_method,
    )


@router.get("/check-permission", response_model=PermissionCheckResponse)
def check_perm(
    user: UserModel = Depends(get_current_user),
    authorized: bool = Depends(PermissionChecker("admin.read")),
):
    """Test RBAC."""
    return {"message": "Permission granted", "user": user.email}
