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





@router.post("/register", response_model=RegisterAdminResponse)
@limiter.limit("3/minute")
def register_initial_admin(payload: RegisterRequest, request: Request, db: Session = Depends(get_session)):
    """Bootstrapping endpoint to create the first admin and tenant."""
    # Check if any users exist to prevent abuse
    if db.execute(select(UserModel)).first():
        raise HTTPException(status_code=403, detail="Registration disabled. Use invites.")

    # Validate password against policy
    try:
        validate_password(payload.password, user_context={'email': payload.email})
    except PasswordPolicyError as e:
        raise HTTPException(status_code=400, detail=e.message)

    # Create User
    new_user = UserModel(
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        is_sysadmin=True,
        status="active"
    )
    db.add(new_user)
    db.flush()
    
    # Create Tenant
    new_tenant = TenantModel(
        name=payload.tenant_name,
        slug=payload.tenant_name.lower().replace(" ", "-"),
        status="active"
    )
    db.add(new_tenant)
    db.flush()
    
    # Create Admin Role
    from app.sqlalchemy_models import RoleModel
    owner_role = RoleModel(
        tenant_id=new_tenant.id,
        name="Owner",
        permissions=["*"]
    )
    db.add(owner_role)
    db.flush()
    
    # Create Membership
    membership = MembershipModel(
        user_id=new_user.id,
        tenant_id=new_tenant.id,
        role_id=owner_role.id
    )
    db.add(membership)
    
    # Audit Log
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


