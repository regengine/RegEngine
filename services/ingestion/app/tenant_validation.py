"""Tenant ID validation and resolution for all endpoints.

Consolidates the _resolve_tenant() pattern that was previously
duplicated across 9+ router files.
"""

import re
from typing import Optional

from fastapi import HTTPException, Path
from shared.tenant_context import set_rls_tenant_id

# Alphanumeric, hyphens, underscores — 1 to 64 chars
_TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_tenant_id(tenant_id: str) -> str:
    """Validate and return tenant_id, or raise 400."""
    if not _TENANT_ID_PATTERN.match(tenant_id):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tenant_id format: must be 1-64 alphanumeric/hyphen/underscore characters",
        )
    return tenant_id


def resolve_tenant(tenant_id: Optional[str], principal) -> str:
    """Resolve tenant ID from auth principal, with controlled explicit fallback.

    Accepts any principal object with a tenant_id attribute (typically
    IngestionPrincipal from app.authz).

    Security invariant (mirrors ``shared/tenant_resolution.resolve_principal_tenant_id``):
    when the principal is bound to a tenant, that tenant is ALWAYS authoritative
    regardless of scope. A conflicting non-empty explicit ``tenant_id`` raises 403
    (tenant mismatch). The wildcard ``*`` scope grants permission BREADTH (which
    actions), not tenant BREADTH (which tenants) — a tenant-bound key with ``*``
    must not be able to pivot to another tenant via an explicit tenant input.

    Explicit-tenant targeting is reserved strictly for principals with NO bound
    tenant (legacy_master / dev_open, which carry ``tenant_id=None``), so those
    admin/dev flows can still intentionally target another tenant. Validates the
    resolved tenant format and raises 400 if no tenant context is available.
    """
    principal_tenant_id = getattr(principal, "tenant_id", None)

    if principal_tenant_id:
        if tenant_id and tenant_id != principal_tenant_id:
            raise HTTPException(
                status_code=403,
                detail="Tenant mismatch: your API key does not have access to this tenant.",
            )
        tid = principal_tenant_id
    else:
        tid = tenant_id or principal_tenant_id

    if not tid:
        raise HTTPException(status_code=400, detail="Tenant context required")
    validate_tenant_id(tid)
    # #2461: seed the RLS contextvar with the resolved tenant so the
    # Engine begin-hook applies app.tenant_id to every transaction the
    # calling handler opens. Called inline in handler bodies (same
    # context as the queries that follow); non-UUID slugs (unbound
    # legacy_master/dev_open principals) are stored but skipped at
    # apply time — slug tolerance mirrors set_tenant_guc_if_uuid.
    set_rls_tenant_id(tid)
    return tid


def ValidTenantId() -> str:
    """FastAPI Path dependency for validated tenant_id."""
    return Path(
        ...,
        description="Tenant identifier (alphanumeric, hyphens, underscores)",
        pattern=r"^[a-zA-Z0-9_-]{1,64}$",
    )
