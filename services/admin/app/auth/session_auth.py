"""Cookie-backed session authentication dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_crypto import AuthCryptoService
from ..database import (
    arm_global_admin_context,
    bind_authenticated_user_context,
    disarm_global_admin_context,
    get_session,
)
from ..sqlalchemy_models import SessionModel, UserModel

AUTH_SESSION_COOKIE = "__Host-regengine_session"
HIGH_ASSURANCE_AUTH_METHODS = frozenset({"webauthn", "sso"})
STEP_UP_ERROR_CODE = "requires_step_up"

logger = structlog.get_logger("auth.session")


@dataclass(frozen=True)
class ActiveSessionContext:
    user: UserModel
    session: SessionModel


def get_auth_crypto_service() -> AuthCryptoService:
    return AuthCryptoService()


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
    )


def _requires_step_up(auth_method: str | None) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": STEP_UP_ERROR_CODE,
            "message": "High assurance authentication required.",
            "auth_method": auth_method,
        },
    )


def get_current_active_session_context(
    request: Request,
    db: Session = Depends(get_session),
    crypto_service: AuthCryptoService = Depends(get_auth_crypto_service),
) -> ActiveSessionContext:
    """Authenticate the current user and DB session from the opaque cookie."""
    session_token = request.cookies.get(AUTH_SESSION_COOKIE)
    if not session_token:
        raise _unauthenticated()

    try:
        token_hash = crypto_service.hash_session_token(session_token)
    except ValueError as exc:
        raise _unauthenticated() from exc

    now = datetime.now(timezone.utc)
    stmt = (
        select(UserModel, SessionModel)
        .join(SessionModel, SessionModel.user_id == UserModel.id)
        .where(
            SessionModel.token_hash == token_hash,
            SessionModel.is_revoked.is_(False),
            SessionModel.revoked_at.is_(None),
            SessionModel.expires_at > now,
            UserModel.global_status == "active",
            UserModel.status == "active",
        )
        .limit(1)
    )

    try:
        row = db.execute(stmt).one_or_none()
    except Exception as exc:
        logger.error("session_lookup_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable.",
        ) from exc

    if row is None:
        raise _unauthenticated()

    user, session = row
    return ActiveSessionContext(user=user, session=session)


def get_scoped_active_session_context(
    request: Request,
    db: Session = Depends(get_session),
    crypto_service: AuthCryptoService = Depends(get_auth_crypto_service),
) -> ActiveSessionContext:
    """Resolve an opaque session from a baseline-denied admin connection.

    The cookie-to-user lookup is necessarily pre-tenant.  Global authority is
    transaction-local and exists only around that lookup; the returned session
    retains a user-self GUC, not the global sysadmin arm.
    """

    try:
        arm_global_admin_context(db)
        context = get_current_active_session_context(
            request=request,
            db=db,
            crypto_service=crypto_service,
        )
    finally:
        disarm_global_admin_context(db)

    bind_authenticated_user_context(db, context.user.id)
    return context


def get_current_active_user(
    context: ActiveSessionContext = Depends(get_scoped_active_session_context),
) -> UserModel:
    """Authenticate the current user from the opaque browser session cookie."""
    return context.user


def require_high_assurance_session(
    context: ActiveSessionContext = Depends(get_scoped_active_session_context),
) -> UserModel:
    """Require an active WebAuthn or SSO-backed browser session."""
    auth_method = getattr(context.session, "auth_method", None)
    if auth_method not in HIGH_ASSURANCE_AUTH_METHODS:
        logger.info(
            "step_up_required",
            user_id=str(getattr(context.user, "id", "")),
            auth_method=auth_method,
        )
        raise _requires_step_up(auth_method)
    return context.user
