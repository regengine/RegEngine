from collections import defaultdict
import os
import time
from typing import Optional
from urllib.parse import urlsplit, urlunsplit
import uuid

from fastapi import Request
from prometheus_client import Counter
import redis
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = structlog.get_logger("shared.tenant_rate_limiting")

tenant_rate_limit_hits_total = Counter(
    "tenant_rate_limit_hits_total",
    "Rate limit hits per tenant",
    ["tenant_id", "status"],
)


def record_rate_limit(tenant_id: str, allowed: bool):
    status = "allowed" if allowed else "blocked"
    tenant_rate_limit_hits_total.labels(tenant_id=tenant_id, status=status).inc()


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
    except Exception:
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
        self._fallback_logged = False

    def is_allowed(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        try:
            pipe = self.redis.pipeline()
            now = time.time()
            cutoff = now - window
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            results = pipe.execute()
            current_count = results[1]

            if current_count >= limit:
                return False, 0

            pipe.zadd(key, {str(uuid.uuid4()): now})
            pipe.expire(key, window)
            pipe.execute()
            return True, limit - (current_count + 1)
        except redis.RedisError as exc:
            if not self._fallback_logged:
                logger.warning(
                    "rate_limit_backend_unavailable",
                    backend="redis",
                    error=str(exc),
                    fallback="in_memory",
                )
                self._fallback_logged = True
            return self._fallback_bucket.is_allowed(key, limit, window)


redis_url = os.getenv("RATE_LIMIT_STORAGE_URI") or os.getenv("REDIS_URL", "redis://localhost:6379/2")
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


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, default_rpm: int = 100, tenant_overrides: Optional[dict] = None):
        super().__init__(app)
        self.default_rpm = int(os.getenv("TENANT_RATE_LIMIT_RPM", str(default_rpm)))
        self.tenant_overrides = tenant_overrides or {}
        self.exempt_paths = {"/health", "/ready", "/metrics", "/"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-ID", "anonymous")
        if tenant_id != "anonymous":
            key = f"tenant:{tenant_id}"
        else:
            key = f"ip:{request.client.host if request.client else 'unknown'}"

        limit = self.tenant_overrides.get(tenant_id, self.default_rpm)
        allowed, remaining = _bucket.is_allowed(key, limit)
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
                    "X-RateLimit-Tenant": tenant_id,
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Tenant"] = tenant_id
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
