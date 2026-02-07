"""SQLAlchemy ORM models for admin service data persistence."""

from __future__ import annotations

import uuid as uuid_module

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
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

    id = Column(BigInteger, primary_key=True, autoincrement=True)
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

class VerticalProjectModel(Base):
    """
    Represents a specific compliance project within a vertical (e.g. A specific Clinic).
    """
    __tablename__ = "vertical_projects"
    
    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=False)
    name = Column(String, nullable=False)
    vertical = Column(String, nullable=False) # e.g. "healthcare"
    vertical_metadata = Column(JSONType(), nullable=False, default=dict)
    status = Column(String, nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(GUID(), nullable=True)
    
    __table_args__ = (
        Index("ix_vertical_projects_tenant", "tenant_id"),
    )

class VerticalRuleInstanceModel(Base):
    """
    A specific instance of a rule derived from a RulePack active for a project.
    """
    __tablename__ = "vertical_rule_instances"
    
    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    project_id = Column(GUID(), ForeignKey("vertical_projects.id"), nullable=False)
    rule_id = Column(String, nullable=False) # e.g. "CLIN-01"
    status = Column(String, nullable=False, default="gray") # green, yellow, red, gray
    evidence_ids = Column(JSONType(), nullable=False, default=list)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("ix_rule_instances_project", "project_id"),
        UniqueConstraint("project_id", "rule_id", name="unique_project_rule"),
    )


class EvidenceLogModel(Base):
    """
    Immutable Evidence Vault (Constitution 2.1).
    Stores proof of compliance (hashes, document refs) that cannot be altered.
    """
    __tablename__ = "evidence_logs"
    
    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=False)
    project_id = Column(GUID(), nullable=False)
    rule_id = Column(String, nullable=False)
    evidence_type = Column(String, nullable=False) # e.g. "document", "approval", "manual_check"
    data = Column(JSONType(), nullable=False) # Context: file path, reviewer comment, etc.
    content_hash = Column(String, nullable=False) # SHA-256 of the data (or the document itself)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(GUID(), nullable=True)
    
    __table_args__ = (
        Index("ix_evidence_project_rule", "project_id", "rule_id"),
        Index("ix_evidence_hash", "content_hash"), # for specific lookups
    )
