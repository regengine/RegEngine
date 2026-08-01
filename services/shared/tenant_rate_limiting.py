import os
import time
import uuid
from collections import defaultdict
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import redis
import structlog
from fastapi import HTTPException, Request
from prometheus_client import REGISTRY, Counter
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = structlog.get_logger("shared.tenant_rate_limiting")

# ---------------------------------------------------------------------------
# #2699: operator-controllable behavior when the shared Redis backend is
# uncertain (error / unreachable). See docs/runbooks/RATE_LIMIT_DEGRADATION.md.
#
#   degrade (default) — per-process in-memory fallback keeps limiting, with a
#     tightened per-process budget (limit // RATE_LIMIT_FALLBACK_DIVISOR,
#     defaulting to WEB_CONCURRENCY), a structured warning + metric on every
#     fallback ACTIVATION (healthy→degraded transition, not per request), and
#     an X-RateLimit-Degraded response header so operators can see it.
#   closed — Redis uncertainty returns 503 + Retry-After (the
#     supplier_portal.py #2700 pattern), trading availability for a hard
#     abuse-control guarantee.
#
# A PRESENT but unrecognized value fails closed (#2662 shape): the operator
# intended a mode, and silently degrading on a typo weakens the control.
# The billing/entitlement gate (subscription_gate.py) already fails closed
# with its own 402/503 contract and does NOT read this knob.
# ---------------------------------------------------------------------------

RATE_LIMIT_FAIL_MODE_ENV = "RATE_LIMIT_FAIL_MODE"
_VALID_FAIL_MODES = {"degrade", "closed"}
_reported_invalid_fail_modes: set[str] = set()


def rate_limit_fail_mode() -> str:
    """Resolve the fail mode: ``degrade`` (default) or ``closed``."""
    raw = os.getenv(RATE_LIMIT_FAIL_MODE_ENV, "degrade").strip().lower()
    if not raw:
        return "degrade"
    if raw not in _VALID_FAIL_MODES:
        if raw not in _reported_invalid_fail_modes:
            _reported_invalid_fail_modes.add(raw)
            logger.error(
                "rate_limit_fail_mode_invalid",
                value=raw,
                valid=sorted(_VALID_FAIL_MODES),
                effective="closed",
            )
        return "closed"
    return raw


def _fallback_divisor() -> int:
    """Per-process budget divisor for the in-memory fallback.

    Effective fleet budget under degrade ≈ limit × workers × replicas; the
    divisor claws that back toward the intended budget. Defaults to
    WEB_CONCURRENCY (gunicorn workers per replica) when set, else 1.
    Override with RATE_LIMIT_FALLBACK_DIVISOR (e.g. workers × replicas).
    """
    raw = os.getenv("RATE_LIMIT_FALLBACK_DIVISOR") or os.getenv("WEB_CONCURRENCY") or "1"
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


class RateLimitBackendUnavailable(HTTPException):
    """Raised in ``closed`` mode when the rate-limit backend is uncertain."""

    def __init__(self, detail: str = "Rate-limit backend unavailable — request not accepted. Please retry shortly."):
        super().__init__(status_code=503, detail=detail, headers={"Retry-After": "30"})


def _safe_counter(name: str, description: str, labelnames: list[str]) -> Counter:
    """Return an existing Prometheus Counter when this module is re-imported."""
    try:
        return Counter(name, description, labelnames)
    except ValueError:
        collector = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if collector is None and name.endswith("_total"):
            collector = REGISTRY._names_to_collectors.get(name[:-6])  # type: ignore[attr-defined]
        if collector is not None:
            return collector  # type: ignore[return-value]
        return Counter(name, description, labelnames, registry=None)


tenant_rate_limit_hits_total = _safe_counter(
    "tenant_rate_limit_hits_total",
    "Rate limit hits per tenant",
    ["tenant_id", "status"],
)

# #2699: incremented once per fallback ACTIVATION (healthy→degraded
# transition), not per request. Alert on any increase in production.
rate_limit_fallback_activations_total = _safe_counter(
    "rate_limit_fallback_activations_total",
    "Rate-limiter transitions from the shared Redis backend to the per-process in-memory fallback",
    ["surface"],
)


def record_rate_limit(tenant_id: str, allowed: bool):
    status = "allowed" if allowed else "blocked"
    tenant_rate_limit_hits_total.labels(tenant_id=tenant_id, status=status).inc()


def rate_limit_reset_epoch(window: int = 60, now: float | None = None) -> int:
    """Return a Unix timestamp for the next rate-limit window boundary."""
    safe_window = max(1, int(window))
    return int((time.time() if now is None else now) + safe_window)


def _redact_connection_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or "unknown"
        port = f":{parsed.port}" if parsed.port else ""
        username = parsed.username or ""

        auth = ""
        if username:
            auth = f"{username}:***@"

        return urlunsplit((parsed.scheme, f"{auth}{host}{port}", parsed.path, "", ""))
    except (ValueError, AttributeError):
        logger.debug("URL sanitization failed", exc_info=True)
        return "<redacted>"


