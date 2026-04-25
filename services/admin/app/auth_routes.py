from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from datetime import timedelta, datetime, timezone
import structlog
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from uuid import UUID
import uuid
import time

import jwt as _jwt

from .database import get_session
from .sqlalchemy_models import UserModel, MembershipModel, TenantModel, RoleModel
from .auth_utils import verify_password, verify_login, get_password_hash, create_access_token, create_refresh_token, decode_access_token, hash_token, REFRESH_TOKEN_EXPIRE_DAYS
from .dependencies import get_current_user, PermissionChecker, get_session_store
from .audit import AuditLogger
from .password_policy import validate_password, PasswordPolicyError
from .session_store import RedisSessionStore, SessionData
from .models import (
    PermissionCheckResponse, SessionListResponse, SessionRevokeResponse,
    RevokeAllSessionsResponse, RegisterAdminResponse, ChangePasswordResponse,
    ResetPasswordResponse
)
from shared.supabase_client import get_supabase
from shared.funnel_events import emit_funnel_event
from shared.pii import mask_email
from shared.rate_limit import limiter
from shared.pagination import PaginationParams

import asyncio

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger("auth")

# Lockout + email-rate-limit helpers extracted to services/admin/app/auth/lockout.py
# (Phase 1 — first auth/ sub-split).  Re-exported here so the existing
# ``from services.admin.app.auth_routes import _progressive_delay_seconds`` imports
# used by tests and other callers continue to work unchanged.
from .auth.lockout import (  # noqa: F401  (re-exported for backward compat)
    _EMAIL_ATTEMPT_LIMIT,
    _EMAIL_ATTEMPT_WINDOW,
    _LOCKOUT_THRESHOLD,
    _LOCKOUT_DURATION,
    _PROGRESSIVE_DELAY_START,
    _PROGRESSIVE_DELAY_CAP_SECONDS,
    _email_attempt_key,
    _maybe_await,
    _check_email_rate_limit,
    _record_failed_login_attempt,
    _clear_email_rate_limit,
    _lockout_key,
    _lockout_delay_key,
    _progressive_delay_seconds,
    _check_account_lockout,
    _record_lockout_attempt,
    _clear_lockout,
)


# Pydantic schemas extracted to services/admin/app/auth/schemas.py and
# _persist_session extracted to services/admin/app/auth/session_helpers.py
# (Phase 1 sub-split 2/N). Re-exported here so existing
# ``from services.admin.app.auth_routes import LoginRequest`` / ``ar._persist_session``
# imports continue to work unchanged.
from .auth.schemas import (  # noqa: F401  (re-exported for backward compat)
    LoginRequest,
    TokenResponse,
    RegisterRequest,
    SignupAcceptedResponse,
    UserResponse,
    _SIGNUP_ACCEPTED_DETAIL,
    _signup_accepted_response,
)
from .auth.session_helpers import _persist_session  # noqa: F401


async def _cleanup_supabase_user(user_id: UUID) -> None:
    """Best-effort delete of an orphaned Supabase user.

    #1090 — called when a Supabase account was created but the subsequent
    DB transaction failed, leaving the Supabase user without a matching
    RegEngine record. Swallows all errors since this is cleanup-only.
    """
    try:
        sb = get_supabase()
        if sb:
            sb.auth.admin.delete_user(str(user_id))
            logger.info("supabase_orphan_cleaned", user_id=str(user_id))
    except Exception as exc:
        logger.warning("supabase_orphan_cleanup_failed", user_id=str(user_id), error=str(exc))


# Slug helpers extracted to services/admin/app/auth/signup_helpers.py
# (Phase 1 sub-split 3/N). Re-exported here so existing imports
# ``from services.admin.app.auth_routes import _slugify_tenant_name`` keep
# working. ``_cleanup_supabase_user`` stays in this module because
# tests patch ``auth_routes.get_supabase`` via the module namespace —
# moving the function would break those patches.
from .auth.signup_helpers import (  # noqa: F401  (re-exported for backward compat)
    _slugify_tenant_name,
    _ensure_unique_tenant_slug,
)

