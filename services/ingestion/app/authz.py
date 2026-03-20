"""Ingestion service authorization helpers."""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.config import get_settings
from shared.auth import APIKey, require_api_key


def _is_production_env() -> bool:
    """Detect production by DATABASE_URL (Supabase pooler) or ENV=production."""
    if os.getenv("ENV", "").lower() == "production":
        return True
    db_url = os.getenv("DATABASE_URL", "")
    return "pooler.supabase.com" in db_url or "railway" in db_url
from shared.api_key_store import APIKeyResponse
from shared.permissions import has_permission
from shared.tenant_rate_limiting import consume_tenant_rate_limit


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
    if request.headers.get("X-Tenant-ID"):
        return str(request.headers["X-Tenant-ID"])
    if request.query_params.get("tenant_id"):
        return str(request.query_params["tenant_id"])
    return "global"


def _principal_from_api_key(api_key: APIKey | APIKeyResponse) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id=api_key.key_id,
        scopes=list(api_key.scopes or []),
        tenant_id=api_key.tenant_id,
        auth_mode="scoped_key",
    )


def _lookup_scoped_key_from_db(raw_api_key: str) -> Optional[IngestionPrincipal]:
    """Fallback direct lookup when DatabaseAPIKeyStore is not enabled."""
    db_session = None
    try:
        from shared.database import SessionLocal

        db_session = SessionLocal()
        row = db_session.execute(
            text(
                """
                SELECT key_id, tenant_id, scopes, enabled, expires_at
                FROM api_keys
                WHERE key_hash = encode(sha256(:raw::bytea), 'hex')
                LIMIT 1
                """
            ),
            {"raw": raw_api_key},
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
    settings = get_settings()
    configured_api_key = getattr(settings, "api_key", None)

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
            raise exc

    # Local-dev/test default when API_KEY is not configured.
    _prod = _is_production_env()
    if not x_regengine_api_key:
        if _prod:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
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
        if _prod:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        return IngestionPrincipal(
            key_id="dev-open",
            scopes=["*"],
            tenant_id=None,
            auth_mode="dev_open",
        )


def require_permission(required_permission: str):
    """FastAPI dependency factory enforcing a required permission scope.

    Also cross-checks the authenticated principal's tenant against any
    tenant_id query parameter to prevent cross-tenant data access.
    """

    async def _dependency(
        request: Request,
        principal: IngestionPrincipal = Depends(get_ingestion_principal),
    ) -> IngestionPrincipal:
        if has_permission(principal.scopes, required_permission):
            # Cross-check: if the principal has a tenant_id AND the request
            # specifies a different tenant_id, reject unless principal has wildcard scope.
            requested_tenant = request.query_params.get("tenant_id")
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
