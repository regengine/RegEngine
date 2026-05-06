"""Ingestion service authorization helpers."""

from __future__ import annotations

import hashlib
import hmac
import importlib
import logging
import os
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from shared.api_key_store import APIKeyResponse
from shared.auth import APIKey, require_api_key
from shared.permissions import has_permission
from shared.tenant_rate_limiting import consume_tenant_rate_limit

logger = logging.getLogger("authz")


# ---------------------------------------------------------------------------
# Auth failure rate limiting — blocks IPs after repeated failed auth attempts
# ---------------------------------------------------------------------------
_AUTH_FAIL_WINDOW = 300  # 5-minute window
_AUTH_FAIL_MAX = 15      # max failures before blocking
_auth_failures: dict[str, list[float]] = {}
_auth_failures_lock = threading.Lock()


def _check_auth_rate_limit(client_ip: str) -> None:
    """Raise 429 if client_ip has exceeded auth failure threshold."""
    now = time.time()
    cutoff = now - _AUTH_FAIL_WINDOW
    with _auth_failures_lock:
        attempts = _auth_failures.get(client_ip, [])
        attempts = [t for t in attempts if t > cutoff]
        _auth_failures[client_ip] = attempts
        if len(attempts) >= _AUTH_FAIL_MAX:
            logger.warning("auth_rate_limit_blocked: %s (%d failures)", client_ip, len(attempts))
            raise HTTPException(status_code=429, detail="Too many authentication failures")


def _record_auth_failure(client_ip: str) -> None:
    """Record a failed auth attempt for rate limiting."""
    with _auth_failures_lock:
        _auth_failures.setdefault(client_ip, []).append(time.time())


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
    if any(
        scope.endswith((".write", ".ingest", ".export", ".verify"))
        for scope in normalized_scopes
    ):
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
    # attacks. Header fallback retained for master-key callers; long-term,
    # all paths should resolve via services/shared/tenant_context.py.
    return "global"


def _requested_tenant_context(request: Request) -> Optional[str]:
    """Return tenant context that the request asserts via header.

    Used only for cross-tenant mismatch detection in ``require_permission``;
    the authoritative tenant is always the authenticated principal.

    The query-string fallback was removed (EPIC-A #1651) because Semgrep
    rule ``tenant-id-from-query-string`` correctly flags any read of
    ``request.query_params["tenant_id"]`` as untrustworthy. Headers are
    still read here as a transition-period defense — a future migration
    should switch the cross-check to use
    ``services/shared/tenant_context.py:resolve_tenant_context`` once
    ``get_ingestion_principal`` populates ``request.state.api_key`` so the
    shared resolver works in this service.
    """
    return request.headers.get("X-Tenant-ID") or request.headers.get("X-RegEngine-Tenant-ID")


def _principal_from_api_key(api_key: APIKey | APIKeyResponse) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id=api_key.key_id,
        scopes=list(api_key.scopes or []),
        tenant_id=api_key.tenant_id,
        auth_mode="scoped_key",
    )


def _current_settings():
    """Resolve settings from the live ``app.config`` module.

    Some ingestion tests temporarily replace ``app.config`` in ``sys.modules``.
    Looking it up lazily keeps authz aligned with the current module instance
    instead of holding a stale function reference across test-module swaps.
    """
    config_module = importlib.import_module("app.config")
    return config_module.get_settings()


