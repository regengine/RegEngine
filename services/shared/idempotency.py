"""Idempotency middleware for POST endpoints using Redis.

Provides deduplication for POST requests via Idempotency-Key header.
Caches successful responses (2xx) for 24 hours to enable safe retries.
Gracefully degrades if Redis is unavailable.

Tenant isolation (#1237): cache keys are composed as
``idempotency:{tenant_id}:{idempotency_key}`` so that two tenants who
happen to choose the same key (``daily-batch-2026-04-17``) cannot see
each other's cached responses.

The tenant is sourced ONLY from authenticated context: the RBAC principal,
``request.state.tenant_id``, the secret-gated ``X-RegEngine-Tenant-ID``
internal header, or a scoped API-key lookup. Neither the request body
(#1237) nor the raw ``X-Tenant-ID`` header (#2841) may name the namespace —
both are client-controlled, and this middleware serves cache hits before any
authentication runs. When no authenticated tenant is available the request
is simply not cached.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

import redis.asyncio as redis
import structlog
from fastapi import Request, Response
from shared.internal_caller import internal_tenant_id
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


def _tenant_value_to_str(value: Any) -> Optional[str]:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _lookup_tenant_id_for_api_key(raw_api_key: str) -> Optional[str]:
    """Resolve a scoped API key to its tenant before route dependencies run.

    The production monolith installs this middleware outside FastAPI route
    dependencies, so ``request.state.principal`` is not available yet for
    API-key-authenticated requests. This best-effort lookup uses the same key
    hash candidates as the auth path and only returns enabled, unexpired keys.
    """
    try:
        from shared.api_key_store import set_api_key_lookup_context
        from shared.database import SessionLocal
        from sqlalchemy import bindparam, text

        db_session = SessionLocal()
        try:
            lookup_proof = set_api_key_lookup_context(db_session, raw_api_key)
            if lookup_proof is None:
                return None
            _key_id, key_hashes = lookup_proof
            stmt = text(
                """
                SELECT tenant_id, enabled, expires_at
                FROM api_keys
                WHERE key_hash IN :key_hashes
                LIMIT 1
                """
            ).bindparams(bindparam("key_hashes", expanding=True))
            row = db_session.execute(stmt, {"key_hashes": key_hashes}).fetchone()
        finally:
            db_session.close()

        if not row:
            return None
        tenant_id, enabled, expires_at = row
        if enabled is False:
            return None
        if expires_at and expires_at < datetime.now(timezone.utc):
            return None
        return str(tenant_id) if tenant_id else None
    except Exception as exc:  # pragma: no cover - environment-specific fallback
        logger.debug("idempotency_api_key_tenant_lookup_failed", error=str(exc))
        return None


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
        """Resolve tenant from AUTHENTICATED context only — never client input.

        Order: RBAC principal (when an outer auth middleware set it) >
        request.state.tenant_id > secret-gated internal tenant header >
        scoped API-key lookup. Returns ``None`` when none of those yield a
        tenant, and ``dispatch`` then skips the cache entirely.

        SECURITY (#2841): this used to consult the raw ``X-Tenant-ID``
        header, and to consult it *ahead of* the authenticated API-key
        lookup below. In the production monolith this middleware is
        installed outside ``TenantContextMiddleware`` and outside all route
        dependencies (``server/main.py``), so the first two sources are
        always unset here and the header was the first populated one — a
        caller could name any tenant and, because ``dispatch`` serves a
        cache hit before ``call_next``, be handed that tenant's cached 2xx
        body with no credential at all. The request body was already
        excluded for exactly this reason (#1237); the header vector was
        left open.

        ``X-Tenant-ID`` is now ignored outright. The trusted-tenant path in
        ``shared/middleware/tenant_context.py`` refuses that header too, so
        this aligns the two. Genuine service-to-service callers keep a
        namespace via ``X-RegEngine-Tenant-ID`` + the internal secret, the
        same gate ``tenant_context.py`` applies.
        """
        principal = getattr(request.state, "principal", None)
        principal_tenant = getattr(principal, "tenant_id", None) if principal else None
        tenant = _tenant_value_to_str(principal_tenant)
        if tenant:
            return tenant
        state_tenant = getattr(request.state, "tenant_id", None)
        tenant = _tenant_value_to_str(state_tenant)
        if tenant:
            return tenant
        internal_tenant = internal_tenant_id(request.headers)
        if internal_tenant:
            return internal_tenant
        raw_api_key = request.headers.get("X-RegEngine-API-Key")
        if raw_api_key:
            return _lookup_tenant_id_for_api_key(raw_api_key)
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
        if not tenant_id:
            logger.info("idempotency_skipped_no_tenant", idempotency_key=idempotency_key)
            return await call_next(request)

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
                fail_mode = os.getenv("IDEMPOTENCY_FAIL_MODE", "degrade").strip().lower()
                logger.warning(
                    "idempotency_cache_read_error",
                    idempotency_key=idempotency_key,
                    tenant_id=tenant_id,
                    error=str(exc),
                    fail_mode=fail_mode,
                )
                # #2699: IDEMPOTENCY_FAIL_MODE=closed refuses the request
                # (503 + Retry-After) instead of re-executing it on a cache
                # read error. Default degrade re-executes — duplicate
                # evidence writes are still blocked by the DB-level
                # UNIQUE (tenant_id, idempotency_key) index (v072), which
                # is why degrade is acceptable here.
                if fail_mode == "closed":
                    return Response(
                        content=json.dumps(
                            {
                                "error": "idempotency_backend_unavailable",
                                "detail": "Idempotency cache unavailable — request not accepted. Please retry shortly.",
                            }
                        ),
                        status_code=503,
                        media_type="application/json",
                        headers={"Retry-After": "30"},
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
