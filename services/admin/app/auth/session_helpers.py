"""Session-persistence helpers shared across login, signup, and refresh.

Extracted from ``auth_routes.py`` (Phase 1 sub-split 2/N). Sole
responsibility is ``_persist_session``: write a ``SessionData`` row to
Redis with one retry, or raise 503 so the caller returns a clean error
instead of leaving the user with a zombie session that can't refresh.

Lives in its own module so both the login and signup handlers (still in
``auth_routes.py`` for now) can import it without circular-import risk
when the handler extractions land in subsequent sprints.

``auth_routes.py`` re-exports ``_persist_session`` so existing
``ar._persist_session(...)`` calls from ``test_auth_routes_1333.py``
continue to work unchanged.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from uuid import UUID

import structlog
from fastapi import HTTPException, status

from ..session_store import RedisSessionStore, SessionData

logger = structlog.get_logger("auth.session_helpers")


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
