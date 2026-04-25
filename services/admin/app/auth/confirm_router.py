"""Confirm (/confirm, require_reauth, /unlock) — extracted from auth_routes.py (Phase 1 sub-split 11/N).

Exposes:
  router           — APIRouter with /confirm, /unlock registered
  confirm_password — handler (re-exported from auth_routes for compat)
  require_reauth   — FastAPI dependency (re-exported from auth_routes for compat)
  unlock_account   — handler (re-exported from auth_routes for compat)
  ConfirmPasswordRequest — schema (re-exported from auth_routes for compat)
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_utils import create_access_token, decode_access_token, verify_password
from ..database import get_session
from ..dependencies import get_current_user, get_session_store, PermissionChecker
from ..session_store import RedisSessionStore
from ..sqlalchemy_models import MembershipModel, TenantModel, UserModel
from .elevation_helpers import _ELEVATION_JTI_KEY_PREFIX, _ELEVATION_TOKEN_TTL_SECONDS
from .lockout import (
    _check_account_lockout,
    _check_email_rate_limit,
    _clear_email_rate_limit,
    _clear_lockout,
    _record_failed_login_attempt,
    _record_lockout_attempt,
)
from shared.pii import mask_email
from shared.rate_limit import limiter

router = APIRouter()
logger = structlog.get_logger("auth")


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
        from ..models import TenantContext as _TC
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
