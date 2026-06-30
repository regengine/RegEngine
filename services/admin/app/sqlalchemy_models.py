"""SQLAlchemy ORM models for admin service data persistence."""

from __future__ import annotations

import uuid as uuid_module

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import CHAR, JSON, TypeDecorator

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

    __table_args__ = (Index("ix_tenants_slug", "slug"),)


class UserModel(Base):
    """Global user identity."""

    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    global_status = Column(String, nullable=False, default="active", server_default="active")
    email = Column(String, nullable=False, unique=True)
    # Legacy plaintext TOTP seed — preserved for backward compat during the
    # encryption migration (#1376). New enrollments write mfa_secret_ciphertext;
    # the plaintext column is read only when the ciphertext column is NULL.
    mfa_secret = Column(String, nullable=True)
    # Fernet-encrypted TOTP seed — primary source once MFA_ENCRYPTION_KEY is set.
    mfa_secret_ciphertext = Column(String, nullable=True)
    # Monotonic counter bumped on logout-all and account-security invalidation to reject
    # outstanding JWTs (#1349, #1375). Access tokens embed the value at mint
    # time; get_current_user rejects tokens whose claim no longer matches.
    token_version = Column(Integer, nullable=False, default=0, server_default="0")
    is_sysadmin = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="active")  # active, locked, invited
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_users_email", "email"),)


class UserEmailModel(Base):
    """Verified and pending email addresses attached to a global user."""

    __tablename__ = "user_emails"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    email = Column(String, nullable=False)
    email_fingerprint = Column(String, nullable=True)
    is_verified = Column(Boolean, nullable=False, default=False, server_default="false")

    __table_args__ = (
        Index("ix_user_emails_user_id", "user_id"),
        Index("ix_user_emails_email_fingerprint", "email_fingerprint", unique=True),
        Index("ix_user_emails_user_verified", "user_id", "is_verified"),
        Index("uq_user_emails_email_lower", func.lower(email), unique=True),
    )


class OrganizationModel(Base):
    """Tenant container for the high-assurance passwordless auth model."""

    __tablename__ = "organizations"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    name = Column(String, nullable=False)
    domain_name = Column(String, nullable=True)
    domain_verified = Column(Boolean, nullable=False, default=False, server_default="false")
    enforced_auth_policy = Column(
        Enum(
            "standard",
            "sso_only",
            name="organization_auth_policy",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        default="standard",
        server_default="standard",
    )

    __table_args__ = (
        Index("ix_organizations_name", "name"),
        Index("ix_organizations_domain_name", "domain_name", unique=True),
    )


class OrganizationMembershipModel(Base):
    """User-to-organization membership selected into authenticated sessions."""

    __tablename__ = "organization_memberships"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(GUID(), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "organization_id", name="uq_organization_memberships_user_org"),
        Index("ix_organization_memberships_user_id", "user_id"),
        Index("ix_organization_memberships_organization_id", "organization_id"),
    )


