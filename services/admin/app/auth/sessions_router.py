"""Session management routes — extracted from auth_routes.py (Phase 1 sub-split 7/N).

Exposes:
  router            — APIRouter with /sessions, /sessions/{id}/revoke, /logout, /logout-all, /session/logout
  list_sessions     — re-exported from auth_routes for compat
  revoke_session    — re-exported from auth_routes for compat
  logout            — re-exported from auth_routes for compat
  revoke_all_sessions — re-exported from auth_routes for compat
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from shared.pagination import PaginationParams
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..auth_utils import decode_access_token, revoke_token
from ..database import get_session
from ..dependencies import get_current_user, get_session_store
from ..models import RevokeAllSessionsResponse, SessionListResponse, SessionRevokeResponse
from ..session_store import RedisSessionStore
from ..sqlalchemy_models import SessionModel, UserModel
from .elevation_helpers import _revoke_all_elevation_tokens_for_user
from .session_auth import AUTH_SESSION_COOKIE, ActiveSessionContext, get_current_active_session_context

router = APIRouter()
logger = structlog.get_logger("auth")


def _bearer_token_from_request(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth_header[7:]


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


@router.post(
    "/sessions/{session_id}/revoke", response_model=SessionRevokeResponse, dependencies=[Depends(get_current_user)]
)
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


@router.post("/logout")
async def logout(
    request: Request,
    current_user: UserModel = Depends(get_current_user),
    session_store: RedisSessionStore = Depends(get_session_store),
):
    """Logout the current bearer-token session.

    Multiple active sessions are allowed; this endpoint only revokes the
    presented access token and, for session-bound local JWTs, its Redis
    session. Legacy local tokens without sid/session_id still get their jti
    revoked so replay of the bearer token fails.
    """
    token = _bearer_token_from_request(request)
    payload = decode_access_token(token)

    jti = payload.get("jti")
    if jti:
        await revoke_token(str(jti))

    sid_raw = payload.get("sid") or payload.get("session_id")
    session_revoked = False
    if sid_raw:
        try:
            session_id = UUID(str(sid_raw))
        except (TypeError, ValueError):
            session_id = None
        if session_id is not None:
            session = await session_store.get_session(session_id)
            if session and session.user_id == current_user.id:
                session_revoked = await session_store.revoke_session(session_id)

    logger.info(
        "logout_success",
        user_id=str(current_user.id),
        jti=str(jti) if jti else None,
        session_id=str(sid_raw) if sid_raw else None,
        session_revoked=session_revoked,
    )

    return {"status": "success"}


@router.post("/session/logout")
async def logout_browser_session(
    response: Response,
    context: ActiveSessionContext = Depends(get_current_active_session_context),
    db: Session = Depends(get_session),
):
    """Logout the opaque browser-cookie session (passwordless auth).

    The bearer-token /logout above cannot revoke these: passwordless sessions
    authenticate from the __Host-regengine_session cookie against the sessions
    table and carry no JWT. Mark the presented session row revoked so
    get_current_active_session_context rejects the cookie immediately instead
    of leaving the row alive until its natural expiry.
    """
    revoked = db.execute(
        update(SessionModel)
        .where(
            SessionModel.id == context.session.id,
            SessionModel.is_revoked.is_(False),
        )
        .values(is_revoked=True, revoked_at=datetime.now(timezone.utc))
    ).rowcount
    db.commit()

    # Mirror the set_cookie attributes from challenges_router — a __Host-
    # prefixed cookie only clears when Secure and Path=/ match.
    response.delete_cookie(
        AUTH_SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )

    logger.info(
        "browser_session_logout",
        user_id=str(context.user.id),
        session_id=str(context.session.id),
        session_revoked=bool(revoked),
    )

    return {"status": "success"}


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
    logout-all and account-security invalidation flows.
    """
    # 1. Revoke Redis session rows (future /refresh attempts will 401).
    count = await session_store.revoke_all_user_sessions(current_user.id)

    # 1b. Revoke opaque browser-session rows too. Passwordless sessions
    # authenticate from the __Host-regengine_session cookie against the
    # sessions table — they carry no token_version claim, so the bump in
    # step 2 alone would leave them alive.
    cookie_sessions_revoked = db.execute(
        update(SessionModel)
        .where(
            SessionModel.user_id == current_user.id,
            SessionModel.is_revoked.is_(False),
        )
        .values(is_revoked=True, revoked_at=datetime.now(timezone.utc))
    ).rowcount

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
    elevation_revoked = await _revoke_all_elevation_tokens_for_user(session_store, current_user.id)

    logger.info(
        "all_sessions_revoked",
        user_id=str(current_user.id),
        count=count,
        cookie_sessions_revoked=cookie_sessions_revoked,
        elevation_tokens_revoked=elevation_revoked,
        new_token_version=new_version,
    )

    return {"status": "success", "revoked_count": count}
