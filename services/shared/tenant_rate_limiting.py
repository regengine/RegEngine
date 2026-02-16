"""
Per-Tenant Rate Limiting Middleware

Extends the existing shared/rate_limiting.py with tenant-aware limits.
Each tenant gets an independent rate limit bucket keyed by
``X-Tenant-ID`` header (or ``tenant_id`` from JWT context).

Usage:
    from shared.tenant_rate_limiting import TenantRateLimitMiddleware

    app.add_middleware(
        TenantRateLimitMiddleware,
        default_rpm=100,
        tenant_overrides={"enterprise-tenant-id": 500},
    )
"""

from __future__ import annotations

import os
import time
import logging
from collections import defaultdict
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("shared.tenant_rate_limiting")


import redis
import uuid

class _RedisBucket:
    """Distributed sliding-window rate limiter per key using Redis ZSET."""

    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    def is_allowed(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        """
        Check if a request is allowed for the given key using Redis ZSET.
        """
        pipe = self.redis.pipeline()
        now = time.time()
        cutoff = now - window
        
        # 1. Remove expired hits
        pipe.zremrangebyscore(key, 0, cutoff)
        # 2. Count hits in window
        pipe.zcard(key)
        # 3. Add current hit if not exceeded
        # We execute 1 & 2 first to get current state
        results = pipe.execute()
        current_count = results[1]

        if current_count >= limit:
            return False, 0

        # Add unique member to ZSET (using UUID to avoid collisions)
        pipe.zadd(key, {str(uuid.uuid4()): now})
        pipe.expire(key, window)
        pipe.execute()
        
        remaining = limit - (current_count + 1)
        return True, max(0, remaining)


# Initialize bucket using the shared RATE_LIMIT_STORAGE_URI or REDIS_URL
redis_url = os.getenv("RATE_LIMIT_STORAGE_URI") or os.getenv("REDIS_URL", "redis://localhost:6379/2")

# Module-level bucket (stateless across replicas)
# Gracefully fall back to memory if Redis connection fails or is not configured
try:
    _bucket = _RedisBucket(redis_url)
    logger.info("distributed_rate_limit_initialized", url=redis_url)
except Exception as e:
    logger.error("redis_rate_limit_fallback", error=str(e))
    # Fallback to current in-memory implementation for robustness
    class _InMemoryBucket:
        def __init__(self):
            self._hits: dict[str, list[float]] = defaultdict(list)
        def is_allowed(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
            now = time.monotonic()
            cutoff = now - window
            hits = self._hits[key]
            self._hits[key] = [t for t in hits if t > cutoff]
            if len(self._hits[key]) >= limit:
                return False, 0
            self._hits[key].append(now)
            return True, limit - len(self._hits[key])
    _bucket = _InMemoryBucket()


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-tenant rate limiting middleware.

    Rate limits are applied per ``X-Tenant-ID`` header value.
    Requests without a tenant ID fall back to per-IP limiting.

    Configuration:
        - ``default_rpm``: Default requests per minute per tenant (default: 100)
        - ``tenant_overrides``: Dict of tenant_id → custom RPM
        - ``exempt_paths``: Paths excluded from rate limiting (e.g. /health)
    """

    def __init__(
        self,
        app,
        default_rpm: int = 100,
        tenant_overrides: Optional[dict[str, int]] = None,
        exempt_paths: Optional[set[str]] = None,
    ):
        super().__init__(app)
        self.default_rpm = int(os.getenv("TENANT_RATE_LIMIT_RPM", str(default_rpm)))
        self.tenant_overrides = tenant_overrides or {}
        self.exempt_paths = exempt_paths or {"/health", "/ready", "/metrics", "/"}

        # Load overrides from env: TENANT_RATE_OVERRIDES=tid1:500,tid2:1000
        env_overrides = os.getenv("TENANT_RATE_OVERRIDES", "")
        if env_overrides:
            for pair in env_overrides.split(","):
                if ":" in pair:
                    tid, rpm = pair.strip().split(":", 1)
                    self.tenant_overrides[tid.strip()] = int(rpm.strip())

        logger.info(
            "tenant_rate_limiting_configured",
            extra={
                "default_rpm": self.default_rpm,
                "overrides": len(self.tenant_overrides),
            },
        )

    async def dispatch(self, request: Request, call_next):
        # Skip health/ready/metrics endpoints
        if request.url.path in self.exempt_paths:
            return await call_next(request)

        # Extract tenant ID from header or context
        tenant_id = (
            request.headers.get("X-Tenant-ID")
            or request.headers.get("x-tenant-id")
        )

        # Fall back to IP if no tenant
        key = f"tenant:{tenant_id}" if tenant_id else f"ip:{request.client.host if request.client else 'unknown'}"

        # Determine rate limit for this tenant
        limit = self.tenant_overrides.get(tenant_id, self.default_rpm) if tenant_id else self.default_rpm

        allowed, remaining = _bucket.is_allowed(key, limit, window=60)

        if not allowed:
            logger.warning(
                "tenant_rate_limited",
                extra={"tenant_id": tenant_id, "key": key, "limit": limit},
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "detail": f"Rate limit of {limit}/minute exceeded for {'tenant ' + tenant_id if tenant_id else 'your IP'}",
                    "retry_after": 60,
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        if tenant_id:
            response.headers["X-RateLimit-Tenant"] = tenant_id

        return response
