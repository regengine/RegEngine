"""
Stripe webhook rate limiting — Redis-backed with in-memory fallback.

Reuses the same sliding-window pattern as app.sandbox.rate_limiting.

#2929: there are two independent budgets, and which one a request lands in
is decided by signature verification, not by the caller. See
``_check_stripe_webhook_rate_limit`` (unverified) and
``_check_verified_stripe_webhook_rate_limit`` (verified) below.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import time
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException

logger = logging.getLogger("stripe_billing.rate_limit")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# #2929: budget for traffic that has NOT been signature-verified — no
# ``Stripe-Signature`` header, a forged one, or an unparseable body. Keyed
# per source IP, which behind a shared reverse proxy degrades to per-proxy-
# peer. That degradation used to be the whole bug: the limiter ran before
# verification, so Stripe and every anonymous caller shared this one bucket
# and ~2 junk POSTs/second starved every genuine billing webhook. It is now
# harmless by construction — a verified delivery never consumes this budget,
# so exhausting it can only reject more junk.
_WEBHOOK_RATE_LIMIT = 100  # requests per window

# #2929: budget for deliveries Stripe actually signed. Sized well above any
# realistic renewal burst (the old shared 100/60s was routinely exceeded by
# renewal traffic alone), and reachable only by a caller holding
# ``STRIPE_WEBHOOK_SECRET``.
_VERIFIED_WEBHOOK_RATE_LIMIT = 5000  # requests per window

_WEBHOOK_WINDOW = 60  # seconds

# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------

_rate_buckets: Dict[str, list] = {}

# #2929: rejections by resolved bucket key, so throttling of real Stripe
# traffic is visible to operators instead of silent.
#
# The unverified key is a client IP, i.e. attacker-chosen cardinality, so the
# map is capped: past the cap further distinct keys aggregate under
# ``_REJECTION_OVERFLOW_KEY`` rather than growing the process without bound
# (the unbounded-``client_host``-label problem of #2858). The verified key is
# low-cardinality by construction and is therefore never the one displaced.
_MAX_TRACKED_REJECTION_KEYS = 1024
_REJECTION_OVERFLOW_KEY = "(other)"
_rate_limit_rejections: Dict[str, int] = {}


def rate_limit_rejection_counts() -> Dict[str, int]:
    """Snapshot of webhook rate-limit rejections keyed by bucket key (#2929)."""
    return dict(_rate_limit_rejections)


def _record_rejection(bucket_key: str) -> int:
    """Increment and return the rejection count for ``bucket_key`` (#2929)."""
    if bucket_key not in _rate_limit_rejections and len(_rate_limit_rejections) >= _MAX_TRACKED_REJECTION_KEYS:
        bucket_key = _REJECTION_OVERFLOW_KEY
    count = _rate_limit_rejections.get(bucket_key, 0) + 1
    _rate_limit_rejections[bucket_key] = count
    return count


def _resolve_limit(limit: Optional[int]) -> int:
    """Default an unspecified limit to the unverified budget."""
    return _WEBHOOK_RATE_LIMIT if limit is None else limit


def _check_in_memory(bucket_key: str, now: float, limit: Optional[int] = None) -> int:
    """In-memory sliding window. Returns remaining seconds if limited, else 0."""
    limit = _resolve_limit(limit)
    bucket = _rate_buckets.setdefault(bucket_key, [])
    bucket[:] = [t for t in bucket if now - t < _WEBHOOK_WINDOW]
    if len(bucket) >= limit:
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


def _check_redis(bucket_key: str, now: float, limit: Optional[int] = None) -> int:
    """Redis sorted-set sliding window. Returns remaining seconds if limited, else 0."""
    limit = _resolve_limit(limit)
    r = _get_redis()
    if r is None:
        return _check_in_memory(bucket_key, now, limit)

    key = f"stripe_webhook:rate:{bucket_key}"
    member = f"{now}:{uuid.uuid4().hex}"
    try:
        remaining = r.eval(
            _RATE_LIMIT_LUA,
            1,
            key,
            now,
            _WEBHOOK_WINDOW,
            limit,
            member,
        )
        return int(remaining)
    except Exception:
        logger.debug("Redis error in stripe webhook rate limit check, falling back to in-memory")
        return _check_in_memory(bucket_key, now, limit)


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
    raw = os.getenv("STRIPE_TRUSTED_PROXY_CIDRS", "").strip() or os.getenv("TRUSTED_PROXY_CIDRS", "").strip()
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
        forwarded = request.headers.get("X-Forwarded-For") or request.headers.get("x-forwarded-for")
        if forwarded:
            first_hop = forwarded.split(",")[0].strip()
            if first_hop and _looks_like_ip(first_hop):
                return first_hop

    return client_host or "unknown"


def _enforce(bucket_key: str, limit: int, *, signed: bool) -> None:
    """Consume one slot in ``bucket_key``; raise 429 when the budget is spent.

    #2929: every rejection increments the exported counter under the
    resolved bucket key and logs it at WARNING, including whether the
    request carried a ``Stripe-Signature`` — throttling of anything that
    claims to be Stripe must be visible, not silent.
    """
    now = datetime.now(timezone.utc).timestamp()
    retry_after = _check_redis(bucket_key, now, limit)
    if retry_after <= 0:
        return

    logger.warning(
        "stripe_webhook_rate_limit_exceeded bucket=%s signed=%s limit=%s rejections=%s",
        bucket_key,
        signed,
        limit,
        _record_rejection(bucket_key),
    )
    raise HTTPException(
        status_code=429,
        detail="Rate limit exceeded. Try again shortly.",
        headers={"Retry-After": str(retry_after)},
    )


def _has_signature_header(request) -> bool:
    """Whether the request claimed to be Stripe. Telemetry only (#2929).

    Feeds the ``signed=`` field on the rejection log so throttling of
    something claiming to be Stripe is distinguishable from anonymous junk.
    It is never a control decision — only ``construct_event`` decides that.
    Starlette's ``Headers`` is a ``Mapping``; anything else (a test double,
    a middleware wrapper) is reported as unsigned rather than probed.
    """
    headers = getattr(request, "headers", None)
    if not isinstance(headers, Mapping):
        return False
    value = headers.get("Stripe-Signature") or headers.get("stripe-signature")
    return isinstance(value, str) and bool(value.strip())


def _check_stripe_webhook_rate_limit(request) -> None:
    """Per-IP budget for webhook traffic that is NOT signature-verified.

    #2929: this used to be the *first* statement of both webhook routes,
    ahead of ``stripe.Webhook.construct_event``. Callers must now invoke it
    only once a request has been shown not to be a genuine Stripe delivery
    (missing/invalid signature, unparseable payload) — see
    ``webhooks._process_stripe_webhook``. Verified deliveries go to
    ``_check_verified_stripe_webhook_rate_limit`` and never touch this
    bucket, so junk traffic can no longer starve real billing webhooks even
    when every caller collapses onto one shared proxy-peer address.

    Raises HTTPException(429) with a Retry-After header if the limit is exceeded.
    """
    _enforce(_client_ip(request), _WEBHOOK_RATE_LIMIT, signed=_has_signature_header(request))


def _verified_bucket_key(event: Any) -> str:
    """Bucket key for a signature-verified delivery (#2929).

    Derived exclusively from the verified event envelope. Landing anything
    in this bucket requires an HMAC-SHA256 signature over the exact request
    body computed with ``STRIPE_WEBHOOK_SECRET``, so a caller without that
    secret can neither consume the budget nor influence which bucket a
    request falls into.

    No client-supplied header participates. In particular we deliberately do
    NOT use ``X-Forwarded-For`` here: this route is unauthenticated at the
    transport layer and the repo configures no trusted-proxy CIDRs in any
    deploy manifest, so that header is attacker-controlled — usable to
    forge a fresh bucket per request and evade the budget entirely.

    ``account`` is Stripe's Connect account id (absent on direct
    integrations, hence the ``platform`` default). It is a bucket label, not
    an authorization decision.
    """
    account = ""
    try:
        if isinstance(event, dict):
            account = str(event.get("account") or "")
        else:  # StripeObject / any attribute-style payload
            account = str(getattr(event, "account", "") or "")
    except Exception:  # pragma: no cover - defensive
        account = ""
    return f"verified:{account or 'platform'}"


def _check_verified_stripe_webhook_rate_limit(event: Any) -> None:
    """Budget for deliveries whose Stripe signature already verified (#2929).

    Kept as a backstop against a runaway sender (or our own retry storm);
    it is not a defense against anonymous callers, who cannot reach it.
    """
    _enforce(_verified_bucket_key(event), _VERIFIED_WEBHOOK_RATE_LIMIT, signed=True)
