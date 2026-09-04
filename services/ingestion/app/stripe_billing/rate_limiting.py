"""
Stripe endpoint rate limiting.

Webhook delivery retains its Redis-backed sliding window with local fallback.
Public checkout uses the shared brute-force primitive and requires Redis in
production/cloud modes so replicas cannot multiply the checkout abuse budget.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Dict

from fastapi import HTTPException, Request
from shared.env import CLOUD_ENV_VARS, get_environment
from shared.proxy_ip_attestation import verified_proxy_client_ip
from shared.rate_limit import BruteForceLimiter

logger = logging.getLogger("stripe_billing.rate_limit")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_WEBHOOK_RATE_LIMIT = 100  # requests per window
_WEBHOOK_WINDOW = 60  # seconds
_CHECKOUT_RATE_LIMIT = 10  # requests per source IP per window
_CHECKOUT_WINDOW = 60  # seconds

_checkout_limiter: BruteForceLimiter | None = None
_checkout_limiter_lock = threading.Lock()

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
# #2699: retry Redis after a cooldown instead of never for the process
# lifetime (the old sticky flag), and log the fallback at WARNING so it
# is visible at prod log levels.
_REDIS_RETRY_COOLDOWN_SECONDS = 30.0
_redis_retry_at = 0.0

# Atomic sliding-window check, evaluated server-side so the trim → count →
# admit/reject → add sequence cannot interleave across concurrent requests
# (the previous non-atomic zcard-then-zadd allowed burst overshoot above the
# limit). A unique member per request avoids same-timestamp collisions that
# would otherwise undercount. Returns 0 if admitted, else Retry-After seconds.
_RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local remaining = 1
  if oldest[2] then
    remaining = math.ceil(window - (now - tonumber(oldest[2])))
    if remaining < 1 then remaining = 1 end
  end
  return remaining
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 1)
return 0
"""


def _get_redis():
    global _redis_client, _redis_failed, _redis_retry_at
    if _redis_failed:
        # #2699: retry after the cooldown rather than never.
        if time.time() < _redis_retry_at:
            return None
        _redis_failed = False
    if _redis_client is not None:
        return _redis_client
    try:
        import redis as redis_lib
        from app.config import get_settings

        settings = get_settings()
        _redis_client = redis_lib.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        _redis_client.ping()
        return _redis_client
    except Exception as exc:
        logger.warning(
            "Redis unavailable for stripe webhook rate limiting, using in-memory fallback (retry in %ss): %s",
            _REDIS_RETRY_COOLDOWN_SECONDS,
            exc,
        )
        _redis_failed = True
        _redis_retry_at = time.time() + _REDIS_RETRY_COOLDOWN_SECONDS
        _redis_client = None
        return None


def _check_redis(client_ip: str, now: float) -> int:
    """Redis sorted-set sliding window. Returns remaining seconds if limited, else 0."""
    r = _get_redis()
    if r is None:
        return _check_in_memory(client_ip, now)

    key = f"stripe_webhook:rate:{client_ip}"
    member = f"{now}:{uuid.uuid4().hex}"
    try:
        remaining = r.eval(
            _RATE_LIMIT_LUA,
            1,
            key,
            now,
            _WEBHOOK_WINDOW,
            _WEBHOOK_RATE_LIMIT,
            member,
        )
        return int(remaining)
    except Exception:
        logger.debug("Redis error in stripe webhook rate limit check, falling back to in-memory")
        return _check_in_memory(client_ip, now)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _client_ip(request) -> str:
    """Resolve an authenticated BFF IP, otherwise use the socket peer."""
    client_host = request.client.host if request.client else None
    authenticated_client_ip = verified_proxy_client_ip(request)
    if authenticated_client_ip:
        return authenticated_client_ip
    return client_host or "unknown"


def _checkout_requires_shared_backend() -> bool:
    """Require Redis anywhere except an explicit, non-cloud local/test run."""
    cloud_deployment = any(os.getenv(name) for name in CLOUD_ENV_VARS)
    environment = get_environment()
    return cloud_deployment or environment not in {"development", "local", "test"}


def _get_checkout_limiter() -> BruteForceLimiter:
    global _checkout_limiter
    if _checkout_limiter is None:
        with _checkout_limiter_lock:
            if _checkout_limiter is None:
                _checkout_limiter = BruteForceLimiter(
                    namespace="stripe_checkout_requests",
                    max_failures=_CHECKOUT_RATE_LIMIT,
                    window_seconds=_CHECKOUT_WINDOW,
                    require_shared_backend=_checkout_requires_shared_backend(),
                )
    return _checkout_limiter


def _check_stripe_checkout_rate_limit(request: Request) -> None:
    """Consume the per-IP public checkout budget before Stripe is called."""
    client_ip = _client_ip(request)
    limiter = _get_checkout_limiter()
    # The Redis INCR inside record_failure is atomic across replicas. Checking
    # first and incrementing second would permit concurrent overshoot.
    current_count = limiter.record_failure(client_ip)
    if current_count > limiter.max_failures:
        logger.warning("stripe_checkout_rate_limit_exceeded client_ip=%s", client_ip)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again shortly.",
            headers={"Retry-After": str(_CHECKOUT_WINDOW)},
        )

    # BruteForceLimiter is a generic fixed-window shared counter. Checkout
    # consumes one unit for every request, not only failures, because Stripe
    # session creation itself is the resource being protected.


def _check_stripe_webhook_rate_limit(request) -> None:
    """Check per-IP rate limit for Stripe webhook requests.

    Raises HTTPException(429) with a Retry-After header if the limit is exceeded.
    """
    client_ip = _client_ip(request)
    now = datetime.now(timezone.utc).timestamp()
    retry_after = _check_redis(client_ip, now)

    if retry_after > 0:
        logger.warning("stripe_webhook_rate_limit_exceeded client_ip=%s", client_ip)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )
