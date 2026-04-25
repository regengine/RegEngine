"""Session management routes — extracted from auth_routes.py (Phase 1 sub-split 7/N).

Exposes:
  router            — APIRouter with /sessions, /sessions/{id}/revoke, /logout-all
  list_sessions     — re-exported from auth_routes for compat
  revoke_session    — re-exported from auth_routes for compat
  revoke_all_sessions — re-exported from auth_routes for compat
"""
from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_session
from ..dependencies import get_current_user, get_session_store
from ..models import RevokeAllSessionsResponse, SessionListResponse, SessionRevokeResponse
from ..session_store import RedisSessionStore
from ..sqlalchemy_models import UserModel
from .elevation_helpers import _revoke_all_elevation_tokens_for_user
from shared.pagination import PaginationParams

router = APIRouter()
logger = structlog.get_logger("auth")


@router.get("/sessions", response_model=SessionListResponse, dependencies=[Depends(get_current_user)])
async def list_sessions(
    pagination: PaginationParams = Depends(),
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store),
):
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
    session_store: RedisSessionStore = Depends(get_session_store),
):
    session = await session_store.get_session(session_id)

    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

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
