"""Login route — extracted from auth_routes.py (Phase 1 sub-split 4/N).

Exposes:
  router   — APIRouter with /login registered; included by auth_routes.py
  login    — the handler function (re-exported from auth_routes for compat)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import AuditLogger
from ..auth_utils import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    hash_token,
    verify_login,
)
from ..database import get_session
from ..dependencies import get_session_store
from ..session_store import RedisSessionStore, SessionData
from ..sqlalchemy_models import MembershipModel, TenantModel, UserModel
from .lockout import (
    _check_account_lockout,
    _check_email_rate_limit,
    _clear_email_rate_limit,
    _clear_lockout,
    _record_failed_login_attempt,
    _record_lockout_attempt,
)
from .schemas import LoginRequest, TokenResponse
from .session_helpers import _persist_session
from shared.rate_limit import limiter

router = APIRouter()
logger = structlog.get_logger("auth")


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_session),
    session_store: RedisSessionStore = Depends(get_session_store),
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
    stmt_mem = (
        select(MembershipModel, TenantModel)
        .join(TenantModel, MembershipModel.tenant_id == TenantModel.id)
        .where(MembershipModel.user_id == user.id)
    )
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
        ip_address=request.client.host if request.client else "0.0.0.0",
    )

    # Persist session — retries once, then fails with 503 so the user
    # gets a clean error instead of a zombie session that can't refresh.
    await _persist_session(
        session_store,
        session_data,
        context="login",
        user_id=user.id,
    )

    # 4. Create Access Token
    access_token_data = {
        "sub": str(user.id),
        "email": user.email,
        "tenant_id": str(active_tenant_id) if active_tenant_id else None,
        "tid": str(active_tenant_id) if active_tenant_id else None,
        "tenant_status": active_tenant_status,
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
        available_tenants=available_tenants,
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
