"""Change-password route — extracted from auth_routes.py (Phase 1 sub-split 9/N).

Exposes:
  router                — APIRouter with /change-password registered
  change_password       — handler (re-exported from auth_routes for compat)
  ChangePasswordRequest — request schema (re-exported from auth_routes for compat)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth_utils import decode_access_token, get_password_hash, verify_password
from ..database import get_session
from ..dependencies import get_current_user, get_session_store
from ..models import ChangePasswordResponse
from ..password_policy import validate_password, PasswordPolicyError
from ..session_store import RedisSessionStore
from ..sqlalchemy_models import UserModel
from .elevation_helpers import _revoke_all_elevation_tokens_for_user
from shared.rate_limit import limiter
from shared.supabase_client import get_supabase

router = APIRouter()
logger = structlog.get_logger("auth")


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
