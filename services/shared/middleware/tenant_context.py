"""
Tenant Context Middleware

Extracts tenant_id from authentication context (JWT token or API key) and
makes it available to request handlers via dependency injection.

This middleware ensures every request has a validated tenant_id before
reaching the application logic.

Usage:
    from shared.middleware.tenant_context import (
        TenantContextMiddleware,
        get_current_tenant_id
    )

    # Add to FastAPI app
    app.add_middleware(TenantContextMiddleware)

    # Use in route handlers
    @app.get("/items")
    async def get_items(tenant_id: UUID = Depends(get_current_tenant_id)):
        return await db.query(Item).filter(Item.tenant_id == tenant_id).all()
"""

import hmac
import logging
import os
import uuid
from typing import Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import REGISTRY, Counter
from shared.tenant_context import set_rls_tenant_id
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_TENANT_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/",
        "/health",
        "/ready",
        "/readiness",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/v1/billing/plans",
        "/api/v1/billing/webhooks",
        "/api/v1/billing/webhook/stripe",
    }
)


def _bind_tenant_log_context(tenant_id: uuid.UUID):
    """Bind the resolved tenant into logging context for this request (#2859).

    Imported lazily: ``shared.observability.context`` runs ``structlog.configure``
    at import time, and this middleware module is imported far more widely than
    that side effect should reach.

    Never raises. This middleware runs before auth on every request, so a
    logging-context failure must degrade to an unlabelled log line rather than
    turning a good request into a 500.
    """
    try:
        from shared.observability.context import bind_tenant_log_context

        return bind_tenant_log_context(str(tenant_id))
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("Could not bind tenant log context: %s", e)
        return None


def _unbind_tenant_log_context(token) -> None:
    """Release the binding made by :func:`_bind_tenant_log_context` (#2859)."""
    try:
        from shared.observability.context import unbind_tenant_log_context

        unbind_tenant_log_context(token)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("Could not unbind tenant log context: %s", e)


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


# Track spoofing attempts for alerting.
#
# #2858: deliberately UNLABELLED. This counter is incremented from PRE-AUTH
# middleware, so any label derived from the request (previously the raw peer
# IP via ``client_host``) is attacker-controlled and unbounded — a remote host
# can mint a new Prometheus time series per source address and grow the
# registry without limit. The rejected peer IP is still recorded, at full
# fidelity and with retention limits, on the structured warning log emitted
# next to the ``.inc()`` in ``_extract_tenant_id``.
tenant_header_rejected_total = _safe_counter(
    "tenant_header_rejected_total",
    "Unauthenticated X-RegEngine-Tenant-ID header rejections",
    [],
)

