"""SQLAlchemy ORM models for admin service data persistence."""

from __future__ import annotations

import uuid as uuid_module

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.types import TypeDecorator, CHAR, JSON
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class GUID(TypeDecorator):
    """Platform-independent UUID type (works with SQLite and Postgres)."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID

            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid_module.UUID):
            return uuid_module.UUID(value)
        return value


class JSONType(TypeDecorator):
    """Platform-independent JSON type (JSONB on Postgres, JSON elsewhere)."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class TenantModel(Base):
    """Root of trust for multi-tenancy."""
    __tablename__ = "tenants"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="active")  # active, suspended, archived
    settings = Column(JSONType(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_tenants_slug", "slug"),
    )


class UserModel(Base):
    """Global user identity."""
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    email = Column(String, nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    mfa_secret = Column(String, nullable=True)
    is_sysadmin = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="active")  # active, locked, invited
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_users_email", "email"),
    )


class RoleModel(Base):
    """RBAC Roles (System or Custom)."""
    __tablename__ = "roles"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=True)  # Null = System Role
    name = Column(String, nullable=False)
    permissions = Column(JSONType(), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_roles_tenant", "tenant_id"),
    )


class MembershipModel(Base):
    """Links users to tenants with specific roles."""
    __tablename__ = "memberships"

    user_id = Column(GUID(), ForeignKey("users.id"), primary_key=True)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), primary_key=True)
    role_id = Column(GUID(), ForeignKey("roles.id"), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(GUID(), nullable=True)

    __table_args__ = (
        Index("ix_memberships_user", "user_id"),
        Index("ix_memberships_tenant", "tenant_id"),
    )




class AuditLogModel(Base):
    """Append-only tamper-evident audit trail.

    No UPDATE or DELETE permitted. Each entry includes a SHA-256 hash chain
    for integrity verification. ISO 27001 controls 12.4.1-12.4.3.
    """
    __tablename__ = "audit_logs"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    tenant_id = Column(GUID(), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # WHO
    actor_id = Column(GUID(), nullable=True)
    actor_email = Column(String, nullable=True)
    actor_ip = Column(String, nullable=True)
    actor_ua = Column(String, nullable=True)

    # WHAT
    event_type = Column(String, nullable=False)
    event_category = Column(String, nullable=False)
    action = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="info")

    # WHERE
    resource_type = Column(String, nullable=True)
    resource_id = Column(String, nullable=True)
    endpoint = Column(String, nullable=True)

    # DETAILS
    metadata_ = Column("metadata", JSONType(), nullable=True, default=dict)
    request_id = Column(GUID(), nullable=True)

    # TAMPER EVIDENCE
    prev_hash = Column(String, nullable=True)
    integrity_hash = Column(String, nullable=False)

    __table_args__ = (
        Index("idx_audit_tenant_time", "tenant_id", "timestamp"),
        Index("idx_audit_event_type", "tenant_id", "event_type"),
        Index("idx_audit_actor", "tenant_id", "actor_id"),
        Index("idx_audit_resource", "tenant_id", "resource_type", "resource_id"),
        Index("idx_audit_integrity", "tenant_id", "id", "integrity_hash"),
    )


class InviteModel(Base):
    """Pending user invitations."""
    __tablename__ = "invites"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False)
    email = Column(String, nullable=False)
    role_id = Column(GUID(), ForeignKey("roles.id"), nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(GUID(), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        # Ensure only one active invite per email per tenant
        Index("ix_invites_tenant_email", "tenant_id", "email", unique=True,
              postgresql_where=(revoked_at.is_(None) & accepted_at.is_(None))),
        Index("ix_invites_token_hash", "token_hash", unique=True),
        Index("ix_invites_tenant_created", "tenant_id", "created_at"),
    )


class PasswordResetTokenModel(Base):
    """Time-limited tokens for password reset flow."""
    __tablename__ = "password_reset_tokens"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_password_reset_tokens_user_id", "user_id"),
    )


class SupplierFacilityModel(Base):
    """Supplier-operated facilities for onboarding and FSMA scoping."""

    __tablename__ = "supplier_facilities"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False)
    supplier_user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    street = Column(String, nullable=False)
    city = Column(String, nullable=False)
    state = Column(String, nullable=False)
    postal_code = Column(String, nullable=False)
    fda_registration_number = Column(String, nullable=True)
    roles = Column(JSONType(), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_supplier_facilities_tenant", "tenant_id"),
        Index("ix_supplier_facilities_user", "supplier_user_id"),
    )


