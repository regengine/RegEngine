"""Tenant validation middleware for Admin API.

Ensures X-Tenant-ID header matches the tenant_id from the validated API key.
This provides defense-in-depth against tenant isolation bypass attempts.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

import structlog
from fastapi import Header, HTTPException, status, Depends

from shared.auth import require_api_key, APIKey

logger = structlog.get_logger("tenant_middleware")


async def validate_tenant_header(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    api_key: APIKey = Depends(require_api_key),
) -> UUID:
    """Validate that X-Tenant-ID header matches API key's tenant.
    
    This middleware provides defense-in-depth:
    1. API key already has tenant_id embedded
    2. This validates the explicit header matches
    
    Returns:
        The validated tenant UUID
        
    Raises:
        HTTPException: If header is missing, invalid, or doesn't match API key
    """
    # Require X-Tenant-ID header
    if not x_tenant_id:
        logger.warning(
            "missing_tenant_header",
            key_id=api_key.key_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required",
        )
    
    # Validate UUID format
    try:
        header_tenant_id = UUID(x_tenant_id)
    except ValueError:
        logger.warning(
            "invalid_tenant_header_format",
            key_id=api_key.key_id,
            provided=x_tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID must be a valid UUID",
        )
    
    # Validate API key has tenant
    if not api_key.tenant_id:
        logger.warning(
            "api_key_missing_tenant",
            key_id=api_key.key_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is not associated with a tenant",
        )
    
    key_tenant_id = UUID(api_key.tenant_id)
    
    # Validate header matches API key tenant
    if header_tenant_id != key_tenant_id:
        logger.warning(
            "tenant_header_mismatch",
            key_id=api_key.key_id,
            header_tenant=str(header_tenant_id),
            key_tenant=str(key_tenant_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="X-Tenant-ID does not match API key tenant",
        )
    
    logger.debug(
        "tenant_validated",
        tenant_id=str(header_tenant_id),
        key_id=api_key.key_id,
    )
    
    return header_tenant_id


# Convenience dependency that just returns the tenant_id from API key
# Use this when you trust the API key and don't need double-validation
async def get_tenant_from_key(
    api_key: APIKey = Depends(require_api_key),
) -> UUID:
    """Get tenant ID directly from API key without header validation.
    
    Use this for internal/admin endpoints where header is optional.
    """
    if not api_key.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is not associated with a tenant",
        )
    return UUID(api_key.tenant_id)
