"""Ingestion service authorization helpers."""

from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.config import get_settings
from shared.auth import APIKey, require_api_key
from shared.api_key_store import APIKeyResponse
from shared.permissions import has_permission


class IngestionPrincipal(BaseModel):
    """Authenticated caller context for ingestion endpoints."""

    key_id: str
    scopes: list[str] = Field(default_factory=list)
    tenant_id: Optional[str] = None
    auth_mode: str = "scoped_key"


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
    if not x_regengine_api_key:
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
        return IngestionPrincipal(
            key_id="dev-open",
            scopes=["*"],
            tenant_id=None,
            auth_mode="dev_open",
        )


def require_permission(required_permission: str):
    """FastAPI dependency factory enforcing a required permission scope."""

    async def _dependency(
        principal: IngestionPrincipal = Depends(get_ingestion_principal),
    ) -> IngestionPrincipal:
        if has_permission(principal.scopes, required_permission):
            return principal
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions: requires '{required_permission}'",
        )

    return _dependency
