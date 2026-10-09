"""Elevation-token constants and session helper utilities."""

from __future__ import annotations

from uuid import UUID

from ..session_store import RedisSessionStore

_ELEVATION_JTI_KEY_PREFIX = "elevation_jti:"
_ELEVATION_TOKEN_TTL_SECONDS = 300  # 5 minutes, matches elevation token lifetime.

# A single SCAN pass can miss keys minted concurrently with the cleanup, so
# repeat full passes until one revokes nothing. Bounded so a steady stream of
# new tokens cannot spin this forever; each pass still deletes atomically.
_MAX_ELEVATION_CLEANUP_PASSES = 3


async def _revoke_all_elevation_tokens_for_user(session_store: RedisSessionStore, user_id: UUID) -> int:
    """Scan the elevation-jti keyspace and delete entries belonging to this user.

    Called from broad session invalidation paths so a previously minted
    elevation token cannot outlive an account-security revocation. Deletions
    within a pass go out in one pipeline, and passes repeat until a full scan
    finds nothing left to revoke, so tokens minted mid-cleanup converge away
    instead of surviving logout-everywhere.
    """
    client = await session_store._get_client()
    owner = str(user_id)
    pattern = f"{_ELEVATION_JTI_KEY_PREFIX}*"
    revoked = 0
    for _ in range(_MAX_ELEVATION_CLEANUP_PASSES):
        revoked_this_pass = 0
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=200)
            matched = []
            for key in keys:
                val = await client.get(key)
                if val == owner:
                    matched.append(key)
            if matched:
                async with client.pipeline(transaction=True) as pipe:
                    await pipe.delete(*matched)
                    await pipe.execute()
                revoked_this_pass += len(matched)
            if cursor == 0:
                break
        revoked += revoked_this_pass
        if revoked_this_pass == 0:
            break
    return revoked