tenant_extraction_failed_total = _safe_counter(
    "tenant_extraction_failed_total",
    "Tenant context extraction failures on non-exempt paths",
    ["error_type"],
)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to extract and validate tenant_id from request context.

    Extracts tenant_id from:
    1. JWT token claims (preferred for user requests)
    2. X-RegEngine-Tenant-ID header (for service-to-service calls)
    3. X-API-Key lookup (for API key authentication)
    """

    async def dispatch(self, request: Request, call_next: Callable):
        """Process request and extract tenant context.

        Fail closed on unexpected extraction errors for protected paths. Public
        infrastructure and webhook paths may continue without tenant context.
        """
        path = request.url.path.rstrip("/") or "/"
        is_exempt = path in _TENANT_EXEMPT_PATHS

        # #2461: hygiene reset — no RLS tenant context may leak into this
        # request from the app-startup context. Auth dependencies remain
        # authoritative and re-seed downstream.
        set_rls_tenant_id(None)

        # #2859: token for the tenant logging binding released in the finally
        # below. Stays None whenever no tenant was resolved, so exempt paths
        # and rejected requests unbind nothing.
        tenant_log_token = None

        try:
            tenant_id = await self._extract_tenant_id(request)

            # Store in request state for easy access
            request.state.tenant_id = tenant_id

            # #2461: best-effort early seed for the RLS begin-hook when the
            # middleware itself resolved a tenant (JWT claim / internal
            # header / env service-account key). Auth dependencies overwrite
            # this with the authoritative principal tenant.
            if tenant_id is not None:
                set_rls_tenant_id(tenant_id)
                # #2859: without this, every log line emitted while serving
                # this request reads tenant_id="unknown" — the resolved tenant
                # was stored on request.state and never reached the logger.
                tenant_log_token = _bind_tenant_log_context(tenant_id)

            # Log tenant context
            logger.debug(f"Request {request.method} {request.url.path} for tenant {tenant_id}")

        except HTTPException:
            # Let the exception handler deal with it
            raise
        except (ValueError, TypeError, AttributeError, KeyError) as e:
            # ValueError: UUID parsing or header validation failures
            # TypeError: unexpected type conversions during extraction
            # AttributeError: missing request attributes
            # KeyError: missing JWT claims
            error_type = type(e).__name__
            tenant_extraction_failed_total.labels(error_type=error_type).inc()
            if is_exempt:
                logger.debug(
                    "Tenant extraction failed on exempt path %s: %s",
                    path,
                    e,
                )
                request.state.tenant_id = None
            else:
                logger.error(
                    "Tenant extraction failed on protected path %s: %s - rejecting request",
                    path,
                    e,
                )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Unable to establish tenant context"},
                )

        try:
            response = await call_next(request)
            return response
        finally:
            # #2859: always release, even when the handler raised, so the
            # tenant cannot leak into the next request on this context.
            if tenant_log_token is not None:
                _unbind_tenant_log_context(tenant_log_token)

    async def _extract_tenant_id(self, request: Request) -> Optional[uuid.UUID]:
        """
        Extract tenant_id from various sources.

        Priority order:
        1. JWT token claims (if user is authenticated)
        2. X-RegEngine-Tenant-ID header
        3. API key lookup
        """
        # Method 1: From JWT token
        if hasattr(request.state, "user") and request.state.user:
            tenant_id_str = request.state.user.get("tenant_id")
            if tenant_id_str:
                try:
                    return uuid.UUID(tenant_id_str)
                except ValueError:
                    # #2696: a tenant claim that fails UUID parsing inside a
                    # VALIDATED token is a signal (minting bug or tampering),
                    # not noise. Re-raise instead of falling through to
                    # weaker sources — dispatch converts this to a 401 on
                    # protected paths (exempt paths proceed tenant-less).
                    logger.error("Malformed tenant_id claim in validated JWT: %r", tenant_id_str)
                    raise

        # Method 2: From custom header (Internal/Service-to-service ONLY)
        # WARNING: This is a potential spoofing vector if not stripped at the gateway.
        # We only trust this header if we are in a 'trusted' internal context.
        tenant_header = request.headers.get("X-RegEngine-Tenant-ID")
        if tenant_header:
            # Validate against the configured internal service secret (env var only —
            # never compare to a hardcoded string in source code).
            internal_secret = request.headers.get("X-RegEngine-Internal-Secret")
            configured_secret = os.getenv("REGENGINE_INTERNAL_SECRET")
            is_internal = bool(
                configured_secret and internal_secret and hmac.compare_digest(internal_secret, configured_secret)
            )

            if is_internal:
                try:
                    return uuid.UUID(tenant_header)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid tenant ID format in header: {tenant_header}")
            else:
                # Defense-in-depth: reject and track spoofing attempts.
                # The nginx gateway should strip this header from external
                # traffic, so seeing it here without a valid internal secret
                # is suspicious.
                client_host = request.client.host if request.client else "unknown"
                logger.warning(
                    "Rejected unauthenticated X-RegEngine-Tenant-ID header — "
                    "possible spoofing attempt or missing gateway header strip",
                    extra={
                        "client_host": client_host,
                        "attempted_tenant": tenant_header,
                    },
                )
                # #2858: no client_host label — the IP lives in the log line above.
                tenant_header_rejected_total.inc()

        return None


def _tenant_id_from_authenticated_principal(request: Request) -> Optional[uuid.UUID]:
    """Resolve tenant_id from the principal attached by ``require_api_key``.

    The middleware's env-only Method 3 cannot resolve per-key DB-issued tenants,
    so DB-issued API keys would otherwise have no tenant source and fail closed
    with 401 on every ``get_current_tenant_id``-guarded route (#2524). Because
    route dependencies run after the middleware, ``require_api_key`` has already
    stored the validated key on ``request.state.api_key`` by the time this is
    read; we coerce its ``tenant_id`` to UUID. Returns None when no principal /
    tenant is present or the value is not a valid UUID (caller fails closed).
    """
    api_key = getattr(request.state, "api_key", None)
    if api_key is None:
        return None
    tenant_id_raw = getattr(api_key, "tenant_id", None)
    if not tenant_id_raw:
        return None
    try:
        return uuid.UUID(str(tenant_id_raw))
    except (ValueError, AttributeError, TypeError):
        logger.warning("Invalid tenant_id on authenticated API key principal: %s", tenant_id_raw)
        return None


def _as_uuid(value: object) -> Optional[uuid.UUID]:
    """Parse ``value`` as a UUID; None when it is not one."""
    try:
        return uuid.UUID(str(value).strip())
    except (ValueError, AttributeError, TypeError):
        return None


async def get_current_tenant_id(request: Request) -> uuid.UUID:
    """
    FastAPI dependency to get the current request's tenant_id.

    Resolution order:
    1. The tenant on the authenticated principal that ``require_api_key``
       attaches to ``request.state.api_key`` — this is how per-key DB-issued
       API keys resolve their own tenant (#2524), and when it is present it is
       the single source of truth.
    2. ``request.state.tenant_id`` set by ``TenantContextMiddleware`` (JWT or
       authenticated internal header). When a principal tenant is also present
       the middleware tenant is only an assertion that must match it: a
       divergence is rejected with 409 ``E_TENANT_MISMATCH`` (the
       ``shared.auth.reconcile_tenant_scope`` contract, #2511) before any data
       access. It is never resolved in favour of the middleware — since #3698
       the key resolves first on every graph router, which had made the
       middleware tenant the last writer of the RLS contextvar, so key tenant A
       plus middleware tenant B read and wrote B's rows on the routers that do
       not call ``reconcile_tenant_scope`` themselves.

    Raises HTTPException(401) if no tenant_id is available (fail closed).

    Usage:
        @app.get("/reports")
        async def get_reports(
            tenant_id: UUID = Depends(get_current_tenant_id)
        ):
            return await fetch_reports(tenant_id)
    """
    middleware_tenant = getattr(request.state, "tenant_id", None)
    api_key = getattr(request.state, "api_key", None)
    principal_tenant = _tenant_id_from_authenticated_principal(request)

    if api_key is not None and principal_tenant is None:
        # An authenticated principal with no usable tenant (missing, empty or
        # unparseable) is a malformed credential, never a reason to fall back
        # to the middleware tenant: that would let a header or claim pick the
        # tenant with no principal authority behind it.
        raise HTTPException(status_code=401, detail="Tenant ID not found in authentication context")

    # Compare parsed UUIDs, so equivalent spellings (case, braces, no hyphens)
    # never 409 and a middleware value that is not a UUID never matches.
    if (
        principal_tenant is not None
        and middleware_tenant is not None
        and _as_uuid(middleware_tenant) != principal_tenant
    ):
        logger.warning(
            "graph_tenant_scope_mismatch: middleware tenant differs from the authenticated API key's tenant",
            extra={
                "authenticated_tenant": str(principal_tenant),
                "middleware_tenant": str(middleware_tenant),
                "key_id": getattr(api_key, "key_id", None),
                "path": request.url.path if getattr(request, "url", None) is not None else None,
            },
        )
        raise HTTPException(status_code=409, detail="E_TENANT_MISMATCH")

    tenant_id = principal_tenant if principal_tenant is not None else middleware_tenant

    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant ID not found in authentication context")

    # #2461: seed the RLS contextvar — this dependency is the tenant
    # funnel for all graph routers (traceability, recall, lineage,
    # compliance, metrics, labels), whose fsma_recall / fsma_audit
    # private engines are covered by the class-level begin-hook. The
    # comparison above only works when require_api_key has already run:
    # every graph route resolves the key first (router-level dependency
    # or declaration order), and test_graph_compliance_key_before_tenant
    # fails any route that does not, because a tenant resolved before the
    # key would hand the handler the middleware tenant with no 409.
    set_rls_tenant_id(tenant_id)
    return tenant_id


async def get_optional_tenant_id(request: Request) -> Optional[uuid.UUID]:
    """
    FastAPI dependency to get tenant_id, but don't require it.

    Returns None if no tenant_id is available (doesn't raise exception).

    Usage:
        @app.get("/public-data")
        async def get_data(
            tenant_id: Optional[UUID] = Depends(get_optional_tenant_id)
        ):
            if tenant_id:
                return await fetch_tenant_data(tenant_id)
            else:
                return await fetch_public_data()
    """
    return getattr(request.state, "tenant_id", None)


async def validate_tenant_access(request: Request, tenant_id: uuid.UUID) -> uuid.UUID:
    """
    Validate that the current user has access to the specified tenant.

    This is useful when tenant_id is provided as a path/query parameter
    and you need to verify the user is allowed to access that tenant.

    Usage:
        @app.get("/tenants/{tenant_id}/data")
        async def get_tenant_data(
            tenant_id: UUID,
            validated_tenant_id: UUID = Depends(validate_tenant_access)
        ):
            # validated_tenant_id is guaranteed to match user's tenant
            return await fetch_data(validated_tenant_id)
    """
    current_tenant_id = await get_current_tenant_id(request)

    if current_tenant_id != tenant_id:
        logger.warning(
            f"Tenant access denied: user in tenant {current_tenant_id} attempted to access tenant {tenant_id}"
        )
        raise HTTPException(status_code=403, detail=f"Access denied to tenant {tenant_id}")

    return tenant_id
