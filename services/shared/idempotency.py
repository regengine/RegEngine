"""Idempotency middleware for POST endpoints using Redis.

Provides deduplication for POST requests via Idempotency-Key header.
Caches successful responses (2xx) for 24 hours to enable safe retries.
Gracefully degrades if Redis is unavailable.

Tenant isolation (#1237): cache keys are composed as
``idempotency:{tenant_id}:{idempotency_key}`` so that two tenants who
happen to choose the same key (``daily-batch-2026-04-17``) cannot see
each other's cached responses. The tenant is sourced from the
authenticated principal / ``X-Tenant-ID`` header, NOT the request body
— the body is read once per request and cannot be used to spoof cache
keys.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Callable, Optional

import redis.asyncio as redis
import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

logger = structlog.get_logger("idempotency")

# Cache key prefix for idempotency responses.
#
# Prior to #1237 the prefix was ``idempotency:`` and keys were not
# tenant-scoped, letting tenant B receive tenant A's cached 2xx response
# when both happened to choose the same idempotency key. The new format
# is ``idempotency:{tenant_id}:{idempotency_key}`` — see
# ``_build_cache_key`` below. Legacy un-scoped keys will expire out on
# their own 24h TTL.
IDEMPOTENCY_KEY_PREFIX = "idempotency:"
IDEMPOTENCY_TTL_SECONDS = 86400  # 24 hours
_ANONYMOUS_TENANT = "_anonymous_"  # placeholder when no tenant resolvable


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware that caches POST responses keyed by Idempotency-Key header.

    For POST requests with an Idempotency-Key header:
    - If a cached response exists for that key, return it immediately
    - Otherwise, let the request proceed and cache the response (2xx only)

    If Redis is unavailable, requests proceed normally without caching.
    """

    def __init__(self, app, redis_url: str | None = None):
        super().__init__(app)
        self.redis_url = redis_url or os.getenv("REDIS_URL", "rediss://redis:6379/0")
        self._client: redis.Redis | None = None
        self._redis_available: bool | None = None

    async def _get_client(self) -> redis.Redis | None:
        """Lazy-init Redis client with graceful degradation on failure."""
        if self._redis_available is False:
            return None
        if self._client is None:
            try:
                self._client = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=False,  # Store as bytes for binary-safe JSON
                    max_connections=10,
                    socket_connect_timeout=2,
                    socket_keepalive=True,
                )
                await self._client.ping()
                self._redis_available = True
                logger.info("idempotency_redis_connected")
            except Exception as exc:  # pragma: no cover - environment specific
                logger.warning("idempotency_redis_unavailable", error=str(exc))
                self._redis_available = False
                self._client = None
        return self._client

    def _should_cache(self, method: str) -> bool:
        """Only cache POST requests."""
        return method.upper() == "POST"

    def _get_cache_key(self, idempotency_key: str, tenant_id: Optional[str] = None) -> str:
        """Generate a tenant-scoped Redis cache key (#1237).

        The cache key is ``idempotency:{tenant_id}:{idempotency_key}``
        so that two tenants using the same idempotency key cannot see
        each other's cached responses. If tenant cannot be resolved
        (e.g. anonymous health probe), a sentinel namespace is used.
        """
        safe_tenant = tenant_id or _ANONYMOUS_TENANT
        return f"{IDEMPOTENCY_KEY_PREFIX}{safe_tenant}:{idempotency_key}"

    def _resolve_tenant_id(self, request: Request) -> Optional[str]:
        """Resolve tenant from authenticated context — never from body.

        Order: RBAC principal (set by auth middleware) > X-Tenant-ID
        header. The request body is NOT consulted: if we did, an
        attacker could include ``tenant_id`` in their JSON payload and
        spoof the cache namespace.
        """
        principal = getattr(request.state, "principal", None)
        principal_tenant = getattr(principal, "tenant_id", None) if principal else None
        if principal_tenant:
            return str(principal_tenant)
        header_tenant = request.headers.get("X-Tenant-ID")
        if header_tenant:
            return header_tenant.strip()
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check cache on receipt, cache response on return (if 2xx)."""
        # Only process POST requests with Idempotency-Key header
        if not self._should_cache(request.method):
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)

        # Validate key format (UUID or similar hex string, max 255 chars)
        if not idempotency_key or len(idempotency_key) > 255:
            return await call_next(request)

        tenant_id = self._resolve_tenant_id(request)
        cache_key = self._get_cache_key(idempotency_key, tenant_id)
        client = await self._get_client()

        # If Redis available, check for cached response
        if client is not None:
            try:
                cached_data = await client.get(cache_key)
                if cached_data is not None:
                    cached_response = json.loads(cached_data.decode("utf-8"))
                    logger.info(
                        "idempotency_cache_hit",
                        idempotency_key=idempotency_key,
                        tenant_id=tenant_id,
                        status=cached_response["status"],
                    )
                    return Response(
                        content=cached_response["body"],
                        status_code=cached_response["status"],
                        headers=dict(cached_response.get("headers", {})),
                    )
            except Exception as exc:
                logger.warning(
                    "idempotency_cache_read_error",
                    idempotency_key=idempotency_key,
                    tenant_id=tenant_id,
                    error=str(exc),
                )
                # Continue to process request on cache read error

        # Request proceeds normally
        response = await call_next(request)

        # Cache successful responses only (2xx status codes)
        if client is not None and 200 <= response.status_code < 300:
            try:
                # Read response body for caching
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                # Prepare cache payload
                cache_payload = {
                    "status": response.status_code,
                    "body": body.decode("utf-8", errors="replace"),
                    "headers": dict(response.headers),
                }

                # Cache with TTL
                await client.setex(
                    cache_key,
                    IDEMPOTENCY_TTL_SECONDS,
                    json.dumps(cache_payload),
                )
                logger.info(
                    "idempotency_cached",
                    idempotency_key=idempotency_key,
                    tenant_id=tenant_id,
                    status=response.status_code,
                )

                # Return a new response with the cached body
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

            except Exception as exc:
                logger.warning(
                    "idempotency_cache_write_error",
                    idempotency_key=idempotency_key,
                    tenant_id=tenant_id,
                    error=str(exc),
                )
                # Return original response on cache write error
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

        return response


class IdempotencyDependency:
    """Dependency injection for idempotency validation.

    Use in route handlers to validate and track Idempotency-Key.
    Validates that key is present (for strict mode) and properly formatted.
    """

    def __init__(self, strict: bool = False):
        """
        Args:
            strict: If True, raise 400 if Idempotency-Key is missing on POST.
                   If False (default), allow missing keys (middleware will skip caching).
        """
        self.strict = strict

    async def __call__(self, request: Request) -> str | None:
        """Extract and validate Idempotency-Key from request headers.

        Returns:
            The idempotency key if present, None if missing and not strict.

        Raises:
            HTTPException(400): If strict=True and key is missing on POST.
        """
        from fastapi import HTTPException

        if request.method.upper() != "POST":
            return None

        idempotency_key = request.headers.get("Idempotency-Key")

        if not idempotency_key:
            if self.strict:
                raise HTTPException(
                    status_code=400,
                    detail="Idempotency-Key header is required for POST requests",
                )
            return None

        if len(idempotency_key) > 255:
            raise HTTPException(
                status_code=400,
                detail="Idempotency-Key must be 255 characters or less",
            )

        logger.info("idempotency_key_validated", idempotency_key=idempotency_key)
        return idempotency_key
