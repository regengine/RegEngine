"""Auth routes — thin shim over ``services/admin/app/auth/`` sub-modules.

Phase 1 split is complete: all handler bodies live in their dedicated
``services.admin.app.auth.*_router`` sub-modules. This file is now only
responsible for:

  1. Owning the ``/auth`` ``APIRouter`` mounted by ``main.py``.
  2. Including each sub-router so all routes register on the same prefix.
  3. Re-exporting every public name (handlers, schemas, helpers) so the
     long tail of existing ``from services.admin.app.auth_routes import X``
     imports keeps working without touching every caller.

Two routes intentionally live here rather than in a sub-module:

  * ``GET /me`` — single-line wrapper around the ``get_current_user``
    dependency; not worth a dedicated router file.
  * ``GET /check-permission`` — same shape, single-line wrapper.

``_cleanup_supabase_user`` also stays here because several wave-2 hardening
tests patch ``auth_routes.get_supabase`` and call this function directly,
and migrating those patches is a larger test-rewrite that does not block
the route-registration fix.

If you are adding a new auth route: put it in a new ``auth/<name>_router.py``
module and add an ``include_router`` call below — do NOT add another route
body to this file.
"""
from __future__ import annotations

import asyncio  # noqa: F401  (re-exported; wave-2 tests patch ar.asyncio.sleep)
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends

from .audit import AuditLogger  # noqa: F401  (re-exported for tests)
from .auth_utils import (  # noqa: F401  (re-exported for tests/back-compat)
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    get_password_hash,
    hash_token,
    verify_login,
    verify_password,
)
from .dependencies import PermissionChecker, get_current_user, get_session_store  # noqa: F401
from .password_policy import validate_password, PasswordPolicyError  # noqa: F401
from .session_store import RedisSessionStore, SessionData  # noqa: F401
from .sqlalchemy_models import (  # noqa: F401
    MembershipModel,
    RoleModel,
    TenantModel,
    UserModel,
)
from .models import (  # noqa: F401
    ChangePasswordResponse,
    PermissionCheckResponse,
    RegisterAdminResponse,
    ResetPasswordResponse,
    RevokeAllSessionsResponse,
    SessionListResponse,
    SessionRevokeResponse,
)
from shared.funnel_events import emit_funnel_event  # noqa: F401  (re-exported for tests)
from shared.pii import mask_email  # noqa: F401
from shared.rate_limit import limiter  # noqa: F401
from shared.supabase_client import get_supabase  # noqa: F401  (re-exported for tests)


# ── Router + sub-module includes ─────────────────────────────────────────────
router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger("auth")

# Helpers / constants — re-exported from auth/lockout.py (sub-split 1/N).
from .auth.lockout import (  # noqa: F401,E402
    _EMAIL_ATTEMPT_LIMIT,
    _EMAIL_ATTEMPT_WINDOW,
    _LOCKOUT_DURATION,
    _LOCKOUT_THRESHOLD,
    _PROGRESSIVE_DELAY_CAP_SECONDS,
    _PROGRESSIVE_DELAY_START,
    _check_account_lockout,
    _check_email_rate_limit,
    _clear_email_rate_limit,
    _clear_lockout,
    _email_attempt_key,
    _lockout_delay_key,
    _lockout_key,
    _maybe_await,
    _progressive_delay_seconds,
    _record_failed_login_attempt,
    _record_lockout_attempt,
)

# Pydantic schemas + signup helpers — sub-splits 2/N and 3/N.
from .auth.schemas import (  # noqa: F401,E402
    LoginRequest,
    RegisterRequest,
    SignupAcceptedResponse,
    TokenResponse,
    UserResponse,
    _SIGNUP_ACCEPTED_DETAIL,
    _signup_accepted_response,
)
from .auth.session_helpers import _persist_session  # noqa: F401,E402
from .auth.signup_helpers import (  # noqa: F401,E402
    _ensure_unique_tenant_slug,
    _slugify_tenant_name,
)
from .auth.elevation_helpers import (  # noqa: F401,E402
    _ELEVATION_JTI_KEY_PREFIX,
    _ELEVATION_TOKEN_TTL_SECONDS,
    _revoke_all_elevation_tokens_for_user,
)

