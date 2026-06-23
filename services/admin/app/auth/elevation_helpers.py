"""Elevation-token constants and session helper utilities."""

from __future__ import annotations

from uuid import UUID

import structlog

from ..session_store import RedisSessionStore

logger = structlog.get_logger("auth")

_ELEVATION_JTI_KEY_PREFIX = "elevation_jti:"
_ELEVATION_TOKEN_TTL_SECONDS = 300  # 5 minutes, matches elevation token lifetime.


async def _revoke_all_elevation_tokens_for_user(session_store: RedisSessionStore, user_id: UUID) -> int:
    """Scan the elevation-jti keyspace and delete entries belonging to this user.

    Called from broad session invalidation paths so a previously minted
    elevation token cannot outlive an account-security revocation.
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
