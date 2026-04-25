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
                "name": "Example Corp",
                "slug": "example-corp",
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
    last_login_at: Optional[datetime] = None  # Added by migration v053

    class Config:
        schema_extra = {
            "example": {
                "email": "user@example.com",
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
    is_active: bool = True
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
                    "subject": "food facilities on the FTL",
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
    framework: str  # e.g., "FSMA_204"
    status: str  # "pass", "fail", "partial"
    score: Optional[float] = None  # 0.0 - 1.0
    findings: list[dict] = Field(default_factory=list)
    assessed_at: datetime = Field(default_factory=datetime.utcnow)
    assessed_by: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
                "product_id": "romaine-lettuce-12ct",
                "framework": "FSMA_204",
                "status": "partial",
                "score": 0.75,
                "findings": [
                    {"requirement": "CTE-SHIPPING-001", "status": "pass"},
                    {"requirement": "CTE-RECEIVING-002", "status": "fail"},
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
                "approved_by": "compliance@example.com",
                "notes": "Approved exemption for pilot program",
            }
        }


from sqlalchemy import text

# ============================================================================
# Database session management
# ============================================================================

# ============================================================================
# Response Models for API Endpoints
# ============================================================================

class ControlResponse(BaseModel):
    """Response model for control operations."""

    id: str
    tenant_id: str
    control_id: str
    title: str
    description: str
    framework: str
    created_at: str
    updated: Optional[bool] = None


class ProductResponse(BaseModel):
    """Response model for product operations."""

    id: str
    tenant_id: str
    product_name: str
    description: str
    product_type: str
    jurisdictions: list[str]
    created_at: str


class MappingResponse(BaseModel):
    """Response model for mapping operations."""

    id: str
    tenant_id: str
    control_id: str
    provision_hash: str
    mapping_type: str
    confidence: float
    notes: Optional[str]
    created_at: str


class LinkResponse(BaseModel):
    """Response model for control-product links."""

    product_id: str
    control_id: str
    tenant_id: str
    created_at: str


class PaginatedListResponse(BaseModel):
    """Generic paginated list response."""

    items: list[dict] = []
    total: int
    skip: int
    limit: int


class ControlsListResponse(BaseModel):
    """Response model for listing controls."""

    controls: list[dict]
    total: int
    skip: int
    limit: int


class ProductsListResponse(BaseModel):
    """Response model for listing products."""

    products: list[dict]
    total: int
    skip: int
    limit: int


class StatusResponse(BaseModel):
    """Generic status response."""

    status: str
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str
    status_code: Optional[int] = None


class PermissionCheckResponse(BaseModel):
    """Response for permission check."""

    message: str
    user: str


class SessionListResponse(BaseModel):
    """Response for listing sessions."""

    items: list[dict]
    total: int
    skip: int
    limit: int


class SessionRevokeResponse(BaseModel):
    """Response for revoking a session."""

    status: str


class RevokeAllSessionsResponse(BaseModel):
    """Response for revoking all sessions."""

    status: str
    revoked_count: int


class RegisterAdminResponse(BaseModel):
    """Response for initial admin registration."""

    message: str
    user_id: str
    tenant_id: str


class ChangePasswordResponse(BaseModel):
    """Response for password change."""

    status: str


class ResetPasswordResponse(BaseModel):
    """Response for password reset."""

    status: str


class TenantContext:
    """Helper class for managing tenant context in database sessions.

    NOTE on the Phase B canonical helper (``services.shared.tenant_context.set_tenant_guc``):
    these methods deliberately do NOT delegate to it. They use the
    SECURITY DEFINER SQL functions (``set_tenant_context(uuid)``,
    ``set_admin_context(bool)``, ``set_config(..., FALSE)``) which are
    SESSION-scoped — the GUC persists for the lifetime of the
    connection, not just the current transaction.

    Why session-scoped intentionally (do not "fix" without a full sweep):

      * Admin handlers commonly commit + start a new transaction mid-
        request (e.g. write the user, separately commit the audit log).
        Transaction-scoped ``SET LOCAL`` would die at the first commit;
        every subsequent query would run with no tenant context and
        either return zero rows (fail-hard RLS) or trip the legacy
        fail-open fallback (since superseded by v056/v059, but the
        change still represents a behavior delta).
      * The pool-bleed risk that motivates Phase B (the #1381 class of
        bug) is mitigated for THIS module by the connect/checkout
        listener in ``services/admin/app/database.py`` which clears
        ``app.tenant_id`` BEFORE every request sees a connection. See
        the security note at the top of that file for the full rationale.

    For NEW code in admin: prefer ``get_tenant_session`` (also in
    ``services/admin/app/database.py``) which uses ``SET LOCAL`` and
    is auto-cleared on COMMIT/ROLLBACK. The Phase B-migration plan
    explicitly carved this caller out as "investigated, intentionally
    not migrated" — see the PR description for migration 6/8.
    """

    @staticmethod
    def set_tenant_context(session, tenant_id: UUID) -> None:
        """Set tenant context for PostgreSQL RLS (session-scoped).

        Args:
            session: SQLAlchemy session
            tenant_id: Tenant UUID

        Sets ``app.tenant_id`` for the duration of the connection (NOT
        the transaction). See class docstring for why session-scope is
        intentional here and why ``set_tenant_guc`` (transaction-scope)
        is NOT the right migration target for this caller.
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
        """Set administrative context for RLS bypass (defense-in-depth).

        SECURITY NOTE: Setting this session variable alone is NOT sufficient
        to bypass RLS. The database policies also require the connection to
        use the 'regengine_sysadmin' role (current_user check). This means
        a regular 'regengine' role connection CANNOT bypass RLS even if
        this variable is set to 'true'. Only connections using the
        'regengine_sysadmin' role with this variable set will see
        cross-tenant data. All sysadmin bypass usage is logged to
        audit.sysadmin_access_log.

        When to use: Cross-tenant admin operations (user provisioning,
        tenant onboarding, system diagnostics). Never in request-scoped
        tenant sessions.

        Args:
            session: SQLAlchemy session
            is_sysadmin: Whether to enable sysadmin bypass
        """
        import structlog
        _logger = structlog.get_logger("rls-admin-context")
        if is_sysadmin:
            _logger.warning(
                "sysadmin_context_activated",
                msg="RLS sysadmin bypass enabled for this session. "
                    "Bypass only effective if connected as regengine_sysadmin role.",
            )
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