# Route sub-modules — each owns an APIRouter that we include below. Importing
# the full module (not just ``router``) keeps ``ar.<handler_name>`` resolution
# working for tests that call ``await auth_routes.<handler>.__wrapped__(...)``.
from .auth import login_router as _login_router_mod  # noqa: E402
from .auth import signup_router as _signup_router_mod  # noqa: E402
from .auth import refresh_router as _refresh_router_mod  # noqa: E402
from .auth import sessions_router as _sessions_router_mod  # noqa: E402
from .auth import register_router as _register_router_mod  # noqa: E402
from .auth import change_password_router as _change_password_router_mod  # noqa: E402
from .auth import reset_password_router as _reset_password_router_mod  # noqa: E402
from .auth import confirm_router as _confirm_router_mod  # noqa: E402

# Handler + schema re-exports for back-compat with ``from auth_routes import X``.
from .auth.login_router import login  # noqa: F401,E402
from .auth.signup_router import signup  # noqa: F401,E402
from .auth.refresh_router import RefreshRequest, refresh_session  # noqa: F401,E402
from .auth.sessions_router import (  # noqa: F401,E402
    list_sessions,
    revoke_all_sessions,
    revoke_session,
)
from .auth.register_router import register_initial_admin  # noqa: F401,E402
from .auth.change_password_router import (  # noqa: F401,E402
    ChangePasswordRequest,
    change_password,
)
from .auth.reset_password_router import (  # noqa: F401,E402
    ResetPasswordRequest,
    _RECOVERY_ALLOWED_AMR_METHODS,
    _RECOVERY_TOKEN_MAX_AGE_SECONDS,
    _claim_recovery_token_single_use,
    _enforce_recovery_token_scope,
    _parse_supabase_token_claims,
    reset_password,
)
from .auth.confirm_router import (  # noqa: F401,E402
    ConfirmPasswordRequest,
    _elevation_jti_key,
    confirm_password,
    require_reauth,
    unlock_account,
)


# ── Mount every sub-router on /auth ─────────────────────────────────────────
router.include_router(_login_router_mod.router)
router.include_router(_signup_router_mod.router)
router.include_router(_refresh_router_mod.router)
router.include_router(_sessions_router_mod.router)
router.include_router(_register_router_mod.router)
router.include_router(_change_password_router_mod.router)
router.include_router(_reset_password_router_mod.router)
router.include_router(_confirm_router_mod.router)


# ── Two trivial routes that intentionally live in the shim ──────────────────
@router.get("/me", response_model=UserResponse)
def get_me(user: UserModel = Depends(get_current_user)):
    """Get current user context (verifies token and tenant context)."""
    return user


@router.get("/check-permission", response_model=PermissionCheckResponse)
def check_perm(
    user: UserModel = Depends(get_current_user),
    authorized: bool = Depends(PermissionChecker("admin.read")),
):
    """Test RBAC."""
    return {"message": "Permission granted", "user": user.email}


# ── Cleanup helper that wave-2 tests patch via ``auth_routes.get_supabase`` ──
async def _cleanup_supabase_user(user_id: UUID) -> None:
    """Best-effort delete of an orphaned Supabase user.

    #1090 — called when a Supabase account was created but the subsequent
    DB transaction failed, leaving the Supabase user without a matching
    RegEngine record. Swallows all errors since this is cleanup-only.

    Stays in this module (rather than a sub-router) so wave-2 hardening
    tests that patch ``auth_routes.get_supabase`` continue to reach the
    cleanup path through a single namespace.
    """
    try:
        sb = get_supabase()
        if sb:
            sb.auth.admin.delete_user(str(user_id))
            logger.info("supabase_orphan_cleaned", user_id=str(user_id))
    except Exception as exc:
        logger.warning(
            "supabase_orphan_cleanup_failed",
            user_id=str(user_id),
            error=str(exc),
        )
