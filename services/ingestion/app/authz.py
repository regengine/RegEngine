"""Ingestion service authorization helpers."""

from __future__ import annotations

import logging
import os
import threading
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from shared.api_key_store import APIKeyResponse
from shared.auth import APIKey, optional_api_key, require_api_key
from shared.permissions import has_permission
from shared.tenant_rate_limiting import consume_tenant_rate_limit, rate_limit_reset_epoch

logger = logging.getLogger("authz")


# ---------------------------------------------------------------------------
# Auth failure rate limiting — blocks IPs after repeated failed auth attempts
#
# #2711: backed by shared.rate_limit.BruteForceLimiter (the #1392 admin
# privileged-auth pattern) instead of a bare module-level dict, so the failure
# budget is shared across workers/replicas when Redis is available and
# honors RATE_LIMIT_FAIL_MODE on Redis uncertainty. Falls back to a
# per-process counter (with a loud per-activation warning) when it isn't.
# ---------------------------------------------------------------------------
_AUTH_FAIL_WINDOW = 300  # 5-minute window
_AUTH_FAIL_MAX = 15  # max failures before blocking
_auth_limiter = None
_auth_limiter_lock = threading.Lock()


def _get_auth_limiter():
    global _auth_limiter
    if _auth_limiter is None:
        with _auth_limiter_lock:
            if _auth_limiter is None:
                from shared.rate_limit import BruteForceLimiter

                _auth_limiter = BruteForceLimiter(
                    namespace="ingestion_auth_fail",
                    max_failures=_AUTH_FAIL_MAX,
                    window_seconds=_AUTH_FAIL_WINDOW,
                )
    return _auth_limiter


def _check_auth_rate_limit(client_ip: str) -> None:
    """Raise 429 if client_ip has exceeded auth failure threshold."""
    if _get_auth_limiter().is_limited(client_ip):
        logger.warning("auth_rate_limit_blocked: %s", client_ip)
        raise HTTPException(status_code=429, detail="Too many authentication failures")


def _record_auth_failure(client_ip: str) -> None:
    """Record a failed auth attempt for rate limiting."""
    _get_auth_limiter().record_failure(client_ip)


def _is_dev_env() -> bool:
    """Return True only when development/test mode is explicit.

    Fail closed: unset, staging, preview, and any unknown value all require
    real authentication.
    """
    return os.getenv("REGENGINE_ENV", "").strip().lower() in {"development", "test"}


def _is_production_env() -> bool:
    """Backward-compatible fail-closed production check.

    Existing callers and tests still reference this name. The semantics are
    now intentionally conservative: anything that is not explicit dev/test is
    treated as production.
    """
    return not _is_dev_env()


def _strict_auth_required() -> bool:
    """Return True when the runtime must never use the dev-open fallback.

    Production, deployed staging/preview environments, and explicit
    ``REGENGINE_AUTH_STRICT=1`` all require credential-bound auth. The
    check also covers cloud deployments wearing a development/test name:
    ``shared.env`` forces production at import when it sees platform
    markers, but that runs only once, so a marker that appears later (or
    a process that never imported ``shared.env``) must still not get the
    fallback. Fail closed: any unexpected error resolves to strict.
    """
    try:
        from shared.env import is_cloud_deployment, requires_strict_auth_runtime

        if requires_strict_auth_runtime():
            return True
        return bool(_is_dev_env() and is_cloud_deployment())
    except Exception:
        logger.warning("strict_auth_probe_failed: failing closed to strict auth")
        return True