class SupplierFacilityFTLCategoryModel(Base):
    """FTL category assignments scoped to supplier facilities."""

    __tablename__ = "supplier_facility_ftl_categories"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False)
    facility_id = Column(GUID(), ForeignKey("supplier_facilities.id"), nullable=False)
    category_id = Column(String, nullable=False)
    category_name = Column(String, nullable=False)
    required_ctes = Column(JSONType(), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("facility_id", "category_id", name="uq_supplier_facility_ftl_category"),
        Index("ix_supplier_ftl_categories_tenant", "tenant_id"),
        Index("ix_supplier_ftl_categories_facility", "facility_id"),
    )


class SupplierTraceabilityLotModel(Base):
    """Supplier-managed traceability lots (TLCs)."""

    __tablename__ = "supplier_traceability_lots"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False)
    supplier_user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    facility_id = Column(GUID(), ForeignKey("supplier_facilities.id"), nullable=False)
    tlc_code = Column(String, nullable=False)
    product_description = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "tlc_code", name="uq_supplier_tlc_per_tenant"),
        Index("ix_supplier_tlcs_tenant", "tenant_id"),
        Index("ix_supplier_tlcs_supplier", "supplier_user_id"),
        Index("ix_supplier_tlcs_facility", "facility_id"),
    )


class SupplierCTEEventModel(Base):
    """Immutable CTE event log with hash-on-write and Merkle chaining."""

    __tablename__ = "supplier_cte_events"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False)
    supplier_user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    facility_id = Column(GUID(), ForeignKey("supplier_facilities.id"), nullable=False)
    lot_id = Column(GUID(), ForeignKey("supplier_traceability_lots.id"), nullable=False)
    cte_type = Column(String, nullable=False)
    event_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    kde_data = Column(JSONType(), nullable=False, default=dict)
    payload_sha256 = Column(String, nullable=False)
    merkle_prev_hash = Column(String, nullable=True)
    merkle_hash = Column(String, nullable=False)
    sequence_number = Column(BigInteger, nullable=False)
    obligation_ids = Column(JSONType(), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "sequence_number", name="uq_supplier_cte_events_tenant_sequence"),
        Index("ix_supplier_cte_events_tenant", "tenant_id"),
        Index("ix_supplier_cte_events_facility", "facility_id"),
        Index("ix_supplier_cte_events_lot", "lot_id"),
    )


class SupplierFunnelEventModel(Base):
    """Lightweight onboarding funnel analytics events."""

    __tablename__ = "supplier_funnel_events"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id"), nullable=False)
    supplier_user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    facility_id = Column(GUID(), ForeignKey("supplier_facilities.id"), nullable=True)
    event_name = Column(String, nullable=False)
    step = Column(String, nullable=True)
    status = Column(String, nullable=True)
    metadata_ = Column("metadata", JSONType(), nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_supplier_funnel_events_tenant", "tenant_id"),
        Index("ix_supplier_funnel_events_user", "supplier_user_id"),
        Index("ix_supplier_funnel_events_event", "event_name"),
        Index("ix_supplier_funnel_events_created", "created_at"),
    )


class ReviewItemModel(Base):
    """Database model for review queue items with tenant isolation."""

    __tablename__ = "review_items"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=True)
    doc_hash = Column(String, nullable=False)
    text_raw = Column(Text, nullable=False)
    extraction = Column(JSONType(), nullable=False)
    provenance = Column(JSONType(), nullable=True)
    embedding = Column(JSONType(), nullable=True)
    confidence_score = Column(Float, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    reviewer_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "doc_hash", "text_raw", name="review_items_unique_content"),
        Index("ix_review_items_status_created", "status", "created_at"),
        Index("ix_review_items_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return (
            "ReviewItemModel(id={id!s}, tenant_id={tenant_id!s}, status={status!s}, "
            "confidence_score={score!r})"
        ).format(
            id=self.id,
            tenant_id=self.tenant_id,
            status=self.status,
            score=self.confidence_score,
        )

class SessionModel(Base):
    """Stateful session tracking for refresh token rotation."""
    __tablename__ = "sessions"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    refresh_token_hash = Column(String, nullable=False, unique=True)
    family_id = Column(GUID(), nullable=False)
    is_revoked = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_refresh_token_hash", "refresh_token_hash"),
        Index("ix_sessions_family_id", "family_id"),
    )

