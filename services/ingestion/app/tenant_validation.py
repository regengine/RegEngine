"""Tenant ID validation for all endpoints."""

import re
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


def ValidTenantId() -> str:
    """FastAPI Path dependency for validated tenant_id."""
    return Path(
        ...,
        description="Tenant identifier (alphanumeric, hyphens, underscores)",
        pattern=r"^[a-zA-Z0-9_-]{1,64}$",
    )