def assert_dev_open_disabled_in_production() -> None:
    """Deploy-time assertion: production must never satisfy the dev-open gate.

    Call once at service startup, before serving traffic. Raises
    RuntimeError when the process is a strict-auth runtime yet
    ``_is_dev_env()`` is True, which would let
    :func:`get_ingestion_principal` authenticate requests without a
    credential. Contradictory configuration must fail the deploy, not
    open an auth bypass.
    """
    if _is_dev_env() and _strict_auth_required():
        message = (
            "Refusing to start: REGENGINE_ENV names a development/test "
            "environment while the runtime requires strict authentication "
            "(production or a deployed strict-auth environment). The "
            "ingestion dev-open fallback would accept requests without an "
            "API key. Use a production environment name on deployed "
            "infrastructure and keep development names for local use only."
        )
        logger.critical(message)
        raise RuntimeError(message)


class IngestionPrincipal(BaseModel):
    """Authenticated caller context for ingestion endpoints."""

    key_id: str
    scopes: list[str] = Field(default_factory=list)
    tenant_id: Optional[str] = None
    auth_mode: str = "scoped_key"


_ACTION_BASE_RPM: dict[str, int] = {
    "read": 180,
    "write": 90,
    "ingest": 75,
    "export": 90,
    "verify": 45,
}

_ROLE_MULTIPLIER: dict[str, float] = {
    "viewer": 1.0,
    "operator": 1.5,
    "admin": 3.0,
}


def _normalize_permission(permission: str) -> str:
    return permission.strip().lower().replace(":", ".")


def _principal_rate_limit_role(principal: IngestionPrincipal) -> str:
    normalized_scopes = [_normalize_permission(scope) for scope in principal.scopes]
    if has_permission(normalized_scopes, "*") or any(scope.startswith("admin") for scope in normalized_scopes):
        return "admin"
    if any(scope.endswith((".write", ".ingest", ".export", ".verify")) for scope in normalized_scopes):
        return "operator"
    return "viewer"


@lru_cache(maxsize=1)
def _rate_limit_overrides() -> dict[str, int]:
    """
    Parse optional per-scope RPM overrides.

    Format:
        INGESTION_RBAC_RATE_LIMITS="fda.export=60,exchange.read=240"
    """
    raw = os.getenv("INGESTION_RBAC_RATE_LIMITS", "").strip()
    if not raw:
        return {}

    overrides: dict[str, int] = {}
    for item in raw.split(","):
        token = item.strip()
        if not token or "=" not in token:
            continue
        scope_raw, value_raw = token.split("=", 1)
        scope = _normalize_permission(scope_raw)
        try:
            value = int(value_raw.strip())
        except ValueError:
            continue
        overrides[scope] = max(1, value)
    return overrides


def _rpm_for_permission(required_permission: str, principal: IngestionPrincipal) -> int:
    required = _normalize_permission(required_permission)
    action = required.split(".")[-1] if "." in required else required
    default_rpm = max(1, int(os.getenv("INGESTION_RBAC_RATE_LIMIT_DEFAULT_RPM", "120")))
    base_rpm = _rate_limit_overrides().get(required, _ACTION_BASE_RPM.get(action, default_rpm))

    role = _principal_rate_limit_role(principal)
    multiplier = _ROLE_MULTIPLIER.get(role, 1.0)
    return max(1, int(round(base_rpm * multiplier)))


def _rate_limit_window_seconds() -> int:
    return max(1, int(os.getenv("INGESTION_RBAC_RATE_LIMIT_WINDOW_SECONDS", "60")))


def _store_rate_limit_headers(
    request: Request,
    response: Response,
    *,
    limit: int,
    remaining: int,
    tenant_id: str,
    scope: str,
    window: int,
) -> None:
    reset = str(rate_limit_reset_epoch(window))
    request.state.rate_limit_limit = limit
    request.state.rate_limit_remaining = remaining
    request.state.rate_limit_reset = reset
    request.state.rate_limit_tenant = tenant_id
    request.state.rate_limit_scope = scope
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = reset
    response.headers["X-RateLimit-Tenant"] = tenant_id
    response.headers["X-RateLimit-Scope"] = scope


