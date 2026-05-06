"""Signup route — extracted from auth_routes.py (Phase 1 sub-split 5/N).

Exposes:
  router   — APIRouter with /signup registered; included by auth_routes.py
  signup   — the handler function (re-exported from auth_routes for compat)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import AuditLogger
from ..auth_utils import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    hash_token,
)
from ..database import get_session
from ..dependencies import get_session_store
from ..password_policy import validate_password, PasswordPolicyError
from ..session_store import RedisSessionStore, SessionData
from ..sqlalchemy_models import MembershipModel, RoleModel, TenantModel, UserModel
from .schemas import (
    RegisterRequest,
    SignupAcceptedResponse,
    TokenResponse,
    _signup_accepted_response,
)
from .session_helpers import _persist_session
from .signup_helpers import _ensure_unique_tenant_slug
from shared.funnel_events import emit_funnel_event
from shared.pii import mask_email
from shared.rate_limit import limiter
from shared.supabase_client import get_supabase

router = APIRouter()
logger = structlog.get_logger("auth")


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
        "is_sysadmin": bool(new_user.is_sysadmin),
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
