from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from datetime import timedelta, datetime, timezone
import inspect
import structlog
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from uuid import UUID
import uuid
import re
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


async def _persist_session(
    session_store: RedisSessionStore,
    session_data: SessionData,
    *,
    context: str,
    user_id: UUID,
) -> None:
    """Persist session to Redis with one retry. Raises 503 on failure.

    A missing session record means the refresh token can never be validated,
    creating a zombie session that silently expires and kicks the user out.
    Failing fast with 503 is better than a half-working login.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            await session_store.create_session(session_data)
            return
        except Exception as exc:
            last_exc = exc
            if attempt == 0:
                logger.warning(
                    "session_store_retry",
                    context=context,
                    user_id=str(user_id),
                    error=str(exc),
                )
                await asyncio.sleep(0.25)  # brief back-off before retry

    # Both attempts failed
    logger.error(
        "session_store_unavailable",
        context=context,
        user_id=str(user_id),
        error=str(last_exc),
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Session service temporarily unavailable. Please try again.",
    )

class LoginRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    tenant_id: Optional[UUID] = None
    user: Dict
    available_tenants: List[Dict]

class RegisterRequest(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)
    tenant_name: str = Field(max_length=100)
    partner_tier: Optional[str] = Field(None, pattern=r"^(founding|standard)$")


class SignupAcceptedResponse(BaseModel):
    detail: str


_SIGNUP_ACCEPTED_DETAIL = "Check your inbox for confirmation instructions."


def _signup_accepted_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=SignupAcceptedResponse(detail=_SIGNUP_ACCEPTED_DETAIL).model_dump(),
    )


class UserResponse(BaseModel):
    id: UUID
    email: str
    is_sysadmin: bool
    status: str


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


def _slugify_tenant_name(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return base or "tenant"


def _ensure_unique_tenant_slug(db: Session, tenant_name: str) -> str:
    base_slug = _slugify_tenant_name(tenant_name)
    slug = base_slug
    suffix = 2
    while db.execute(select(TenantModel).where(TenantModel.slug == slug)).scalar_one_or_none():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug

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

@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store)
):
    # 1. Verify User (normalize email to lowercase for case-insensitive match)
    normalized_login_email = payload.email.strip().lower()

    # Account lockout check — cumulative failures across all IPs (#972)
    await _check_account_lockout(session_store, normalized_login_email)
    # Per-email rate limit — check before any DB work to prevent enumeration
    await _check_email_rate_limit(session_store, normalized_login_email)

    stmt = select(UserModel).where(UserModel.email == normalized_login_email)
    user = db.execute(stmt).scalar_one_or_none()

    # #1082 — verify_login() runs argon2 against a module-level dummy
    # hash when user is None, so the unknown-email and wrong-password
    # branches both pay the full verify cost. Previously the
    # ``not user or not verify_password(...)`` short-circuited the
    # argon2 op on unknown emails, making response latency a reliable
    # account-enumeration oracle. Both branches must also fire the
    # same Redis side-effects (failed-login counter + lockout ramp) so
    # subsequent-request state can't become a secondary timing oracle.
    if not verify_login(payload.password, user):
        logger.warning("login_failed", reason="invalid_credentials")
        await _record_failed_login_attempt(session_store, normalized_login_email)
        await _record_lockout_attempt(session_store, normalized_login_email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account disabled")

    # 2. Get Memberships
    stmt_mem = select(MembershipModel, TenantModel)\
        .join(TenantModel, MembershipModel.tenant_id == TenantModel.id)\
        .where(MembershipModel.user_id == user.id)
    results = db.execute(stmt_mem).all()

    available_tenants = []
    active_tenant_id = None
    active_tenant_status = None

    for mem, tenant in results:
        available_tenants.append({"id": tenant.id, "name": tenant.name, "slug": tenant.slug})
        if not active_tenant_id:
            active_tenant_id = tenant.id
            active_tenant_status = tenant.status
    
    # Clear failed-attempt counters on successful credential verification
    await _clear_email_rate_limit(session_store, normalized_login_email)
    await _clear_lockout(session_store, normalized_login_email)

    # 3. Create Session in Redis (replaces PostgreSQL session)
    raw_refresh_token = create_refresh_token()
    token_hash = hash_token(raw_refresh_token)
    family_id = uuid.uuid4()
    
    session_data = SessionData(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash=token_hash,
        family_id=family_id,
        created_at=datetime.now(timezone.utc),
        last_used_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=request.headers.get("User-Agent", "Unknown"),
        ip_address=request.client.host if request.client else "0.0.0.0"
    )
    
    # Persist session — retries once, then fails with 503 so the user
    # gets a clean error instead of a zombie session that can't refresh.
    await _persist_session(
        session_store, session_data,
        context="login",
        user_id=user.id,
    )

    # 4. Create Access Token
    access_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "tenant_id": str(active_tenant_id) if active_tenant_id else None,  # For RLS
        "tid": str(active_tenant_id) if active_tenant_id else None,  # Backward compat
        "tenant_status": active_tenant_status,  # Middleware checks this to reject suspended tenants
        # #1349 / #1375 — token_version binds this access token to the user's
        # current password/session generation. Bumped on reset or logout-all.
        "tv": int(getattr(user, "token_version", 0) or 0),
    }

    access_token = create_access_token(access_token_data)

    # ── Login is complete at this point ──
    # The access token and session are ready. Everything below is
    # best-effort bookkeeping that must never block authentication.

    logger.info(
        "login_success",
        user_id=str(user.id),
        session_id=str(session_data.id),
    )

    response = TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        tenant_id=active_tenant_id,
        user={"id": str(user.id), "email": user.email, "is_sysadmin": user.is_sysadmin},
        available_tenants=available_tenants
    )

    # Best-effort side-effects: audit log + last_login_at
    # Failures are logged but never prevent the user from logging in.
    try:
        if active_tenant_id:
            AuditLogger.log_event(
                db,
                tenant_id=active_tenant_id,
                event_type="user.login",
                action="session.create",
                event_category="authentication",
                actor_id=user.id,
                resource_type="session",
                resource_id=str(session_data.id),
            )
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as e:
        logger.warning("login_side_effects_failed", user_id=str(user.id), error=str(e))
        db.rollback()

    return response


@router.post(
    "/signup",
    response_model=SignupAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("5/minute")
async def signup(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Self-serve signup that creates tenant + owner membership and returns session tokens.

    Consistency model (three systems: Supabase + Postgres + Redis):

    * Redis ``create_session`` is performed BEFORE ``db.commit()`` so that a
      Redis outage rolls the Postgres transaction back cleanly (no orphan
      tenant / no 409 on retry). See #1403 / PR #1688.
    * If ``db.commit()`` fails AFTER Redis persisted, we best-effort delete
      the Redis session. If THAT ``delete_session`` call also fails (the
      most likely correlated failure: Redis is usually down for both calls),
      a dangling Redis session survives pointing at a rolled-back user.
      That residual orphan is bounded by the session TTL (see
      ``REFRESH_TOKEN_EXPIRE_DAYS`` — ``RedisSessionStore.create_session``
      always sets an expiry via ``EXPIRE`` / ``SETEX``), so the dangling
      session self-cleans without operator intervention. The original DB
      commit exception is re-raised to the caller, with the Redis cleanup
      failure explicitly attached via ``__context__`` so Sentry sees the
      DB error as the primary (actionable) failure and the Redis cleanup
      error as the chained secondary cause.
    * Supabase-user orphan cleanup on DB rollback is a separate layer
      tracked by #1090.

    See #1692 for the tests that lock the above invariants in place.
    """
    normalized_email = payload.email.strip().lower()
    tenant_name = payload.tenant_name.strip()
    if not tenant_name:
        raise HTTPException(status_code=400, detail="Tenant name is required")

    existing_user = db.execute(
        select(UserModel).where(UserModel.email == normalized_email)
    ).scalar_one_or_none()
    if existing_user:
        # Return the exact same accepted response as successful signup to
        # prevent email enumeration (#1861). We do NOT send a confirmation
        # email here to avoid email-bombing the existing user.
        logger.info("signup_duplicate_masked", email=mask_email(normalized_email))
        return _signup_accepted_response()

    try:
        validate_password(payload.password, user_context={"email": normalized_email})
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=400, detail=exc.message)

    # #1090 — Create the DB row (flush) FIRST; only call Supabase once we know
    # the user doesn't already exist in our DB.  If Supabase creation fails the
    # DB transaction is rolled back cleanly.  The reverse order (Supabase first,
    # DB second) left orphaned Supabase accounts whenever the DB insert failed.
    new_user_id = uuid.uuid4()
    new_user = UserModel(
        id=new_user_id,
        email=normalized_email,
        password_hash=get_password_hash(payload.password),
        is_sysadmin=False,
        status="active",
    )
    db.add(new_user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("signup_duplicate_race_rejected", email=mask_email(normalized_email))
        return _signup_accepted_response()

    # #1090 — Supabase provisioning happens AFTER db.flush() succeeds.  If
    # Supabase fails we roll back the DB transaction so the caller can retry.
    supabase_user_id: Optional[UUID] = None
    sb = get_supabase()
    if sb:
        try:
            supabase_response = sb.auth.admin.create_user(
                {
                    "email": normalized_email,
                    "password": payload.password,
                    "email_confirm": True,
                    "user_metadata": {"tenant_name": tenant_name},
                }
            )
            supabase_user = getattr(supabase_response, "user", None)
            if supabase_user and getattr(supabase_user, "id", None):
                supabase_user_id = UUID(str(supabase_user.id))
        except (OSError, TimeoutError, ConnectionError, ValueError, RuntimeError, AttributeError) as exc:  # pragma: no cover - external dependency behavior
            logger.warning("supabase_signup_provisioning_failed", email=mask_email(normalized_email), error=str(exc))
            # Non-fatal: we continue without Supabase linkage rather than
            # blocking signup entirely. Supabase orphan cleanup handled by
            # _cleanup_supabase_user if needed on later failure paths.

    tenant_settings: dict = {
        "onboarding": {
            "workspace_setup_completed": False,
            "facility_created": False,
            "ftl_check_completed": False,
            "first_document_imported": False,
            "team_member_invited": False,
            "mock_drill_run": False,
        },
    }
    if payload.partner_tier:
        tenant_settings["partner_tier"] = payload.partner_tier
        logger.info("design_partner_signup", email=mask_email(normalized_email), tier=payload.partner_tier)

    new_tenant = TenantModel(
        name=tenant_name,
        slug=_ensure_unique_tenant_slug(db, tenant_name),
        status="active",
        settings=tenant_settings,
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

    raw_refresh_token = create_refresh_token()
    token_hash = hash_token(raw_refresh_token)
    family_id = uuid.uuid4()
    session_data = SessionData(
        id=uuid.uuid4(),
        user_id=new_user.id,
        refresh_token_hash=token_hash,
        family_id=family_id,
        created_at=datetime.now(timezone.utc),
        last_used_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        user_agent=request.headers.get("User-Agent", "Unknown"),
        ip_address=request.client.host if request.client else "0.0.0.0",
    )

    # #1403 — Persist session to Redis BEFORE committing the DB.
    # Previous order (commit → Redis) left an orphan tenant + membership
    # whenever Redis was unavailable: the client got 503, saw no session,
    # retried the same email, and was blocked by a 409 "user already exists"
    # with no way to recover. By persisting Redis inside the transaction,
    # a Redis failure rolls the tenant/user/membership back and the client
    # can simply retry. Supabase-user orphans are a separate layer (#1090).
    try:
        await _persist_session(
            session_store, session_data,
            context="signup",
            user_id=new_user.id,
        )
    except HTTPException:
        # _persist_session already logged; roll back the DB so the user can
        # retry signup with the same email once Redis recovers.
        db.rollback()
        raise

    # Commit the user + tenant + membership rows now that the session is
    # durable in Redis. If the commit itself fails, we best-effort delete
    # the Redis session we just created so it doesn't reference a ghost user.
    #
    # Correlated-failure note (#1692): Redis is the reason this rollback
    # path exists in the first place, so the most likely mode is that
    # ``delete_session`` ALSO fails. In that case the dangling session is
    # bounded by its TTL (set by ``RedisSessionStore.create_session``).
    # We explicitly attach the cleanup error to the DB exception's
    # ``__context__`` so callers / Sentry see the full picture (DB is the
    # primary cause, Redis-cleanup is the secondary) without the cleanup
    # failure masking the actionable DB error.
    try:
        db.commit()
    except Exception as commit_exc:
        db.rollback()

        # #1090 — Compensating cleanup: if the DB insert rolls back but a
        # Supabase user was already created, delete it so the email is not
        # permanently locked in Supabase with no matching DB record.
        if supabase_user_id is not None:
            _sb = get_supabase()
            if _sb:
                try:
                    _sb.auth.admin.delete_user(str(supabase_user_id))
                    logger.info(
                        "signup_supabase_orphan_cleaned",
                        supabase_user_id=str(supabase_user_id),
                        email=mask_email(normalized_email),
                    )
                except Exception as sb_cleanup_exc:
                    logger.warning(
                        "signup_supabase_orphan_cleanup_failed",
                        supabase_user_id=str(supabase_user_id),
                        email=mask_email(normalized_email),
                        error=str(sb_cleanup_exc),
                        residual_orphan="supabase_user_dangling",
                    )

        try:
            await session_store.delete_session(session_data.id)
        except Exception as cleanup_exc:
            # Explicit exception chaining: attach the cleanup error to
            # the commit error's __context__ so operators can still
            # reach it from the trace. We DO NOT use ``raise from`` —
            # that would set __cause__ and make the cleanup error look
            # like the root cause, which is wrong: the DB failure is
            # the root cause, Redis-cleanup is the secondary.
            commit_exc.__context__ = cleanup_exc
            logger.warning(
                "signup_session_cleanup_failed",
                session_id=str(session_data.id),
                user_id=str(new_user.id),
                error=str(cleanup_exc),
                residual_orphan="redis_session_dangling_until_ttl",
            )
        raise

    access_token_data = {
        "sub": str(new_user.id),
        "email": new_user.email,
        "tenant_id": str(new_tenant.id),
        "tid": str(new_tenant.id),
        "tv": int(getattr(new_user, "token_version", 0) or 0),
    }
    access_token = create_access_token(access_token_data)

    logger.info(
        "signup_success",
        user_id=str(new_user.id),
        tenant_id=str(new_tenant.id),
        supabase_user_linked=bool(supabase_user_id),
    )

    response = TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh_token,
        tenant_id=new_tenant.id,
        user={"id": str(new_user.id), "email": new_user.email, "is_sysadmin": new_user.is_sysadmin},
        available_tenants=[{"id": new_tenant.id, "name": new_tenant.name, "slug": new_tenant.slug}],
    )

    # Best-effort side-effects: audit log + funnel event
    try:
        AuditLogger.log_event(
            db,
            tenant_id=new_tenant.id,
            event_type="tenant.create",
            action="tenant.create",
            event_category="tenant_management",
            actor_id=new_user.id,
            resource_type="tenant",
            resource_id=str(new_tenant.id),
            metadata={"tenant_name": new_tenant.name, "signup": True},
        )
        emit_funnel_event(
            tenant_id=str(new_tenant.id),
            event_name="signup_completed",
            metadata={
                "source": "auth.signup",
                "user_id": str(new_user.id),
            },
            db_session=db,
        )
        db.commit()
    except Exception as e:
        logger.warning("signup_side_effects_failed", user_id=str(new_user.id), error=str(e))
        db.rollback()

    # Do not return tokens from signup (#1861). Returning a TokenResponse for
    # new emails but a message for existing emails made account enumeration
    # trivial via response-body shape. The user can authenticate through
    # /auth/login after account creation.
    return _signup_accepted_response()



class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh_session(
    payload: RefreshRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    input_hash = hash_token(payload.refresh_token)

    # Atomically claim the token — GETDEL ensures only one concurrent
    # refresh request succeeds. The second request finds the mapping gone
    # and gets 401, preventing the "last write wins" race condition where
    # two tabs refresh simultaneously and one gets an invalidated token.
    session = await session_store.claim_session_by_token(input_hash)

    if not session:
        # SECURITY (#1859): distinguish "never valid" from "already rotated".
        # If the hash appears in the used-token tombstone, this is refresh-
        # token reuse — either a theft replay or a double-spend. Revoke the
        # entire session family so the thief (and victim) are forced to
        # re-authenticate, and emit a high-severity audit signal.
        reused_session_id = await _maybe_await(
            session_store.check_token_reuse(input_hash)
        )
        if reused_session_id is not None:
            reused_session = await _maybe_await(
                session_store.get_session(reused_session_id)
            )
            if reused_session is not None:
                await _maybe_await(
                    session_store.revoke_all_for_family(reused_session.family_id)
                )
                try:
                    audit_tenant_id = db.execute(
                        select(MembershipModel.tenant_id)
                        .where(
                            MembershipModel.user_id == reused_session.user_id,
                            MembershipModel.is_active == True,  # noqa: E712
                        )
                        .limit(1)
                    ).scalar_one_or_none()
                    if audit_tenant_id:
                        AuditLogger.log_event(
                            db,
                            tenant_id=audit_tenant_id,
                            event_type="auth.refresh_token_reuse",
                            action="refresh_token.reuse_detected",
                            event_category="authentication",
                            severity="critical",
                            actor_id=reused_session.user_id,
                            actor_ip=request.client.host if request.client else None,
                            actor_ua=request.headers.get("User-Agent"),
                            resource_type="session_family",
                            resource_id=str(reused_session.family_id),
                            endpoint="/auth/refresh",
                            metadata={
                                "session_id": str(reused_session_id),
                                "token_hash_prefix": input_hash[:8],
                                "response": "session_family_revoked",
                            },
                        )
                        db.commit()
                    else:
                        logger.warning(
                            "refresh_token_reuse_audit_skipped_no_tenant",
                            session_id=str(reused_session_id),
                            family_id=str(reused_session.family_id),
                            user_id=str(reused_session.user_id),
                        )
                except Exception as exc:
                    db.rollback()
                    logger.warning(
                        "refresh_token_reuse_audit_failed",
                        session_id=str(reused_session_id),
                        family_id=str(reused_session.family_id),
                        error=str(exc),
                    )
                logger.warning(
                    "refresh_token_reuse_detected",
                    session_id=str(reused_session_id),
                    family_id=str(reused_session.family_id),
                    user_id=str(reused_session.user_id),
                    token_hash=input_hash[:8],
                )
            else:
                logger.warning(
                    "refresh_token_reuse_detected_session_gone",
                    session_id=str(reused_session_id),
                    token_hash=input_hash[:8],
                )
            raise HTTPException(status_code=401, detail="Refresh token reuse detected")
        logger.warning("refresh_invalid_token", token_hash=input_hash[:8])
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if session.is_revoked:
        # Session revoked - potential theft
        logger.warning("refresh_attempt_revoked_session", session_id=str(session.id))
        raise HTTPException(status_code=401, detail="Session revoked")

    if session.expires_at < datetime.now(timezone.utc):
        logger.warning("refresh_expired_session", session_id=str(session.id))
        raise HTTPException(status_code=401, detail="Session expired")

    # ROTATION: Generate new refresh token
    new_raw_refresh_token = create_refresh_token()
    new_hash = hash_token(new_raw_refresh_token)

    # Update session with new token hash and timestamps.
    # old_token_hash already deleted by claim_session_by_token (GETDEL).
    await _maybe_await(
        session_store.update_session(
        session.id,
        {
            "refresh_token_hash": new_hash,
            "last_used_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()
        },
        new_token_hash=new_hash,
        old_token_hash=input_hash,
    ))

    # SECURITY (#1859): tombstone the consumed hash so a replay can be
    # detected as reuse (not just "unknown token"). TTL matches refresh
    # expiration so the tombstone outlives any legitimate replay window.
    await _maybe_await(
        session_store.mark_token_used(
            input_hash,
            session.id,
            ttl_seconds=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )
    )

    # Re-issue Access Token
    user = db.get(UserModel, session.user_id)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # #1379 — preserve the ORIGINAL acting tenant from the incoming access
    # token. Re-deriving from `memberships[0]` without ORDER BY silently
    # switches tenants for multi-tenant users because PostgreSQL does not
    # guarantee row order. The caller proves which tenant they were acting
    # under by presenting the old access token alongside the refresh token.
    original_tenant_id: Optional[UUID] = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            old_payload = decode_access_token(auth_header[7:])
            old_tid = old_payload.get("tenant_id") or old_payload.get("tid")
            if old_tid:
                original_tenant_id = UUID(str(old_tid))
        except Exception as exc:
            # An expired-but-parseable token is fine here — we still trust the
            # tenant claim since the session row already authenticated the
            # user. We only fall back to membership lookup if the header is
            # missing or entirely malformed.
            try:
                import jwt as _jwt
                unverified = _jwt.decode(auth_header[7:], options={"verify_signature": False})  # nosemgrep: python.jwt.security.unverified-jwt-decode.unverified-jwt-decode
                old_tid = unverified.get("tenant_id") or unverified.get("tid")
                if old_tid:
                    original_tenant_id = UUID(str(old_tid))
            except Exception:
                logger.warning("refresh_old_token_unparseable", error=str(exc))

    # Enforce that the user is still a member of the original acting tenant
    # AND that the tenant is still active. If either check fails we refuse
    # the refresh — we do NOT silently downgrade to a different tenant.
    stmt_mem = (
        select(MembershipModel)
        .join(TenantModel, MembershipModel.tenant_id == TenantModel.id)
        .where(
            MembershipModel.user_id == user.id,
            MembershipModel.is_active == True,  # noqa: E712
            TenantModel.status == "active",
        )
    )
    memberships = db.execute(stmt_mem).scalars().all()
    active_tenant_ids = {m.tenant_id for m in memberships}

    if original_tenant_id is not None:
        if original_tenant_id not in active_tenant_ids:
            logger.warning(
                "refresh_tenant_no_longer_active_member",
                user_id=str(user.id),
                tenant_id=str(original_tenant_id),
            )
            raise HTTPException(status_code=403, detail="Tenant membership no longer active")
        active_tenant_id = original_tenant_id
    else:
        # No prior tenant claim (e.g. legacy client that never carried one).
        # Fall back to deterministic ordering so refreshes are at least
        # stable, rather than racing on VACUUM/HOT updates.
        memberships_sorted = sorted(memberships, key=lambda m: str(m.tenant_id))
        active_tenant_id = memberships_sorted[0].tenant_id if memberships_sorted else None

    if not active_tenant_id:
        logger.warning("refresh_no_active_tenant", user_id=str(user.id))
        raise HTTPException(status_code=403, detail="No active tenant available")

    # #1401 — Re-query the real tenant status instead of hardcoding "active".
    # The query above already filters for active memberships/tenants, but the
    # status we embed in the token should reflect the DB truth at refresh time.
    real_tenant_status: Optional[str] = None
    if active_tenant_id:
        tenant_row = db.get(TenantModel, active_tenant_id)
        if tenant_row:
            real_tenant_status = tenant_row.status
        else:
            real_tenant_status = "active"  # defensive fallback; query above already enforced it
    if real_tenant_status is None:
        logger.warning("refresh_no_tenant_status", user_id=str(user.id), tenant_id=str(active_tenant_id))

    access_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "tenant_id": str(active_tenant_id) if active_tenant_id else None,  # For RLS
        "tid": str(active_tenant_id) if active_tenant_id else None,  # Backward compat
        "tenant_status": real_tenant_status,  # #1401: re-queried, never hardcoded
        "tv": int(getattr(user, "token_version", 0) or 0),
    }
    access_token = create_access_token(access_token_data)

    db.commit()

    logger.info("token_refreshed", user_id=str(user.id), session_id=str(session.id))
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_raw_refresh_token,
        tenant_id=active_tenant_id,
        user={"id": str(user.id), "email": user.email, "is_sysadmin": user.is_sysadmin},
        available_tenants=[] # Don't need full list on refresh
    )