def _tenant_for_rate_limit(request: Request, principal: IngestionPrincipal) -> str:
    if principal.tenant_id:
        return principal.tenant_id
    header_tenant = request.headers.get("X-Tenant-ID") or request.headers.get("X-RegEngine-Tenant-ID")
    if header_tenant:
        return str(header_tenant)
    # Query-string fallback removed (EPIC-A #1651): attacker-controllable
    # input must not determine the rate-limit bucket. A request that lands
    # here with no authenticated principal AND no X-Tenant-ID header gets
    # the shared "global" bucket, preventing tenant-bucket isolation
    # attacks. The header fallback is used only by the explicit local
    # dev-open principal; production keys are credential-bound.
    return "global"


def _requested_tenant_context(request: Request) -> Optional[str]:
    """Return query/header tenant context for DEFENSIVE mismatch detection.

    The returned value is NEVER used as a tenant trust signal — the
    authoritative tenant is always the authenticated principal. This
    helper exists solely so ``require_permission`` can detect a caller
    attempting to override the principal's tenant via query string or
    header and reject the request with 403.

    The Semgrep rule ``tenant-id-from-query-string`` correctly flags
    untrustworthy READS, but a defensive DETECTION read that never feeds
    a trust decision is the legitimate exception this helper exists for.
    Each query/header read below is annotated with ``nosemgrep:`` and
    only that specific finding is suppressed; new call sites elsewhere
    in the codebase still trip the gate.

    Long-term: replace this defensive check with
    ``services/shared/tenant_context.py:resolve_tenant_context()`` at each
    call site. The shared resolver now understands ``request.state.principal``;
    this helper remains only for older read endpoints that intentionally return
    404 on tenant mismatch to avoid tenant-existence oracles.
    """
    # nosemgrep: tenant-id-from-query-string  defensive-detection-not-trust
    query_tenant = request.query_params.get("tenant_id")
    header_tenant = request.headers.get("X-Tenant-ID") or request.headers.get("X-RegEngine-Tenant-ID")

    if query_tenant and header_tenant and query_tenant != header_tenant:
        raise HTTPException(
            status_code=400,
            detail="Conflicting tenant context: tenant_id does not match X-Tenant-ID header",
        )

    return query_tenant or header_tenant


def _principal_from_api_key(api_key: APIKey | APIKeyResponse) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id=api_key.key_id,
        scopes=list(api_key.scopes or []),
        tenant_id=api_key.tenant_id,
        auth_mode="scoped_key",
    )


