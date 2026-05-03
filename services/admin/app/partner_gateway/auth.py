"""Auth dependencies for the partner gateway.

The partner gateway uses a dedicated ``X-RegEngine-Partner-Key`` header
rather than the generic ``X-RegEngine-API-Key`` header. Functionally
both headers validate against the same ``api_keys`` table (and the same
``DatabaseAPIKeyStore``), but separating headers gives operations three
things:

  1. WAF and rate-limit policies can target partner traffic without
     affecting internal/admin clients.
  2. Logs and audit trails can filter on header without parsing scopes.
  3. A leaked partner key cannot accidentally be used in a context that
     expects an internal admin key, because middlewares can hard-fail
     when a header is present in the wrong service.

Scope enforcement uses :func:`shared.permissions.has_permission`, which
already supports the ``partner.{resource}.{action}`` namespace pattern
declared in the OpenAPI spec.
"""
from __future__ import annotations

from typing import Any, Optional, Union

import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from shared.api_key_store import APIKeyResponse, DatabaseAPIKeyStore
from shared.auth import APIKey, get_key_store
from shared.permissions import has_permission

logger = structlog.get_logger("partner_gateway.auth")
_DEFAULT_PARTNER_RATE_LIMIT_PER_MINUTE = 1000


class PartnerPrincipal(BaseModel):
    """Authenticated caller context for partner gateway endpoints.

    Mirrors ``IngestionPrincipal`` in ``services/ingestion/app/authz.py``
    but is a separate type so the type system catches accidental use of
    a partner-scoped key in a non-partner code path.
    """

    key_id: str
    scopes: list[str] = Field(default_factory=list)
    tenant_id: Optional[str] = None
    partner_id: Optional[str] = None
    auth_mode: str = "partner_key"


def _rate_limit_per_minute(api_key: Union[APIKey, APIKeyResponse]) -> int:
    value = getattr(api_key, "rate_limit_per_minute", None)
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_PARTNER_RATE_LIMIT_PER_MINUTE
    return limit if limit > 0 else _DEFAULT_PARTNER_RATE_LIMIT_PER_MINUTE


async def _enforce_partner_rate_limit(
    key_store: Any,
    api_key: Union[APIKey, APIKeyResponse],
) -> None:
    limit = _rate_limit_per_minute(api_key)
    if isinstance(key_store, DatabaseAPIKeyStore):
        rate_info = await key_store.check_rate_limit(api_key.key_id, limit)
        if rate_info.allowed:
            return
        retry_after = getattr(rate_info, "retry_after", None) or 60
    else:
        if key_store.check_rate_limit(api_key.key_id, limit):
            return
        retry_after = 60

    logger.warning(
        "partner_rate_limit_exceeded",
        key_id=api_key.key_id,
        limit_per_minute=limit,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded",
        headers={"Retry-After": str(retry_after)},
    )


async def get_partner_principal(
    request: Request,
    x_regengine_partner_key: Optional[str] = Header(
        default=None, alias="X-RegEngine-Partner-Key"
    ),
) -> PartnerPrincipal:
    """Validate the partner API key and return a typed principal.

    Returns 401 if the header is missing or the key is invalid/revoked/expired.
    Returns 429 if the per-key rate limit is exhausted (handled by the
    underlying key store).
    """
    if not x_regengine_partner_key:
        logger.warning("partner_key_missing", path=request.url.path)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-RegEngine-Partner-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    key_store = get_key_store()
    api_key: Optional[Union[APIKey, APIKeyResponse]]
    if isinstance(key_store, DatabaseAPIKeyStore):
        api_key = await key_store.validate_key(x_regengine_partner_key)
    else:
        api_key = key_store.validate_key(x_regengine_partner_key)

    if not api_key:
        logger.warning(
            "partner_key_invalid",
            path=request.url.path,
            key_prefix=x_regengine_partner_key[:10],
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid partner API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # ``partner_id`` is a real column on ``api_keys`` (added in v076). We
    # MUST NOT read it from ``extra_data`` — that field is partner-
    # writable through ``update_key(metadata=...)`` and would let a
    # compromised partner change which other partner's tenants they can
    # see. The scope check below independently gates access; this field
    # only narrows queries to "your own" partner data.
    partner_id = getattr(api_key, "partner_id", None)
    if not partner_id:
        logger.warning(
            "partner_key_missing_partner_id",
            path=request.url.path,
            key_id=api_key.key_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Partner API key is not bound to a partner",
        )

    await _enforce_partner_rate_limit(key_store, api_key)

    return PartnerPrincipal(
        key_id=api_key.key_id,
        scopes=list(api_key.scopes or []),
        tenant_id=getattr(api_key, "tenant_id", None),
        partner_id=partner_id,
    )


def require_partner_scope(required_scope: str):
    """Dependency factory enforcing a required scope on the partner key.

    Mirrors the OpenAPI ``x-required-scopes`` declaration. Use one
    decorator per route:

        @router.get("/clients", dependencies=[Depends(require_partner_scope(
            "partner.clients.read"))])
        async def list_clients(...): ...

    Or as a positional dep when the handler also wants the principal:

        async def list_clients(
            principal: PartnerPrincipal = Depends(
                require_partner_scope("partner.clients.read")
            ),
        ): ...
    """

    async def _dep(
        principal: PartnerPrincipal = Depends(get_partner_principal),
    ) -> PartnerPrincipal:
        if not has_permission(principal.scopes, required_scope):
            logger.warning(
                "partner_scope_denied",
                key_id=principal.key_id,
                required_scope=required_scope,
                granted_scopes=principal.scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions: this endpoint requires "
                    f"'{required_scope}'."
                ),
            )
        return principal

    return _dep