class AuthChallengeModel(Base):
    """Ephemeral OTP challenge state for email-code authentication."""

    __tablename__ = "auth_challenges"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    purpose = Column(
        Enum(
            "sign_in",
            "accept_invite",
            "step_up",
            name="auth_challenge_purpose",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    email_fingerprint = Column(String, nullable=False)
    code_digest = Column(String, nullable=False)
    browser_binding_hash = Column(String, nullable=False)
    status = Column(
        Enum(
            "queued",
            "pending",
            "consumed",
            "locked",
            "expired",
            name="auth_challenge_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
        default="queued",
        server_default="queued",
    )
    failed_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_auth_challenges_expires_at", "expires_at"),
        Index("ix_auth_challenges_status_expires_at", "status", "expires_at"),
        Index("ix_auth_challenges_email_purpose_status", "email_fingerprint", "purpose", "status"),
        Index("ix_auth_challenges_browser_binding_hash", "browser_binding_hash"),
    )


class WebAuthnCredentialModel(Base):
    """Stored public-key credentials for phishing-resistant passkey auth."""

    __tablename__ = "webauthn_credentials"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    credential_id = Column(String, nullable=False)
    public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_webauthn_credentials_user_id", "user_id"),
        Index("ix_webauthn_credentials_credential_id", "credential_id", unique=True),
    )


class WebAuthnChallengeModel(Base):
    """Short-lived WebAuthn registration/authentication challenge state."""

    __tablename__ = "webauthn_challenges"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    challenge = Column(String, nullable=False)
    purpose = Column(
        Enum(
            "registration",
            "authentication",
            name="webauthn_challenge_purpose",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        nullable=False,
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_webauthn_challenges_user_purpose", "user_id", "purpose"),
        Index("ix_webauthn_challenges_challenge", "challenge", unique=True),
        Index("ix_webauthn_challenges_expires_at", "expires_at"),
    )


class RoleModel(Base):
    """RBAC Roles (System or Custom)."""

    __tablename__ = "roles"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=True)  # Null = System Role
    name = Column(String, nullable=False)
    permissions = Column(JSONType(), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_roles_tenant", "tenant_id"),)


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


class MFARecoveryCodeModel(Base):
    """One-time-use recovery codes for MFA account recovery."""

    __tablename__ = "admin_mfa_recovery_codes"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    code_hash = Column(String, nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_mfa_recovery_codes_user", "user_id"),)


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
    # Contiguous per-tenant chain position (#2513). Nullable for legacy
    # rows written before the backfill migration; new rows always set it
    # under the per-tenant advisory lock. UNIQUE (tenant_id, sequence_num)
    # surfaces a forked chain as an IntegrityError instead of silent
    # duplicate sequences, and lets verify_chain detect a removed middle
    # row via a sequence gap.
    sequence_num = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=True)

    __table_args__ = (
        Index("idx_audit_tenant_time", "tenant_id", "timestamp"),
        Index("idx_audit_event_type", "tenant_id", "event_type"),
        Index("idx_audit_actor", "tenant_id", "actor_id"),
        Index("idx_audit_resource", "tenant_id", "resource_type", "resource_id"),
        Index("idx_audit_integrity", "tenant_id", "id", "integrity_hash"),
        UniqueConstraint("tenant_id", "sequence_num", name="uq_audit_tenant_sequence"),
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
        Index(
            "ix_invites_tenant_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=(revoked_at.is_(None) & accepted_at.is_(None)),
        ),
        Index("ix_invites_token_hash", "token_hash", unique=True),
        Index("ix_invites_tenant_created", "tenant_id", "created_at"),
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
    """Database model for review queue items with tenant isolation.

    tenant_id is NOT NULL in the Alembic migration chain (fix for #1389) -- rows
    without a tenant would otherwise leak across every tenant in
    ``list_hallucinations`` when the caller's API key has no tenant
    binding.
    """

    __tablename__ = "review_items"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), nullable=False)
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
            "ReviewItemModel(id={id!s}, tenant_id={tenant_id!s}, status={status!s}, confidence_score={score!r})"
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
    active_membership_id = Column(GUID(), ForeignKey("organization_memberships.id"), nullable=True)
    token_hash = Column(String, nullable=True)
    auth_method = Column(String, nullable=False, default="email_otp", server_default="email_otp")
    authenticated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    refresh_token_hash = Column(String, nullable=False, unique=True)
    family_id = Column(GUID(), nullable=False)
    is_revoked = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)

    __table_args__ = (
        CheckConstraint("auth_method IN ('email_otp', 'webauthn', 'sso')", name="ck_sessions_auth_method_values"),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_active_membership_id", "active_membership_id"),
        Index("ix_sessions_token_hash", "token_hash", unique=True),
        Index("ix_sessions_auth_method", "auth_method"),
        Index("ix_sessions_expires_at", "expires_at"),
        Index("ix_sessions_refresh_token_hash", "refresh_token_hash"),
        Index("ix_sessions_family_id", "family_id"),
    )