async def get_ingestion_principal(
    request: Request,
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> IngestionPrincipal:
    """
    Authenticate caller and return principal context.

    Production accepts only database-backed, credential-bound API keys.
    Explicit development/test mode retains the historical open fallback.
    """
    client_ip = request.client.host if request.client else "unknown"

    # Check if this IP is temporarily blocked due to repeated auth failures
    _check_auth_rate_limit(client_ip)

    _dev = _is_dev_env()
    if not x_regengine_api_key:
        if _dev and _strict_auth_required():
            logger.warning(
                "dev_open_auth_blocked: path=%s client_ip=%s - "
                "development environment name with strict-auth runtime; "
                "requiring an API key",
                request.url.path,
                client_ip,
            )
            _record_auth_failure(client_ip)
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        if not _dev:
            _record_auth_failure(client_ip)
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        logger.warning(
            "dev_open_auth_activated: path=%s client_ip=%s - "
            "Request authenticated with dev-open fallback; "
            "this MUST NOT appear outside local development",
            request.url.path,
            client_ip,
        )
        return IngestionPrincipal(
            key_id="dev-open",
            scopes=["*"],
            tenant_id=None,
            auth_mode="dev_open",
        )

    # Once a credential is presented, never downgrade a rejected credential to
    # dev-open access.  This preserves workload/tenant key separation in every
    # environment and prevents rate-limit/backend failures being bypassed by a
    # second, weaker lookup path.
    try:
        api_key = await require_api_key(
            request=request,
            x_regengine_api_key=x_regengine_api_key,
        )
        return _principal_from_api_key(api_key)
    except HTTPException as exc:
        if exc.status_code == 401:
            _record_auth_failure(client_ip)
        raise


async def get_optional_ingestion_principal(
    request: Request,
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> Optional[IngestionPrincipal]:
    """Authenticate a presented tenant key without requiring one.

    Only absence is anonymous. A present invalid, expired, revoked,
    rate-limited, tenantless, or backend-unverifiable credential preserves the
    canonical error from :func:`shared.auth.require_api_key` and can never be
    downgraded to the anonymous path.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_auth_rate_limit(client_ip)

    # The retired shared administrative credential must not acquire meaning
    # merely because this route also permits a truly anonymous caller. Read it
    # directly from the request so X-Admin-Key stays absent from OpenAPI.
    if "x-admin-key" in request.headers:
        _record_auth_failure(client_ip)
        raise HTTPException(status_code=401, detail="X-Admin-Key is not an accepted authentication method")

    try:
        api_key = await optional_api_key(
            request=request,
            x_regengine_api_key=x_regengine_api_key,
        )
        if api_key is None:
            return None
        return _principal_from_api_key(api_key)
    except HTTPException as exc:
        # 401 is an invalid/expired/revoked key. The canonical tenant-key
        # dependency uses 403 when a workload credential is presented on a
        # tenant surface; that is also a rejected credential for this realm.
        if exc.status_code in {401, 403}:
            _record_auth_failure(client_ip)
        raise


def require_permission(required_permission: str):
    """FastAPI dependency factory enforcing a required permission scope.

    Also cross-checks the authenticated principal's tenant against any
    tenant_id query/header context to prevent cross-tenant data access.
    """

    async def _dependency(
        request: Request,
        response: Response,
        principal: IngestionPrincipal = Depends(get_ingestion_principal),
    ) -> IngestionPrincipal:
        request.state.principal = principal
        if has_permission(principal.scopes, required_permission):
            # Cross-check: if the principal has a tenant_id AND the request
            # specifies a different tenant_id, reject. Wildcard ``*`` scope
            # grants permission BREADTH (which actions), not tenant BREADTH
            # (which tenants) — a tenant-scoped key with ``*`` MUST NOT be
            # able to pivot to another tenant by passing ``?tenant_id=other``.
            #
            # The explicit local-development fallback carries
            # ``tenant_id=None`` and therefore bypasses this check through
            # the ``principal.tenant_id`` guard below. Production callers
            # are always bound to a tenant by their database-backed key.
            #
            # Fixes the wildcard-bypass finding in the 2026-05 audit
            # (services/ingestion/app/authz.py:385).
            requested_tenant = _requested_tenant_context(request)
            if requested_tenant and principal.tenant_id and requested_tenant != principal.tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail="Tenant mismatch: your API key does not have access to this tenant.",
                )

            tenant_id = _tenant_for_rate_limit(request, principal)
            window = _rate_limit_window_seconds()
            rpm = _rpm_for_permission(required_permission, principal)
            role = _principal_rate_limit_role(principal)
            scope = _normalize_permission(required_permission)

            allowed, remaining = consume_tenant_rate_limit(
                tenant_id=tenant_id,
                bucket_suffix=f"rbac.{scope}.{role}",
                limit=rpm,
                window=window,
            )
            if not allowed:
                reset = str(rate_limit_reset_epoch(window))
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for tenant '{tenant_id}' on '{scope}'",
                    headers={
                        "Retry-After": str(window),
                        "X-RateLimit-Limit": str(rpm),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": reset,
                        "X-RateLimit-Tenant": tenant_id,
                        "X-RateLimit-Scope": scope,
                    },
                )

            _store_rate_limit_headers(
                request,
                response,
                limit=rpm,
                remaining=remaining,
                tenant_id=tenant_id,
                scope=scope,
                window=window,
            )
            return principal
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions: requires '{required_permission}'",
        )

    return _dependency
