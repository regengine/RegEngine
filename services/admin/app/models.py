"""Database models for Admin service with tenant isolation."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Tenant(BaseModel):
    """Tenant model for multi-tenant isolation."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    slug: str
    status: str = "active"  # active, suspended, archived
    settings: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "name": "Acme Corp",
                "slug": "acme-corp",
                "status": "active",
                "settings": {"mfa_required": True},
            }
        }


class User(BaseModel):
    """Global user identity."""

    id: UUID = Field(default_factory=uuid4)
    email: str
    is_sysadmin: bool = False
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "email": "jane@acme.com",
                "is_sysadmin": False,
                "status": "active",
            }
        }


class Role(BaseModel):
    """RBAC Role definition."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: Optional[UUID] = None  # None for system roles
    name: str
    permissions: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "name": "Compliance Manager",
                "permissions": ["compliance.read", "compliance.write"],
            }
        }


class Membership(BaseModel):
    """User membership in a tenant."""

    user_id: UUID
    tenant_id: UUID
    role_id: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AuditLog(BaseModel):
    """Audit log entry."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    actor_id: Optional[UUID] = None
    action: str
    resource_type: str
    resource_id: str
    changes: Optional[dict] = None
    metadata: Optional[dict] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewItem(BaseModel):
    """Review queue item with tenant isolation."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    document_id: str
    extraction_data: dict  # JSON-encoded ExtractionPayload
    status: str = "pending"  # pending, approved, rejected
    reviewer_id: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "document_id": "doc_001",
                "extraction_data": {
                    "subject": "financial institutions",
                    "action": "must maintain",
                    "confidence_score": 0.72,
                },
                "status": "pending",
            }
        }


class APIKeyDB(BaseModel):
    """API Key database model with tenant association."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    key_hash: str
    name: str
    enabled: bool = True
    rate_limit_per_minute: int = 60
    scopes: list[str] = Field(default_factory=lambda: ["read"])
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Production API Key",
                "enabled": True,
                "rate_limit_per_minute": 1000,
                "scopes": ["read", "write", "ingest"],
            }
        }


class AssessmentResult(BaseModel):
    """Compliance assessment result with tenant isolation."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    product_id: str
    framework: str  # e.g., "FSMA_204", "GDPR", "SOC2"
    status: str  # "pass", "fail", "partial"
    score: Optional[float] = None  # 0.0 - 1.0
    findings: list[dict] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=datetime.utcnow)
    assessed_by: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "product_id": "crypto-trading-platform",
                "framework": "FSMA_204",
                "status": "partial",
                "score": 0.75,
                "findings": [
                    {"requirement": "CTF-001", "status": "pass"},
                    {"requirement": "CTF-002", "status": "fail"},
                ],
            }
        }


class TenantOverride(BaseModel):
    """Tenant-specific regulatory interpretation overrides."""

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    provision_hash: str
    override_type: str  # "interpretation", "exemption", "custom_threshold"
    override_data: dict
    approved_by: str
    approved_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "provision_hash": "abc123def456",
                "override_type": "custom_threshold",
                "override_data": {"threshold_value": 10.0, "unit": "percent"},
                "approved_by": "compliance-officer@acme.com",
                "notes": "Approved exemption for pilot program",
            }
        }


from sqlalchemy import text

# ============================================================================
# Database session management
# ============================================================================

class TenantContext:
    """Helper class for managing tenant context in database sessions."""

    @staticmethod
    def set_tenant_context(session, tenant_id: UUID) -> None:
        """Set tenant context for PostgreSQL RLS.

        Args:
            session: SQLAlchemy session
            tenant_id: Tenant UUID

        This sets the PostgreSQL session variable that RLS policies use
        to enforce tenant isolation.
        """
        session.execute(
            text("SELECT set_tenant_context(:tid)"),
            {"tid": str(tenant_id)}
        )

    @staticmethod
    def get_tenant_context(session) -> Optional[UUID]:
        """Get current tenant context from PostgreSQL session.

        Args:
            session: SQLAlchemy session

        Returns:
            Current tenant UUID or None if not set
        """
        result = session.execute(text("SELECT get_tenant_context()")).scalar()
        if result is None:
            return None
        if isinstance(result, UUID):
            return result
        return UUID(result)

    @staticmethod
    def set_admin_context(session, is_sysadmin: bool) -> None:
        """Set administrative context to bypass RLS.

        Args:
            session: SQLAlchemy session
            is_sysadmin: Whether to enable sysadmin bypass
        """
        session.execute(
            text("SELECT set_admin_context(:is_admin)"),
            {"is_admin": is_sysadmin}
        )

    @staticmethod
    def clear_tenant_context(session) -> None:
        """Clear tenant context (use with caution).

        Args:
            session: SQLAlchemy session

        Note:
            This should only be used for admin operations that need
            to access data across all tenants.
        """
        session.execute(text("SELECT set_config('app.tenant_id', '', FALSE)"))
