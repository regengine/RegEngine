"""Shared tenant resolution — single source of truth.

Resolves tenant_id from explicit parameter, header, or API key lookup.
Replaces duplicate implementations in edi_ingestion, epcis_ingestion, and exchange_api.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from shared.api_key_store import set_api_key_lookup_context
from shared.database import get_db_safe
from shared.tenant_context import set_rls_tenant_id
from sqlalchemy import bindparam, text

logger = logging.getLogger(__name__)


def _normalize_tenant_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _pick_requested_tenant_id(
    explicit_tenant_id: Optional[str],
    x_tenant_id: Optional[str],
) -> Optional[str]:
    explicit = _normalize_tenant_id(explicit_tenant_id)
    header = _normalize_tenant_id(x_tenant_id)
    if explicit and header and explicit != header:
        raise HTTPException(
            status_code=400,
            detail="Conflicting tenant context: tenant_id does not match X-Tenant-ID header",
        )
    return explicit or header


def _lookup_api_key_tenant_id(x_regengine_api_key: Optional[str]) -> Optional[str]:
    raw_api_key = _normalize_tenant_id(x_regengine_api_key)
    if not raw_api_key:
        return None

    db = get_db_safe()
    try:
        lookup_proof = set_api_key_lookup_context(db, raw_api_key)
        if lookup_proof is None:
            return None
        _key_id, key_hashes = lookup_proof
        row = db.execute(
            text(
                """
                SELECT tenant_id
                FROM api_keys
                WHERE key_hash IN :key_hashes
                LIMIT 1
                """
            ).bindparams(bindparam("key_hashes", expanding=True)),
            {"key_hashes": key_hashes},
        ).fetchone()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception as exc:
        logger.warning("tenant_lookup_failed error=%s", str(exc))
    finally:
        db.close()

    return None


def resolve_tenant_id(
    explicit_tenant_id: Optional[str],
    x_tenant_id: Optional[str],
    x_regengine_api_key: Optional[str],
) -> Optional[str]:
    """Resolve tenant context from explicit ID, header, or API-key lookup.

    Scoped API keys are authoritative and cannot be overridden by a request
    body/query/header tenant. The local development fallback may supply a
    tenant explicitly, but conflicting explicit/header values are rejected.
    """
    requested_tenant_id = _pick_requested_tenant_id(explicit_tenant_id, x_tenant_id)
    api_key_tenant_id = _lookup_api_key_tenant_id(x_regengine_api_key)

    if api_key_tenant_id:
        if requested_tenant_id and requested_tenant_id != api_key_tenant_id:
            logger.warning(
                "tenant_override_rejected requested=%s api_key_tenant=%s",
                requested_tenant_id,
                api_key_tenant_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Tenant mismatch: your API key does not have access to this tenant.",
            )
        return api_key_tenant_id

    return requested_tenant_id


def resolve_principal_tenant_id(
    explicit_tenant_id: Optional[str],
    x_tenant_id: Optional[str],
    principal_tenant_id: Optional[str],
) -> str:
    """Resolve tenant context for an authenticated ingestion principal.

    Scoped principals cannot override their tenant through query/body/header.
    Only the local development fallback reaches this helper without a binding.
    """
    requested_tenant_id = _pick_requested_tenant_id(explicit_tenant_id, x_tenant_id)
    principal_tenant = _normalize_tenant_id(principal_tenant_id)

    if principal_tenant:
        if requested_tenant_id and requested_tenant_id != principal_tenant:
            logger.warning(
                "principal_tenant_override_rejected requested=%s principal_tenant=%s",
                requested_tenant_id,
                principal_tenant,
            )
            raise HTTPException(
                status_code=403,
                detail="Tenant mismatch: your API key does not have access to this tenant.",
            )
        # #2461: seed the RLS contextvar with the resolved tenant so the
        # Engine begin-hook applies app.tenant_id on every transaction
        # the calling handler opens (exchange_api, EDI, inflow_workbench,
        # recall_simulations, supplier_portal authenticated routes).
        set_rls_tenant_id(principal_tenant)
        return principal_tenant

    if requested_tenant_id:
        set_rls_tenant_id(requested_tenant_id)
        return requested_tenant_id

    raise HTTPException(status_code=400, detail="Tenant context required")