# ---------------------------------------------------------------------------
# Password Reset — updates the RegEngine argon2 hash using a Supabase
# recovery session token.
#
# WHY THIS EXISTS:
# The frontend uses supabase.auth.verifyOtp({ token_hash }) on /auth/verify,
# which creates a Supabase recovery session. supabase.auth.updateUser() would
# only update Supabase's internal password store. But the RegEngine login
# endpoint checks argon2 hashes in our own PostgreSQL users table — a
# completely separate store. This endpoint updates that store.
#
# AUTH FLOW:
#   1. /auth/verify calls verifyOtp → Supabase issues access_token (recovery)
#   2. /reset-password page reads session.access_token
#   3. Frontend POSTs here with { new_password } + Authorization: Bearer <supabase_token>
#   4. We validate the token via sb.auth.get_user(), get the user's email
#   5. We update password_hash in the RegEngine DB
#   6. We also sync Supabase via admin.update_user_by_id() so both stores match
# ---------------------------------------------------------------------------

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password", response_model=ChangePasswordResponse)
@limiter.limit("5/minute")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_session),
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Change an authenticated user's password.

    Verifies the current password, validates the new password against policy,
    updates the argon2 hash in the RegEngine DB, and syncs to Supabase so both
    stores stay aligned (matching the pattern used in reset-password).

    #1380 — also revokes any outstanding elevation tokens so a /confirm at T+0
    cannot be replayed after a password change at T+1. The caller's CURRENT
    access token keeps working (tv unchanged for this session) so we do not
    log them out of their own browser.
    """
    # Re-fetch the user within this session to get the current password_hash
    user = db.get(UserModel, current_user.id)
    if not user or user.status != "active":
        raise HTTPException(status_code=403, detail="Account disabled")

    if not verify_password(payload.current_password, user.password_hash):
        logger.warning("change_password_wrong_current", user_id=str(user.id))
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    try:
        validate_password(payload.new_password, user_context={"email": user.email})
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    user.password_hash = get_password_hash(payload.new_password)
    user.token_version = int(getattr(user, "token_version", 0) or 0) + 1

    # #1089 — Supabase sync must succeed before we commit the DB change.
    # Previously a Supabase failure was swallowed and the DB was committed,
    # leaving the two stores desynchronised: new password in RegEngine DB,
    # old password still valid in Supabase. We now treat Supabase sync as a
    # pre-commit gate: if it fails we return 503 without committing so the
    # caller can retry (both stores remain consistent at the old password).
    sb = get_supabase()
    if sb:
        try:
            sb.auth.admin.update_user_by_id(str(user.id), {"password": payload.new_password})
        except Exception as exc:
            logger.warning(
                "change_password_supabase_sync_failed",
                user_id=str(user.id),
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Password updated locally but sync failed; please try again.",
            )

    db.commit()

    # #1088 — revoke all OTHER sessions after password change. The calling
    # session is preserved so the user stays logged in on the device they
    # used to change their password. We extract the current session id from
    # the Authorization header's access token (best-effort; falls back to
    # revoking all sessions if parsing fails).
    current_session_id: Optional[UUID] = None
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_payload = decode_access_token(auth_header[7:])
            sid_raw = token_payload.get("sid") or token_payload.get("session_id")
            if sid_raw:
                current_session_id = UUID(str(sid_raw))
    except Exception:
        pass  # fall back to revoking all sessions

    try:
        other_sessions_revoked = await session_store.revoke_all_user_sessions(
            user.id, except_session_id=current_session_id
        )
    except Exception as exc:
        logger.warning(
            "change_password_session_revoke_failed",
            user_id=str(user.id),
            error=str(exc),
        )
        other_sessions_revoked = 0

    # #1380 — invalidate any elevation tokens previously minted by /confirm.
    elevation_revoked = await _revoke_all_elevation_tokens_for_user(session_store, user.id)

    logger.info(
        "change_password_success",
        user_id=str(user.id),
        other_sessions_revoked=other_sessions_revoked,
        elevation_tokens_revoked=elevation_revoked,
    )
    return {"status": "success"}


class ResetPasswordRequest(BaseModel):
    new_password: str


# #1087: recovery tokens must be fresh. Supabase recovery links are short-lived
# by default, but the *access token* minted after verifyOtp() inherits the
# session TTL. We cap the acceptable age at 15 minutes so a stolen session
# access token (even one originally obtained via OTP) can't be replayed as a
# recovery token hours or days later. This matches common industry practice
# for "re-authentication required" gates (OWASP ASVS V2.5.4).
_RECOVERY_TOKEN_MAX_AGE_SECONDS = 15 * 60

# #1087: valid Supabase amr.method values that indicate the token was issued
# via a code-to-email / code-to-phone / recovery flow (i.e. the caller
# demonstrated possession of the email/phone in the last few minutes). We
# explicitly EXCLUDE "password" (regular login — no proof of email ownership)
# and "oauth"/"saml" (third-party-only proof). "recovery" is what newer
# Supabase versions emit specifically for password-recovery flows; "otp"
# covers older versions and magic-link sessions.
_RECOVERY_ALLOWED_AMR_METHODS = frozenset({"otp", "recovery"})


def _parse_supabase_token_claims(token: str) -> dict:
    """Decode a Supabase JWT's payload WITHOUT verifying the signature.

    Why unverified? ``sb.auth.get_user()`` already verified the signature
    (it calls Supabase's API, which rejects unsigned/stale tokens). We
    just need the ``amr`` and ``iat`` claims for scope checks, and
    re-verifying would require the Supabase JWT secret on our side —
    which would then need to be rotated in lockstep with Supabase.
    """
    try:
        return _jwt.decode(token, options={"verify_signature": False})  # nosemgrep: python.jwt.security.unverified-jwt-decode.unverified-jwt-decode
    except _jwt.PyJWTError:
        return {}


def _enforce_recovery_token_scope(
    token: str,
    *,
    user_id: Optional[str] = None,
) -> None:
    """Reject Supabase tokens that were not issued for password recovery (#1087).

    Previously ``/auth/reset-password`` accepted any valid Supabase access
    token — including regular password-login session tokens. That meant an
    attacker with any stolen access token (XSS, exposed browser storage,
    cross-origin leak) could reset the victim's password and lock them out.

    Two layers of defense applied here:

    1. ``amr`` claim: the Supabase JWT's ``amr`` array records how the
       session was authenticated. Recovery flows always include a
       method in ``_RECOVERY_ALLOWED_AMR_METHODS``. Regular password
       logins have ``method == "password"`` and are refused.
    2. ``iat`` recency: even a legitimately-issued recovery token must
       be fresh. We reject anything older than
       ``_RECOVERY_TOKEN_MAX_AGE_SECONDS`` to limit the blast radius
       of a stolen token.

    Raises ``HTTPException(401)`` on any failure. Uses a single generic
    detail message so we don't leak which check failed to attackers.
    """
    claims = _parse_supabase_token_claims(token)
    amr = claims.get("amr") or []
    iat = claims.get("iat")

    # 1. amr claim must indicate an OTP / recovery flow.
    amr_ok = False
    if isinstance(amr, list):
        for entry in amr:
            if isinstance(entry, dict):
                method = entry.get("method")
                if isinstance(method, str) and method in _RECOVERY_ALLOWED_AMR_METHODS:
                    amr_ok = True
                    break
    if not amr_ok:
        logger.warning(
            "reset_password_wrong_token_scope",
            user_id=user_id,
            amr_methods=[
                entry.get("method")
                for entry in (amr if isinstance(amr, list) else [])
                if isinstance(entry, dict)
            ],
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )

    # 2. Token must be fresh.
    if not isinstance(iat, (int, float)):
        logger.warning("reset_password_token_missing_iat", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )
    age_seconds = int(time.time() - int(iat))
    # Allow small negative skew (clocks drift ±a few seconds); but reject
    # obviously-future iats as a sign of token tampering.
    if age_seconds < -300:
        logger.warning(
            "reset_password_token_future_iat",
            user_id=user_id,
            age_seconds=age_seconds,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )
    if age_seconds > _RECOVERY_TOKEN_MAX_AGE_SECONDS:
        logger.warning(
            "reset_password_stale_token",
            user_id=user_id,
            age_seconds=age_seconds,
            max_age_seconds=_RECOVERY_TOKEN_MAX_AGE_SECONDS,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )


async def _claim_recovery_token_single_use(
    session_store: RedisSessionStore,
    token: str,
    *,
    user_id: Optional[str] = None,
) -> None:
    """Enforce single-use on a recovery-scoped Supabase token (#1087).

    Uses the JWT ``jti`` (or ``session_id`` fallback) as the dedup key.
    First caller wins; subsequent attempts with the same token receive
    401. Fails OPEN on Redis errors — the amr+iat gates are the primary
    defense, and we'd rather allow a legitimate retry during a Redis
    outage than block a user out of their own reset flow.
    """
    claims = _parse_supabase_token_claims(token)
    dedup_id = claims.get("jti") or claims.get("session_id")
    if not dedup_id or not isinstance(dedup_id, str):
        # No stable identifier to dedup on — fail open, but log.
        logger.warning("reset_password_token_missing_jti", user_id=user_id)
        return

    key = f"auth:recovery:used:{dedup_id}"
    try:
        client = await session_store._get_client()
        # SET NX EX: first writer wins, 1h TTL (longer than the 15-min
        # iat window so we cover any clock skew + retries).
        claimed = await client.set(key, "1", nx=True, ex=3600)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "reset_password_single_use_redis_error",
            user_id=user_id,
            error=str(exc),
        )
        return

    if not claimed:
        logger.warning(
            "reset_password_token_replay",
            user_id=user_id,
            dedup_id=dedup_id,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )


@router.post("/reset-password", response_model=ResetPasswordResponse)
@limiter.limit("5/minute")
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Reset a user's password using a Supabase recovery session token.

    The caller must include `Authorization: Bearer <supabase_access_token>`.
    The token is validated via sb.auth.get_user(); the user is looked up by
    email and their argon2 password hash is updated in the RegEngine DB.

    #1087 — in addition to signature validation, the token must:
      * Have an ``amr`` claim indicating an OTP/recovery flow (excludes
        regular password-login tokens and OAuth tokens).
      * Have been issued within the last 15 minutes.
      * Not have been consumed already (single-use via Redis jti check).
    These gates fail-closed on malformed/stale/replayed tokens and emit
    a generic 401 so an attacker can't distinguish failure modes.
    """
    # 1. Extract the Supabase access token from the Authorization header
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )
    supabase_token = auth_header[7:]

    # 2. Validate the token with Supabase (service-role client)
    sb = get_supabase()
    if not sb:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unavailable",
        )

    try:
        user_response = sb.auth.get_user(supabase_token)
        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired recovery token",
            )
        sb_user = user_response.user
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("reset_password_token_validation_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired recovery token",
        )

    # #1087 — Scope check. Supabase's ``get_user()`` only validates that the
    # token is a valid session token for SOME user; it doesn't distinguish
    # "password login session" from "recovery session". Before this fix, any
    # stolen password-session token could call reset-password and lock the
    # victim out. These gates reject any token that wasn't issued via an
    # OTP/recovery flow, or is older than 15 minutes.
    sb_user_id = getattr(sb_user, "id", None)
    _enforce_recovery_token_scope(supabase_token, user_id=str(sb_user_id) if sb_user_id else None)
    await _claim_recovery_token_single_use(
        session_store, supabase_token, user_id=str(sb_user_id) if sb_user_id else None
    )

    email = getattr(sb_user, "email", None)
    if not email:
        raise HTTPException(status_code=400, detail="No email associated with token")

    # 3. Validate the new password against the configured policy
    try:
        validate_password(payload.new_password, user_context={"email": email})
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    # 4. Find the user in the RegEngine DB (the authoritative store for login)
    normalized_email = email.strip().lower()
    user = db.execute(
        select(UserModel).where(UserModel.email == normalized_email)
    ).scalar_one_or_none()

    if not user:
        logger.warning("reset_password_user_not_found", email=mask_email(normalized_email))
        raise HTTPException(status_code=404, detail="User not found")

    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account disabled")

    # 5. Update the argon2 hash in the RegEngine DB
    user.password_hash = get_password_hash(payload.new_password)

    # #1349 — bump token_version so every outstanding JWT becomes stale.
    # get_current_user rejects tokens whose `tv` claim is below this value.
    # Coalesce None to 0 for rows created before the column existed.
    current_version = int(getattr(user, "token_version", 0) or 0)
    user.token_version = current_version + 1

    # 6. Keep Supabase in sync so both stores stay aligned
    try:
        sb.auth.admin.update_user_by_id(str(sb_user.id), {"password": payload.new_password})
    except Exception as exc:
        # Non-fatal — the RegEngine DB is the authoritative login store
        logger.warning(
            "reset_password_supabase_sync_failed",
            user_id=str(sb_user.id),
            error=str(exc),
        )

    db.commit()

    # #1349 — revoke every active session so stolen refresh tokens cannot be
    # replayed. This runs AFTER the commit so a Redis outage does not block
    # the password change itself. A Redis miss is logged but not fatal; the
    # token_version bump above is the primary defense.
    try:
        revoked_count = await session_store.revoke_all_for_user(user.id)
    except Exception as exc:
        logger.warning(
            "reset_password_session_revoke_failed",
            user_id=str(user.id),
            error=str(exc),
        )
        revoked_count = 0

    # #1380 — outstanding elevation tokens are now stale too.
    elevation_revoked = await _revoke_all_elevation_tokens_for_user(session_store, user.id)

    logger.info(
        "reset_password_success",
        user_id=str(user.id),
        sessions_revoked=revoked_count,
        elevation_tokens_revoked=elevation_revoked,
        new_token_version=user.token_version,
    )
    return {"status": "success"}


# ── Re-authentication gate for sensitive operations — OWASP API6:2023 (#976) ──

class ConfirmPasswordRequest(BaseModel):
    password: str = Field(max_length=128)


# #1380 — elevation-token jtis live in this Redis key for the token's full TTL.
# require_reauth consults the set; password-change / reset bulk-revoke by user.
def _elevation_jti_key(jti: str) -> str:
    return f"{_ELEVATION_JTI_KEY_PREFIX}{jti}"


@router.post("/confirm")
@limiter.limit("5/minute")
async def confirm_password(
    payload: ConfirmPasswordRequest,
    request: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Verify password and return short-lived elevation token for sensitive ops.

    #1340 — wrapped in both SlowAPI @limiter.limit and the same per-email/cumulative
    lockout counters that protect /auth/login. A stolen access token no longer gives
    the attacker unlimited password guesses.
    #1380 — elevation payload now carries tenant_id (scoped to active tenant) and
    the jti is persisted so it can be revoked individually or in bulk.
    """
    normalized_email = (current_user.email or "").strip().lower()

    # Same lockout infrastructure as /login (#1340).
    await _check_account_lockout(session_store, normalized_email)
    await _check_email_rate_limit(session_store, normalized_email)

    if not verify_password(payload.password, current_user.password_hash):
        logger.warning("confirm_password_failed", user_id=str(current_user.id))
        await _record_failed_login_attempt(session_store, normalized_email)
        await _record_lockout_attempt(session_store, normalized_email)
        raise HTTPException(status_code=401, detail="Incorrect password")

    # Success — clear the failure counters so one stray typo doesn't linger.
    await _clear_email_rate_limit(session_store, normalized_email)

    # #1380 — bind the elevation token to a specific tenant. We prefer the
    # ACTING tenant already set on the RLS session (via get_current_user),
    # falling back to the first active membership if the session has no
    # tenant context yet.
    acting_tenant_id: Optional[UUID] = None
    try:
        from .models import TenantContext as _TC
        acting_tenant_id = _TC.get_tenant_context(db)
    except Exception:
        acting_tenant_id = None
    if acting_tenant_id is None:
        mem = db.execute(
            select(MembershipModel)
            .join(TenantModel, MembershipModel.tenant_id == TenantModel.id)
            .where(
                MembershipModel.user_id == current_user.id,
                MembershipModel.is_active == True,  # noqa: E712
                TenantModel.status == "active",
            )
        ).scalars().first()
        if mem is not None:
            acting_tenant_id = mem.tenant_id

    if acting_tenant_id is None:
        raise HTTPException(status_code=403, detail="No active tenant for elevation")

    # Pre-allocate jti so we can store it before handing out the token.
    elevation_jti = str(uuid.uuid4())

    elevation_token = create_access_token(
        data={
            "sub": str(current_user.id),
            "elevated": True,
            "tenant_id": str(acting_tenant_id),
            "jti": elevation_jti,
            "tv": int(getattr(current_user, "token_version", 0) or 0),
        },
        expires_delta=timedelta(seconds=_ELEVATION_TOKEN_TTL_SECONDS),
    )

    # Record the jti so it (a) can be individually revoked, and (b) can be
    # scoped to a specific user for bulk-revoke on password change. Best-effort:
    # if Redis is down the token still has a short TTL as a fallback.
    try:
        client = await session_store._get_client()
        await client.setex(
            _elevation_jti_key(elevation_jti),
            _ELEVATION_TOKEN_TTL_SECONDS,
            str(current_user.id),
        )
    except Exception as exc:
        logger.warning("elevation_jti_store_failed", user_id=str(current_user.id), error=str(exc))

    logger.info(
        "elevation_token_issued",
        user_id=str(current_user.id),
        tenant_id=str(acting_tenant_id),
        jti=elevation_jti,
    )
    return {"elevation_token": elevation_token, "expires_in": _ELEVATION_TOKEN_TTL_SECONDS}


async def require_reauth(
    request: Request,
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """FastAPI dependency — requires a recent elevation token for sensitive ops.

    #1380 hardening:
      * Rejects tokens that are missing ``tenant_id`` or whose tenant differs
        from the caller's current acting tenant.
      * Rejects tokens whose jti has been revoked via the short-lived Redis
        set populated at /confirm.
      * Rejects tokens whose ``tv`` claim is stale (password was changed
        between /confirm and the sensitive call).
    """
    elevation_header = request.headers.get("X-Elevation-Token")
    if not elevation_header:
        raise HTTPException(status_code=403, detail="Re-authentication required for this operation")
    try:
        payload = decode_access_token(elevation_header)
        if not payload.get("elevated"):
            raise HTTPException(status_code=403, detail="Invalid elevation token")
        if str(payload.get("sub")) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Elevation token user mismatch")

        # Tenant binding (#1380.1) — compare the token's claim to the caller's
        # current acting tenant. We re-parse the caller's access token from the
        # Authorization header rather than relying on request.state, because
        # FastAPI does not automatically stash tenant_id there and we want this
        # dependency to work with zero extra wiring at every call site.
        token_tid = payload.get("tenant_id") or payload.get("tid")
        if not token_tid:
            raise HTTPException(status_code=403, detail="Elevation token missing tenant")
        acting_tid: Optional[str] = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                access_payload = decode_access_token(auth_header[7:])
                acting_tid = access_payload.get("tenant_id") or access_payload.get("tid")
            except Exception:
                acting_tid = None
        if acting_tid and str(token_tid) != str(acting_tid):
            logger.warning(
                "elevation_tenant_mismatch",
                user_id=str(current_user.id),
                token_tid=str(token_tid),
                acting_tid=str(acting_tid),
            )
            raise HTTPException(status_code=403, detail="Elevation token tenant mismatch")

        # jti revocation (#1380.2) — the jti is persisted for the token's TTL
        # in Redis when /confirm mints it. A password change deletes the entry
        # via _revoke_all_elevation_tokens_for_user; a missing entry means
        # either "revoked" or "naturally expired" — either way, reject.
        jti = payload.get("jti")
        if not jti:
            raise HTTPException(status_code=403, detail="Elevation token missing jti")
        try:
            client = await session_store._get_client()
            stored = await client.get(_elevation_jti_key(str(jti)))
        except Exception:
            stored = None
        if stored is None:
            raise HTTPException(status_code=403, detail="Elevation token revoked or expired")

        # token_version mismatch (#1380 + #1349) — a password change bumps tv
        # and must invalidate any elevation token in flight.
        tv_claim = payload.get("tv")
        user_tv = int(getattr(current_user, "token_version", 0) or 0)
        if tv_claim is not None and int(tv_claim) < user_tv:
            raise HTTPException(status_code=403, detail="Elevation token stale")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=403, detail="Elevation token expired or invalid")


# ── Admin: Unlock locked account (#972) ──

@router.post("/unlock", dependencies=[Depends(PermissionChecker("admin:manage_users"))])
async def unlock_account(
    email: str = Query(...),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Admin endpoint to unlock a locked-out account."""
    normalized = email.strip().lower()
    await _clear_lockout(session_store, normalized)
    await _clear_email_rate_limit(session_store, normalized)
    logger.info("account_unlocked", email=mask_email(normalized))
    return {"unlocked": True, "email": mask_email(normalized)}