class _InMemoryBucket:
    def __init__(self):
        self._hits = defaultdict(list)

    def is_allowed(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window
        self._hits[key] = [hit for hit in self._hits[key] if hit > cutoff]
        if len(self._hits[key]) >= limit:
            return False, 0
        self._hits[key].append(now)
        return True, limit - len(self._hits[key])


class _RedisBucket:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self._fallback_bucket = _InMemoryBucket()
        # #2699: True while the last Redis call failed — drives the
        # per-activation warning/metric and the X-RateLimit-Degraded header.
        self.degraded = False

    def is_allowed(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        try:
            pipe = self.redis.pipeline()
            now = time.time()
            cutoff = now - window
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            results = pipe.execute()
            current_count = results[1]

            if self.degraded:
                # Recovery: back on the shared backend.
                self.degraded = False
                logger.info("rate_limit_backend_recovered", backend="redis")

            if current_count >= limit:
                return False, 0

            pipe.zadd(key, {str(uuid.uuid4()): now})
            pipe.expire(key, window)
            pipe.execute()
            return True, limit - (current_count + 1)
        except redis.RedisError as exc:
            mode = rate_limit_fail_mode()
            if not self.degraded:
                # Activation (healthy→degraded transition): warn + metric
                # once, not per request (#2699).
                self.degraded = True
                logger.warning(
                    "rate_limit_backend_unavailable",
                    backend="redis",
                    error=str(exc),
                    fail_mode=mode,
                    fallback="in_memory" if mode == "degrade" else "closed_503",
                    fallback_divisor=_fallback_divisor(),
                )
                rate_limit_fallback_activations_total.labels(surface="tenant").inc()
            # Alert via Sentry (deduplicated)
            from shared.redis_health import report_redis_fallback

            report_redis_fallback("rate_limiter", str(exc))
            if mode == "closed":
                raise RateLimitBackendUnavailable() from exc
            # degrade: per-process fallback with a tightened budget —
            # limit // divisor per process ≈ the intended fleet budget.
            fallback_limit = max(1, limit // _fallback_divisor())
            return self._fallback_bucket.is_allowed(key, fallback_limit, window)


_explicit_redis_url = os.getenv("RATE_LIMIT_STORAGE_URI") or os.getenv("REDIS_URL")
if _explicit_redis_url:
    redis_url = _explicit_redis_url
    try:
        _bucket = _RedisBucket(redis_url)
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning(
            "rate_limit_backend_init_failed",
            backend="redis",
            redis_url=_redact_connection_url(redis_url),
            error=str(exc),
            fallback="in_memory",
        )
        _bucket = _InMemoryBucket()
else:
    logger.warning(
        "rate_limit_redis_not_configured",
        message=(
            "REDIS_URL not set — rate limiter is per-process only, "
            "not suitable for multi-replica deployments. "
            "Set REDIS_URL or RATE_LIMIT_STORAGE_URI to enable a shared Redis backend."
        ),
    )
    _bucket = _InMemoryBucket()


def rate_limiter_degraded() -> bool:
    """True while the shared Redis backend is failing and the per-process
    fallback is in force (#2699). Exposed for health/readiness payloads;
    always False when no Redis was configured (that state is reported by
    the boot-time ``rate_limit_redis_not_configured`` warning instead)."""
    return bool(getattr(_bucket, "degraded", False))


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, default_rpm: int = 100, tenant_overrides: Optional[dict] = None):
        super().__init__(app)
        self.default_rpm = int(os.getenv("TENANT_RATE_LIMIT_RPM", str(default_rpm)))
        self.tenant_overrides = tenant_overrides or {}
        self.exempt_paths = {"/health", "/ready", "/readiness", "/metrics", "/"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID", "anonymous")
        if tenant_id != "anonymous":
            key = f"tenant:{tenant_id}"
        else:
            key = f"ip:{request.client.host if request.client else 'unknown'}"

        limit = self.tenant_overrides.get(tenant_id, self.default_rpm)
        window = 60
        reset_epoch = rate_limit_reset_epoch(window)
        try:
            allowed, remaining = _bucket.is_allowed(key, limit, window)
        except RateLimitBackendUnavailable as exc:
            # #2699 closed mode: Redis uncertainty → 503 + Retry-After.
            # (HTTPException raised inside BaseHTTPMiddleware bypasses
            # FastAPI's handlers, so convert to a response here.)
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": "rate_limit_backend_unavailable", "detail": exc.detail},
                headers=dict(exc.headers or {}),
            )
        record_rate_limit(tenant_id, allowed)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": f"Limit of {limit}/min exceeded for {tenant_id}",
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_epoch),
                    "X-RateLimit-Tenant": tenant_id,
                    "X-RateLimit-Scope": "global",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(getattr(request.state, "rate_limit_limit", limit))
        response.headers["X-RateLimit-Remaining"] = str(getattr(request.state, "rate_limit_remaining", remaining))
        response.headers["X-RateLimit-Reset"] = str(getattr(request.state, "rate_limit_reset", reset_epoch))
        response.headers["X-RateLimit-Tenant"] = str(getattr(request.state, "rate_limit_tenant", tenant_id))
        response.headers["X-RateLimit-Scope"] = str(getattr(request.state, "rate_limit_scope", "global"))
        if rate_limiter_degraded():
            # #2699: visible marker that the per-process fallback is in
            # force (see docs/runbooks/RATE_LIMIT_DEGRADATION.md).
            response.headers["X-RateLimit-Degraded"] = "1"
        return response


def consume_tenant_rate_limit(
    *,
    tenant_id: str,
    bucket_suffix: str,
    limit: int,
    window: int = 60,
) -> tuple[bool, int]:
    """
    Consume one request from a tenant-scoped rate-limit bucket.

    Returns ``(allowed, remaining)``.
    """
    safe_tenant = tenant_id or "anonymous"
    safe_suffix = bucket_suffix or "default"
    safe_limit = max(1, int(limit))
    safe_window = max(1, int(window))
    key = f"tenant:{safe_tenant}:{safe_suffix}"

    allowed, remaining = _bucket.is_allowed(key, safe_limit, safe_window)
    record_rate_limit(safe_tenant, allowed)
    return allowed, remaining
