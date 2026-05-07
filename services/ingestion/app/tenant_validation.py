"""Tenant ID validation and resolution for all endpoints.

Consolidates the _resolve_tenant() pattern that was previously
duplicated across 9+ router files.
"""

import re
from typing import Optional

from fastapi import HTTPException, Path

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
    IngestionPrincipal from app.authz). For scoped callers, the
    authenticated principal is authoritative. Explicit tenant IDs remain
    available only for wildcard or otherwise unscoped principals so
    admin/dev flows can intentionally target another tenant. Validates
    the resolved tenant format and raises 400 if no tenant context is
    available.
    """
    principal_tenant_id = getattr(principal, "tenant_id", None)
    principal_scopes = getattr(principal, "scopes", []) or []

    if principal_tenant_id and "*" not in principal_scopes:
        tid = principal_tenant_id
    else:
        tid = tenant_id or principal_tenant_id

    if not tid:
        raise HTTPException(status_code=400, detail="Tenant context required")
    validate_tenant_id(tid)
    return tid


def ValidTenantId() -> str:
    """FastAPI Path dependency for validated tenant_id."""
    return Path(
        ...,
        description="Tenant identifier (alphanumeric, hyphens, underscores)",
        pattern=r"^[a-zA-Z0-9_-]{1,64}$",
    )
