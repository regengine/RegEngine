"""
PCOS shared dependencies — helper functions and imports used across all sub-routers.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import get_pcos_session
from ..models import TenantContext


def get_pcos_tenant_context(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    db: Session = Depends(get_pcos_session),
) -> tuple[Session, UUID]:
    """
    Get Entertainment database session with tenant context set for PCOS operations.
    
    As of V002 migration (Jan 31, 2026), all PCOS tables are in the Entertainment DB.
    For development/testing, uses header-based tenant ID.
    """
    if not x_tenant_id:
        # Default tenant for development
        tenant_id = UUID("00000000-0000-0000-0000-000000000001")
    else:
        try:
            tenant_id = UUID(x_tenant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tenant ID format")
    
    # Set tenant context for RLS
    TenantContext.set_tenant_context(db, tenant_id)
    
    return db, tenant_id
