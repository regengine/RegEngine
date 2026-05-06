"""Token-refresh route — extracted from auth_routes.py (Phase 1 sub-split 6/N).

Exposes:
  router          — APIRouter with /refresh registered; included by auth_routes.py
  refresh_session — the handler function (re-exported from auth_routes for compat)
  RefreshRequest  — request schema (re-exported from auth_routes for compat)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import AuditLogger
from ..auth_utils import (
    REFRESH_TOKEN_EXPIRE_DAYS,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_token,
)
from ..database import get_session
from ..dependencies import get_session_store
from ..session_store import RedisSessionStore
from ..sqlalchemy_models import MembershipModel, TenantModel, UserModel
from .lockout import _maybe_await
from .schemas import TokenResponse
from shared.rate_limit import limiter

router = APIRouter()
logger = structlog.get_logger("auth")


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
        "is_sysadmin": bool(user.is_sysadmin),
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
        available_tenants=[]  # Don't need full list on refresh
    )