# Login route extracted to services/admin/app/auth/login_router.py
# (Phase 1 sub-split 4/N).  Re-exported here so existing
# ``from services.admin.app.auth_routes import login`` imports and
# ``monkeypatch.setattr(ar, "login", ...)`` calls continue to work.
from .auth.login_router import login  # noqa: F401
from .auth import login_router as _login_router_mod
router.include_router(_login_router_mod.router)

# Signup route extracted to services/admin/app/auth/signup_router.py
# (Phase 1 sub-split 5/N).  Re-exported here so existing
# ``from services.admin.app.auth_routes import signup`` imports and
# ``ar.signup.__wrapped__(...)`` test calls continue to work.
from .auth.signup_router import signup  # noqa: F401
from .auth import signup_router as _signup_router_mod
router.include_router(_signup_router_mod.router)

# Refresh route extracted to services/admin/app/auth/refresh_router.py
# (Phase 1 sub-split 6/N).  Re-exported here so existing
# ``from services.admin.app.auth_routes import refresh_session`` imports and
# ``ar.refresh_session.__wrapped__(...)`` test calls continue to work.
from .auth.refresh_router import refresh_session, RefreshRequest  # noqa: F401
from .auth import refresh_router as _refresh_router_mod
router.include_router(_refresh_router_mod.router)

# Elevation constants + _revoke_all_elevation_tokens_for_user moved to
# auth/elevation_helpers.py so sessions_router can import them without
# a circular dependency. Re-imported here so change_password / reset_password
# (still in this module) and test patches on ``ar`` continue to work.
from .auth.elevation_helpers import (  # noqa: F401
    _ELEVATION_JTI_KEY_PREFIX,
    _ELEVATION_TOKEN_TTL_SECONDS,
    _revoke_all_elevation_tokens_for_user,
)

# Sessions cluster extracted to services/admin/app/auth/sessions_router.py
# (Phase 1 sub-split 7/N).  Re-exported here so existing imports and
# ``ar.list_sessions / ar.revoke_session / ar.revoke_all_sessions`` calls work.
from .auth.sessions_router import list_sessions, revoke_session, revoke_all_sessions  # noqa: F401
from .auth import sessions_router as _sessions_router_mod
router.include_router(_sessions_router_mod.router)

# /register extracted to auth/register_router.py (sub-split 8/N).
from .auth.register_router import register_initial_admin  # noqa: F401
from .auth import register_router as _register_router_mod
router.include_router(_register_router_mod.router)

# /change-password extracted to auth/change_password_router.py (sub-split 9/N).
from .auth.change_password_router import change_password, ChangePasswordRequest  # noqa: F401
from .auth import change_password_router as _change_password_router_mod
router.include_router(_change_password_router_mod.router)

# /reset-password extracted to auth/reset_password_router.py (sub-split 10/N).
from .auth.reset_password_router import (  # noqa: F401
    reset_password,
    ResetPasswordRequest,
    _enforce_recovery_token_scope,
    _claim_recovery_token_single_use,
)
from .auth import reset_password_router as _reset_password_router_mod
router.include_router(_reset_password_router_mod.router)

# /confirm + require_reauth + /unlock extracted to auth/confirm_router.py (sub-split 11/N).
from .auth.confirm_router import (  # noqa: F401
    confirm_password,
    require_reauth,
    unlock_account,
    ConfirmPasswordRequest,
)
from .auth import confirm_router as _confirm_router_mod
router.include_router(_confirm_router_mod.router)

@router.get("/me", response_model=UserResponse)
def get_me(user: UserModel = Depends(get_current_user)):
    """Get current user context (verifies token and tenant context)."""
    return user

@router.get("/check-permission", response_model=PermissionCheckResponse)
def check_perm(
    user: UserModel = Depends(get_current_user),
    authorized: bool = Depends(PermissionChecker("admin.read"))
):
    """Test RBAC."""
    return {"message": "Permission granted", "user": user.email}
