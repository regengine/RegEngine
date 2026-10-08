"""Idempotency middleware for POST endpoints using Redis.

Provides deduplication for POST requests via Idempotency-Key header.
Caches successful responses (2xx) for 24 hours to enable safe retries.
Gracefully degrades if Redis is unavailable unless IDEMPOTENCY_FAIL_MODE=closed.
The default degrade mode can dispatch duplicates on an ambiguous Redis failure;
use closed mode where cache-level duplicate suppression is required.

Keys bind exact request bytes, URL, content type, and credential to the tenant.
Conflicting and legacy unbound cache entries return 409. An active or uncertain
reservation also returns 409 and remains for the 24-hour retry window after a
crash or failed publish. Such outcomes need reconciliation before retrying with
another key. Rolling deployment requires retiring old writers first: old code
cannot safely interpret reservation payloads or enforce fingerprint binding.

Browser Cookie/Authorization requests and /auth operations bypass this cache,
preserving session revocation and single-use authentication checks. Webhook
replays bind the signature and current signing secret as well as request bytes.
API-key replay fingerprints include fresh database scopes and jurisdictions,
so same-key permission changes invalidate older responses. A replay still skips
route dependencies: unrelated dynamic authorization policies and rate limits
require an outer enforcement layer or a future route-level replay boundary.

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

import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

import redis.asyncio as redis
import structlog
from fastapi import Request, Response
from shared.internal_caller import internal_tenant_id
from starlette.middleware.base import BaseHTTPMiddleware

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


def _lookup_api_key_context(raw_api_key: str) -> Optional[tuple[str, str]]:
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
                SELECT tenant_id, enabled, expires_at, key_id, scopes, allowed_jurisdictions
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
        tenant_id, enabled, expires_at, key_id, scopes, jurisdictions = row
        if enabled is False:
            return None
        # Naive datetimes (SQLite) are read as UTC: comparing naive with
        # aware raises TypeError, which the handler below would swallow
        # into "no tenant" and silently disable idempotency caching.
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < datetime.now(timezone.utc):
            return None
        if not tenant_id:
            return None
        # Permission narrowing may retain the same raw key. Bind the current
        # authoritative authorization state so an older response cannot survive it.
        snapshot = json.dumps(
            [
                str(tenant_id),
                str(key_id),
                sorted(scopes or []),
                sorted(jurisdictions or []),
            ]
        )
        return str(tenant_id), hashlib.sha256(snapshot.encode()).hexdigest()
    except Exception:  # pragma: no cover - environment-specific fallback
        logger.debug("idempotency_api_key_context_lookup_failed")
        return None


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware that caches POST responses keyed by Idempotency-Key header.

    For POST requests with an Idempotency-Key header:
    - Reject a key already bound to another request with 409.
    - Replay completed requests; reject active reservations with 409.
    - Reserve new requests atomically, then cache successful responses.

    Redis failures follow IDEMPOTENCY_FAIL_MODE (degrade by default).
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
                    socket_timeout=2,
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

        Order: authoritative presented API key > RBAC principal (when an outer
        auth middleware set it) > request.state.tenant_id > secret-gated internal
        tenant header. Returns ``None`` when none of those yield a
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
        # A presented key must be rechecked even if an outer middleware or
        # internal header already provided a tenant. Never fall back from a
        # revoked/unverifiable key to a cached response under another auth mode.
        raw_api_key = request.headers.get("X-RegEngine-API-Key")
        if raw_api_key:
            context = _lookup_api_key_context(raw_api_key)
            if context is None:
                return None
            tenant, authorization_fingerprint = context
            request.state.idempotency_authorization_fingerprint = authorization_fingerprint
            return tenant
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
        return None

    async def _request_fingerprint(self, request: Request) -> str:
        # Bind the exact operation and credential, not just the tenant. Never
        # persist raw credentials or body. JSON whitespace changes conflict too.
        parts = [
            request.method.upper(),
            str(request.url),
            request.headers.get("content-type", ""),
            request.headers.get("authorization", ""),
            request.headers.get("x-regengine-api-key", ""),
            request.headers.get("x-regengine-internal-secret", ""),
            request.headers.get("cookie", ""),
            getattr(request.state, "idempotency_authorization_fingerprint", ""),
        ]
        if request.url.path.rstrip("/") == "/api/v1/webhooks/ingest":
            # Same trimmed configuration as webhook_router_v2.security. Bind
            # both proof and signing-key epoch so missing/rotated proof cannot
            # bypass the route's HMAC validator through an old cached response.
            parts.extend(
                [
                    request.headers.get("x-webhook-signature", ""),
                    hashlib.sha256(os.getenv("WEBHOOK_HMAC_SECRET", "").strip().encode()).hexdigest(),
                ]
            )
        digest = hashlib.sha256(json.dumps(parts).encode())
        # This middleware is outside RequestSizeLimitMiddleware in the monolith.
        # Bound actual streamed bytes before retaining a body for downstream use.
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 10 * 1024 * 1024:
                raise ValueError("idempotency request body exceeds 10 MB")
            body.extend(chunk)
        # Starlette's _CachedRequest replays _body to call_next after consumption.
        request._body = bytes(body)
        digest.update(body)
        return digest.hexdigest()

    @staticmethod
    def _error(status: int, code: str) -> Response:
        return Response(
            json.dumps({"error": code}),
            status_code=status,
            media_type="application/json",
            headers={"Retry-After": "30"} if status == 503 else {},
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Bind retries to one operation; reserve its key before dispatch.

        Reservations last for the retry window. A crash or uncertain cache
        write leaves the reservation in place rather than dispatching twice.
        This is cache-level protection, not exactly-once database execution.
        Route dependencies still run only on the original request; callers
        must not treat a tenant lookup as fresh route authorization.
        """
        if not self._should_cache(request.method):
            return await call_next(request)
        # Browser/session authority has revocation and single-use semantics
        # beyond API-key scopes. Always let its canonical dependencies execute.
        if (
            "cookie" in request.headers
            or "authorization" in request.headers
            or request.url.path == "/auth"
            or request.url.path.startswith("/auth/")
            or request.url.path == "/v1/auth"
            or request.url.path.startswith("/v1/auth/")
        ):
            return await call_next(request)
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key or len(idempotency_key) > 255:
            return await call_next(request)
        tenant_id = self._resolve_tenant_id(request)
        if not tenant_id:
            return await call_next(request)

        client = await self._get_client()
        closed = os.getenv("IDEMPOTENCY_FAIL_MODE", "degrade").strip().lower() == "closed"
        if client is None:
            if closed:
                return self._error(503, "idempotency_backend_unavailable")
            return await call_next(request)

        try:
            fingerprint = await asyncio.wait_for(self._request_fingerprint(request), timeout=120)
        except ValueError:
            return self._error(413, "payload_too_large")
        except asyncio.TimeoutError:
            return self._error(504, "request_timeout")
        cache_key = self._get_cache_key(idempotency_key, tenant_id)
        reservation = json.dumps({"fingerprint": fingerprint, "owner": uuid4().hex})
        try:
            cached_data = await client.get(cache_key)
            if cached_data is None:
                acquired = await client.set(
                    cache_key,
                    reservation,
                    nx=True,
                    ex=IDEMPOTENCY_TTL_SECONDS,
                )
                if not acquired:
                    cached_data = await client.get(cache_key)
                    if cached_data is None:
                        return self._error(503, "idempotency_backend_unavailable")
            if cached_data is not None:
                cached = json.loads(cached_data)
                # Old payloads lack operation binding. Do not replay them or
                # silently re-execute a potentially committed operation.
                if cached.get("fingerprint") != fingerprint:
                    return self._error(409, "idempotency_key_conflict")
                if "status" not in cached:
                    return self._error(409, "idempotency_request_in_progress")
                return Response(
                    content=(
                        cached["body"].encode("latin1") if cached.get("body_encoding") == "latin1" else cached["body"]
                    ),
                    status_code=cached["status"],
                    headers=cached.get("headers", {}),
                )
        except Exception:
            logger.warning("idempotency_cache_read_error", fail_closed=closed)
            if closed:
                return self._error(503, "idempotency_backend_unavailable")
            # Do not overwrite a reservation/cache entry after an uncertain read.
            return await call_next(request)

        response = await call_next(request)
        # Compare-and-set prevents an expired owner overwriting another request.
        if not 200 <= response.status_code < 300:
            try:
                await client.eval(
                    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) end return 0",
                    1,
                    cache_key,
                    reservation,
                )
            except Exception:
                logger.warning("idempotency_reservation_release_error")
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        # JSON responses are the supported cache format. Preserve binary bytes
        # exactly using latin1 as a reversible storage encoding.
        payload = json.dumps(
            {
                "fingerprint": fingerprint,
                "status": response.status_code,
                "body": body.decode("latin1"),
                "body_encoding": "latin1",
                "headers": dict(response.headers),
            }
        )
        try:
            await client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then "
                "return redis.call('setex', KEYS[1], ARGV[2], ARGV[3]) end return 0",
                1,
                cache_key,
                reservation,
                IDEMPOTENCY_TTL_SECONDS,
                payload,
            )
        except Exception:
            logger.warning("idempotency_cache_write_error")
        return Response(content=body, status_code=response.status_code, headers=dict(response.headers))


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
