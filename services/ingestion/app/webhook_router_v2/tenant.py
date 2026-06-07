"""Tenant resolution for webhook ingest (#2069) and the legacy
API-key → tenant lookup fallback.

Code moved verbatim from the original ``webhook_router_v2.py``.
Collaborators that lived at module level in the original file are
resolved through the package namespace (``_pkg``) at call time so
monkeypatching ``app.webhook_router_v2.<name>`` keeps working.
"""

from __future__ import annotations

import sys
from typing import Optional

from fastapi import HTTPException

from sqlalchemy.exc import SQLAlchemyError

from ..authz import IngestionPrincipal

_pkg = sys.modules[__package__]


def _lookup_tenant_id_for_api_key(raw_api_key: str) -> Optional[str]:
    """Best-effort legacy tenant lookup for callers without principal tenant context."""
    try:
        from shared.database import SessionLocal
        from sqlalchemy import bindparam as _bindparam
        from sqlalchemy import text as _text

        key_hashes = _pkg.api_key_hash_candidates(raw_api_key)
        _db = SessionLocal()
        try:
            stmt = _text(
                "SELECT tenant_id FROM api_keys WHERE key_hash IN :key_hashes LIMIT 1"
            ).bindparams(_bindparam("key_hashes", expanding=True))
            _row = _db.execute(
                stmt,
                {"key_hashes": key_hashes},
            ).fetchone()
            if _row and _row[0]:
                return str(_row[0])
        finally:
            _db.close()
    except (ImportError, SQLAlchemyError, ValueError, RuntimeError, ConnectionError, OSError) as _tenant_err:
        _pkg.logger.debug("tenant_key_lookup_failed", error=str(_tenant_err))
    return None


def _resolve_ingest_tenant_id(
    *,
    payload_tenant_id: Optional[str],
    principal: IngestionPrincipal,
    x_regengine_api_key: Optional[str],
    x_tenant_id: Optional[str],
) -> str:
    """Resolve tenant context without letting request bodies override scoped keys.

    Scoped API keys already carry tenant authority in ``principal.tenant_id``.
    Any divergent body/header tenant is therefore an attempted cross-tenant
    write and must fail before rate limiting or persistence (#2069).
    """
    if principal.tenant_id:
        for source, requested in (
            ("payload tenant_id", payload_tenant_id),
            ("X-Tenant-ID", x_tenant_id),
        ):
            if requested and requested != principal.tenant_id:
                raise HTTPException(
                    status_code=403,
                    detail=f"Tenant mismatch: {source} does not match authenticated API key tenant.",
                )
        _pkg.validate_tenant_id(principal.tenant_id)
        return principal.tenant_id

    # Legacy master/dev-open callers do not carry a principal tenant. Preserve
    # the historical fallback order for those modes only.
    tenant_id = payload_tenant_id
    if not tenant_id and x_regengine_api_key:
        tenant_id = _pkg._lookup_tenant_id_for_api_key(x_regengine_api_key)
    if not tenant_id and x_tenant_id:
        tenant_id = x_tenant_id
    if not tenant_id:
        _pkg.logger.error("Webhook rejected: no tenant_id resolved")
        raise HTTPException(status_code=400, detail="Tenant context required")
    _pkg.validate_tenant_id(tenant_id)
    return tenant_id
