"""
Stripe webhook rate limiting — Redis-backed with in-memory fallback.

Reuses the same sliding-window pattern as app.sandbox.rate_limiting.
Limits: 100 requests/minute per source IP.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict

from fastapi import HTTPException

logger = logging.getLogger("stripe_billing.rate_limit")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_WEBHOOK_RATE_LIMIT = 100  # requests per window
_WEBHOOK_WINDOW = 60  # seconds

# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------

_rate_buckets: Dict[str, list] = {}


def _check_in_memory(client_ip: str, now: float) -> int:
    """In-memory sliding window. Returns remaining seconds if limited, else 0."""
    bucket = _rate_buckets.setdefault(client_ip, [])
    bucket[:] = [t for t in bucket if now - t < _WEBHOOK_WINDOW]
    if len(bucket) >= _WEBHOOK_RATE_LIMIT:
        oldest = bucket[0]
        return int(_WEBHOOK_WINDOW - (now - oldest)) or 1
    bucket.append(now)
    return 0


# ---------------------------------------------------------------------------
# Redis
# ---------------------------------------------------------------------------

_redis_client = None
_redis_failed = False


def _get_redis():
    global _redis_client, _redis_failed
    if _redis_failed:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        from app.config import get_settings
        import redis as redis_lib

        settings = get_settings()
        _redis_client = redis_lib.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        return _redis_client
    except Exception:
        logger.debug(
            "Redis unavailable for stripe webhook rate limiting, using in-memory fallback"
        )
        _redis_failed = True
        return None


def _check_redis(client_ip: str, now: float) -> int:
    """Redis sorted-set sliding window. Returns remaining seconds if limited, else 0."""
    r = _get_redis()
    if r is None:
        return _check_in_memory(client_ip, now)

    key = f"stripe_webhook:rate:{client_ip}"
    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, now - _WEBHOOK_WINDOW)
        pipe.zcard(key)
        pipe.execute()

        count = r.zcard(key)
        if count >= _WEBHOOK_RATE_LIMIT:
            oldest = r.zrange(key, 0, 0, withscores=True)
            if oldest:
                remaining = int(_WEBHOOK_WINDOW - (now - oldest[0][1]))
                return max(remaining, 1)
            return 1

        r.zadd(key, {f"{now}": now})
        r.expire(key, _WEBHOOK_WINDOW + 1)
        return 0
    except Exception:
        logger.debug("Redis error in stripe webhook rate limit check, falling back to in-memory")
        return _check_in_memory(client_ip, now)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _check_stripe_webhook_rate_limit(request) -> None:
    """Check per-IP rate limit for Stripe webhook requests.

    Raises HTTPException(429) with a Retry-After header if the limit is exceeded.
    """
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    now = datetime.now(timezone.utc).timestamp()
    retry_after = _check_redis(client_ip, now)

    if retry_after > 0:
        logger.warning("stripe_webhook_rate_limit_exceeded client_ip=%s", client_ip)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
