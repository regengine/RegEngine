from prometheus_client import Counter
from fastapi import Request
import os
import time
import structlog
import redis
import uuid
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from collections import defaultdict

logger = structlog.get_logger("shared.tenant_rate_limiting")

tenant_rate_limit_hits_total = Counter(
    "tenant_rate_limit_hits_total",
    "Rate limit hits per tenant",
    ["tenant_id", "status"]  # status = "allowed" or "blocked"
)

def record_rate_limit(tenant_id: str, allowed: bool):
    status = "allowed" if allowed else "blocked"
    tenant_rate_limit_hits_total.labels(tenant_id=tenant_id, status=status).inc()

class _RedisBucket:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    def is_allowed(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
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

# Initialize bucket
redis_url = os.getenv("RATE_LIMIT_STORAGE_URI") or os.getenv("REDIS_URL", "redis://localhost:6379/2")
try:
    _bucket = _RedisBucket(redis_url)
except Exception:
    class _InMemoryBucket:
        def __init__(self): self._hits = defaultdict(list)
        def is_allowed(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
            now = time.monotonic()
            cutoff = now - window
            self._hits[key] = [t for t in self._hits[key] if t > cutoff]
            if len(self._hits[key]) >= limit: return False, 0
            self._hits[key].append(now)
            return True, limit - len(self._hits[key])
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
        key = f"tenant:{tenant_id}" if tenant_id != "anonymous" else f"ip:{request.client.host if request.client else 'unknown'}"
        limit = self.tenant_overrides.get(tenant_id, self.default_rpm)

        allowed, remaining = _bucket.is_allowed(key, limit)
        record_rate_limit(tenant_id, allowed)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limit_exceeded", "detail": f"Limit of {limit}/min exceeded for {tenant_id}"},
                headers={"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": "0"}
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
