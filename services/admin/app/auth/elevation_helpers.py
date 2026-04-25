"""Elevation-token constants and cross-handler helpers.

Extracted from ``auth_routes.py`` so sessions_router, change_password, and
reset_password can all import ``_revoke_all_elevation_tokens_for_user``
without a circular dependency on auth_routes.

``auth_routes.py`` re-imports and re-exports these names so existing
callers/tests that reference ``ar._revoke_all_elevation_tokens_for_user``
continue to work unchanged.
"""
from __future__ import annotations

from uuid import UUID

import structlog

from ..session_store import RedisSessionStore

logger = structlog.get_logger("auth")

_ELEVATION_JTI_KEY_PREFIX = "elevation_jti:"
_ELEVATION_TOKEN_TTL_SECONDS = 300  # 5 minutes — matches token exp_delta


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
