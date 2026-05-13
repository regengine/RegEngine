"""
Stripe webhook rate limiting — Redis-backed with in-memory fallback.

Reuses the same sliding-window pattern as app.sandbox.rate_limiting.
Limits: 100 requests/minute per source IP.
"""

from __future__ import annotations

import ipaddress
import logging
import os
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


def _trusted_proxy_cidrs() -> list:
    """Parse trusted-proxy CIDRs from env.

    Mirrors ``services/admin/app/audit_middleware.py``: ``X-Forwarded-For``
    is honored ONLY when the immediate connection peer falls inside one
    of these CIDRs. Without that gate, an attacker can mint a fresh
    per-IP rate-limit bucket on every request by rotating the header,
    fully bypassing the limiter.

    Two env vars accepted (in order): ``STRIPE_TRUSTED_PROXY_CIDRS``
    (specific) wins over ``TRUSTED_PROXY_CIDRS`` (shared). Unset = XFF
    ignored; the raw socket address is used.
    """
    raw = (
        os.getenv("STRIPE_TRUSTED_PROXY_CIDRS", "").strip()
        or os.getenv("TRUSTED_PROXY_CIDRS", "").strip()
    )
    if not raw:
        return []
    cidrs = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            cidrs.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("stripe_trusted_proxy_cidr_invalid value=%s", item)
    return cidrs


def _is_trusted_proxy(client_host: str | None) -> bool:
    if not client_host:
        return False
    try:
        client_ip = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    for cidr in _trusted_proxy_cidrs():
        if client_ip in cidr:
            return True
    return False


def _looks_like_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _client_ip(request) -> str:
    """Resolve the real client IP.

    Honors ``X-Forwarded-For`` only when the peer is a trusted proxy
    (#XFF-bypass-2026-05-12). Otherwise falls back to
    ``request.client.host``.
    """
    client_host = request.client.host if request.client else None

    if _is_trusted_proxy(client_host):
        forwarded = request.headers.get("X-Forwarded-For") or request.headers.get(
            "x-forwarded-for"
        )
        if forwarded:
            first_hop = forwarded.split(",")[0].strip()
            if first_hop and _looks_like_ip(first_hop):
                return first_hop

    return client_host or "unknown"


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