@router.get("/sessions", response_model=SessionListResponse, dependencies=[Depends(get_current_user)])
async def list_sessions(
    pagination: PaginationParams = Depends(),
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    # Get all active sessions for user from Redis
    sessions = await session_store.list_user_sessions(current_user.id, active_only=True)
    total = len(sessions)
    sessions = sessions[pagination.skip : pagination.skip + pagination.limit]

    return {
        "items": [
            {
                "id": str(s.id),
                "created_at": s.created_at.isoformat(),
                "last_used_at": s.last_used_at.isoformat(),
                "user_agent": s.user_agent,
                "ip_address": s.ip_address,
            }
            for s in sessions
        ],
        "total": total,
        "skip": pagination.skip,
        "limit": pagination.limit,
    }

@router.post("/sessions/{session_id}/revoke", response_model=SessionRevokeResponse, dependencies=[Depends(get_current_user)])
async def revoke_session(
    session_id: UUID,
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store)
):
    # Get session from Redis
    session = await session_store.get_session(session_id)
    
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Revoke in Redis
    await session_store.revoke_session(session_id)
    
    logger.info("session_revoked", session_id=str(session_id), user_id=str(current_user.id))
    
    return {"status": "revoked"}

@router.post("/logout-all", response_model=RevokeAllSessionsResponse, dependencies=[Depends(get_current_user)])
async def revoke_all_sessions(
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Revoke every session + access token for the calling user.

    #1375 — previous implementation only flipped is_revoked on the Redis session
    row, so outstanding access tokens kept working until their natural 60-min
    expiry. We now ALSO bump users.token_version so get_current_user rejects any
    access token minted before this call. The same mechanism is used by
    /auth/reset-password (#1349).
    """
    # 1. Revoke Redis session rows (future /refresh attempts will 401).
    count = await session_store.revoke_all_user_sessions(current_user.id)

    # 2. Bump token_version to kill outstanding access tokens immediately.
    user = db.get(UserModel, current_user.id)
    if user is not None:
        current_version = int(getattr(user, "token_version", 0) or 0)
        user.token_version = current_version + 1
        db.commit()
        new_version = user.token_version
    else:
        new_version = None

    # 3. Revoke any outstanding elevation tokens too.
    elevation_revoked = await _revoke_all_elevation_tokens_for_user(
        session_store, current_user.id
    )

    logger.info(
        "all_sessions_revoked",
        user_id=str(current_user.id),
        count=count,
        elevation_tokens_revoked=elevation_revoked,
        new_token_version=new_version,
    )

    return {"status": "success", "revoked_count": count}



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
_ELEVATION_JTI_KEY_PREFIX = "elevation_jti:"
_ELEVATION_TOKEN_TTL_SECONDS = 300  # 5 minutes — matches token exp_delta below


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


async def _revoke_all_elevation_tokens_for_user(
    session_store: RedisSessionStore, user_id: UUID
) -> int:
    """Scan the elevation-jti keyspace and delete entries belonging to this user.

    Called from password change / reset paths so that a 5-minute elevation token
    minted at T+0 cannot outlive a password change at T+1 (#1380).
    """
    try:
        client = await session_store._get_client()
        cursor = 0
        revoked = 0
        pattern = f"{_ELEVATION_JTI_KEY_PREFIX}*"
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=200)
            for key in keys:
                val = await client.get(key)
                if val == str(user_id):
                    await client.delete(key)
                    revoked += 1
            if cursor == 0:
                break
        return revoked
    except Exception as exc:
        logger.warning("elevation_revoke_all_failed", user_id=str(user_id), error=str(exc))
        return 0


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