def _lookup_scoped_key_from_db(raw_api_key: str) -> Optional[IngestionPrincipal]:
    """Fallback direct lookup when DatabaseAPIKeyStore is not enabled."""
    db_session = None
    try:
        from shared.database import SessionLocal

        key_hash = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()
        db_session = SessionLocal()
        row = db_session.execute(
            text(
                """
                SELECT key_id, tenant_id, scopes, enabled, expires_at
                FROM api_keys
                WHERE key_hash = :key_hash
                LIMIT 1
                """
            ),
            {"key_hash": key_hash},
        ).fetchone()
        if not row:
            return None

        key_id, tenant_id, scopes, enabled, expires_at = row
        if enabled is False:
            return None
        if expires_at and expires_at < datetime.now(timezone.utc):
            return None

        return IngestionPrincipal(
            key_id=str(key_id),
            scopes=list(scopes or []),
            tenant_id=str(tenant_id) if tenant_id else None,
            auth_mode="scoped_key_db_fallback",
        )
    except Exception:
        logger.warning("DB API key lookup failed", exc_info=True)
        return None
    finally:
        if db_session is not None:
            db_session.close()


async def get_ingestion_principal(
    request: Request,
    x_regengine_api_key: Optional[str] = Header(default=None, alias="X-RegEngine-API-Key"),
) -> IngestionPrincipal:
    """
    Authenticate caller and return principal context.

    Behavior:
    - If ``API_KEY`` is configured: require either that legacy master key or a
      valid scoped key from the API key store.
    - If ``API_KEY`` is not configured: keep local-dev behavior open.
    """
    settings = _current_settings()
    configured_api_key = getattr(settings, "api_key", None)
    client_ip = request.client.host if request.client else "unknown"

    # Check if this IP is temporarily blocked due to repeated auth failures
    _check_auth_rate_limit(client_ip)

    if configured_api_key:
        if x_regengine_api_key and hmac.compare_digest(
            x_regengine_api_key.encode("utf-8"),
            configured_api_key.encode("utf-8"),
        ):
            return IngestionPrincipal(
                key_id="legacy-master",
                scopes=["*"],
                tenant_id=None,
                auth_mode="legacy_master",
            )

        if not x_regengine_api_key:
            _record_auth_failure(client_ip)
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        try:
            api_key = await require_api_key(
                request=request,
                x_regengine_api_key=x_regengine_api_key,
            )
            return _principal_from_api_key(api_key)
        except HTTPException as exc:
            principal = _lookup_scoped_key_from_db(x_regengine_api_key)
            if principal:
                return principal
            _record_auth_failure(client_ip)
            raise exc

    # Local-dev/test default when API_KEY is not configured.
    _dev = _is_dev_env()
    if not x_regengine_api_key:
        if not _dev:
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

    # In dev mode, prefer scoped-key auth when available, but preserve historical
    # open behavior if key store is not configured.
    try:
        api_key = await require_api_key(
            request=request,
            x_regengine_api_key=x_regengine_api_key,
        )
        return _principal_from_api_key(api_key)
    except HTTPException:
        principal = _lookup_scoped_key_from_db(x_regengine_api_key)
        if principal:
            return principal
        if not _dev:
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


def require_permission(required_permission: str):
    """FastAPI dependency factory enforcing a required permission scope.

    Also cross-checks the authenticated principal's tenant against any
    tenant_id query/header context to prevent cross-tenant data access.
    """

    async def _dependency(
        request: Request,
        principal: IngestionPrincipal = Depends(get_ingestion_principal),
    ) -> IngestionPrincipal:
        if has_permission(principal.scopes, required_permission):
            # Cross-check: if the principal has a tenant_id AND the request
            # specifies a different tenant_id, reject unless principal has wildcard scope.
            requested_tenant = _requested_tenant_context(request)
            if (
                requested_tenant
                and principal.tenant_id
                and requested_tenant != principal.tenant_id
                and "*" not in principal.scopes
            ):
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
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for tenant '{tenant_id}' on '{scope}'",
                    headers={
                        "Retry-After": str(window),
                        "X-RateLimit-Limit": str(rpm),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Tenant": tenant_id,
                        "X-RateLimit-Scope": scope,
                    },
                )

            # Keep remaining available for downstream handlers/logging if needed.
            request.state.rate_limit_remaining = remaining
            request.state.rate_limit_scope = scope
            return principal
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions: requires '{required_permission}'",
        )

    return _dependency
