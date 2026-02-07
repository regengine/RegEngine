"""
Production Compliance OS (PCOS) Domain Models

SQLAlchemy ORM models and Pydantic schemas for the Production Compliance OS
add-on module. Designed for small film/TV production companies in California/LA.

Tables prefixed with 'pcos_' to isolate from core RegEngine tables.
"""

from __future__ import annotations

import uuid as uuid_module
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, Time, func, ARRAY, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

# Import base and utilities from existing admin models
from .sqlalchemy_models import Base, GUID, JSONType


# =============================================================================
# ENUMS (Python representations of PostgreSQL enums)
# =============================================================================

class LocationType(str, Enum):
    """Types of filming locations."""
    CERTIFIED_STUDIO = "certified_studio"
    PRIVATE_PROPERTY = "private_property"
    RESIDENTIAL = "residential"
    PUBLIC_ROW = "public_row"


class ClassificationType(str, Enum):
    """Worker classification types."""
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"


class TaskStatus(str, Enum):
    """Status of compliance tasks."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class GateState(str, Enum):
    """Project gate states for go/no-go decisions."""
    DRAFT = "draft"
    READY_FOR_REVIEW = "ready_for_review"
    GREENLIT = "greenlit"
    IN_PRODUCTION = "in_production"
    WRAP = "wrap"
    ARCHIVED = "archived"


class EntityType(str, Enum):
    """Legal entity types."""
    SOLE_PROPRIETOR = "sole_proprietor"
    LLC_SINGLE_MEMBER = "llc_single_member"
    LLC_MULTI_MEMBER = "llc_multi_member"
    S_CORP = "s_corp"
    C_CORP = "c_corp"
    PARTNERSHIP = "partnership"


class OwnerPayMode(str, Enum):
    """Owner compensation methods."""
    DRAW = "draw"
    PAYROLL = "payroll"


class RegistrationType(str, Enum):
    """Types of business registrations."""
    SOS = "sos"  # Secretary of State
    FTB = "ftb"  # Franchise Tax Board
    BTRC = "btrc"  # LA Business Tax Registration Certificate
    DBA_FBN = "dba_fbn"  # DBA / Fictitious Business Name
    EDD = "edd"  # Employment Development Department
    DIR = "dir"  # Department of Industrial Relations


class InsuranceType(str, Enum):
    """Types of insurance policies."""
    GENERAL_LIABILITY = "general_liability"
    WORKERS_COMP = "workers_comp"
    ERRORS_OMISSIONS = "errors_omissions"
    EQUIPMENT = "equipment"
    AUTO = "auto"
    UMBRELLA = "umbrella"


class EvidenceType(str, Enum):
    """Types of evidence documents."""
    COI = "coi"
    PERMIT_APPROVED = "permit_approved"
    CLASSIFICATION_MEMO_SIGNED = "classification_memo_signed"
    WORKERS_COMP_POLICY = "workers_comp_policy"
    IIPP_POLICY = "iipp_policy"
    WVPP_POLICY = "wvpp_policy"
    W9 = "w9"
    I9 = "i9"
    W4 = "w4"
    VENDOR_COI = "vendor_coi"
    MINOR_WORK_PERMIT = "minor_work_permit"
    SIGNED_CONTRACT = "signed_contract"
    LOCATION_RELEASE = "location_release"
    TALENT_RELEASE = "talent_release"
    PAYSTUB = "paystub"
    TRAINING_RECORD = "training_record"
    OTHER = "other"


class ProjectType(str, Enum):
    """Types of production projects."""
    COMMERCIAL = "commercial"
    NARRATIVE_FEATURE = "narrative_feature"
    NARRATIVE_SHORT = "narrative_short"
    DOCUMENTARY = "documentary"
    MUSIC_VIDEO = "music_video"
    BRANDED_CONTENT = "branded_content"
    STILL_PHOTO = "still_photo"
    OTHER = "other"


class Jurisdiction(str, Enum):
    """Geographic jurisdictions for compliance."""
    LA_CITY = "la_city"
    LA_COUNTY = "la_county"
    CA_OTHER = "ca_other"
    OUT_OF_STATE = "out_of_state"


# =============================================================================
# SQLAlchemy ORM Models
# =============================================================================

class PCOSCompanyModel(Base):
    """Company profile for production company."""
    __tablename__ = "pcos_companies"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Legal entity info
    legal_name = Column(String(255), nullable=False)
    entity_type = Column(String(50), nullable=False)
    ein = Column(String(20))  # Encrypted at app layer
    sos_entity_number = Column(String(50))

    # Legal address
    legal_address_line1 = Column(String(255))
    legal_address_line2 = Column(String(255))
    legal_address_city = Column(String(100))
    legal_address_state = Column(String(2), default="CA")
    legal_address_zip = Column(String(10))

    # Mailing address
    mailing_address_line1 = Column(String(255))
    mailing_address_line2 = Column(String(255))
    mailing_address_city = Column(String(100))
    mailing_address_state = Column(String(2))
    mailing_address_zip = Column(String(10))

    # LA presence
    has_la_city_presence = Column(Boolean, nullable=False, default=False)
    la_business_address_line1 = Column(String(255))
    la_business_address_city = Column(String(100))
    la_business_address_zip = Column(String(10))

    # Owner compensation
    owner_pay_mode = Column(String(20))
    owner_pay_cpa_approved = Column(Boolean, nullable=False, default=False)
    owner_pay_cpa_approved_date = Column(Date)

    # Payroll provider config
    payroll_provider_config = Column(JSONType(), nullable=False, default=dict)

    # Metadata
    status = Column(String(50), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(GUID(), ForeignKey("users.id"))
    updated_by = Column(GUID(), ForeignKey("users.id"))

    # Relationships
    registrations = relationship("PCOSCompanyRegistrationModel", back_populates="company", cascade="all, delete-orphan")
    insurance_policies = relationship("PCOSInsurancePolicyModel", back_populates="company", cascade="all, delete-orphan")
    safety_policies = relationship("PCOSSafetyPolicyModel", back_populates="company", cascade="all, delete-orphan")
    projects = relationship("PCOSProjectModel", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_pcos_companies_tenant", "tenant_id"),
        Index("idx_pcos_companies_status", "status"),
    )


class PCOSCompanyRegistrationModel(Base):
    """Company registration records (SOS, FTB, BTRC, DBA)."""
    __tablename__ = "pcos_company_registrations"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(GUID(), ForeignKey("pcos_companies.id", ondelete="CASCADE"), nullable=False)

    registration_type = Column(String(20), nullable=False)
    registration_number = Column(String(100))
    registration_name = Column(String(255))  # For DBA/FBN
    jurisdiction = Column(String(100))

    issue_date = Column(Date)
    expiration_date = Column(Date)
    renewal_date = Column(Date)

    status = Column(String(50), nullable=False, default="pending")
    evidence_id = Column(GUID())

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    company = relationship("PCOSCompanyModel", back_populates="registrations")

    __table_args__ = (
        Index("idx_pcos_registrations_tenant", "tenant_id"),
        Index("idx_pcos_registrations_company", "company_id"),
        Index("idx_pcos_registrations_expiry", "expiration_date"),
    )


class PCOSInsurancePolicyModel(Base):
    """Insurance policy records."""
    __tablename__ = "pcos_insurance_policies"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(GUID(), ForeignKey("pcos_companies.id", ondelete="CASCADE"), nullable=False)

    policy_type = Column(String(30), nullable=False)
    carrier_name = Column(String(255))
    policy_number = Column(String(100))

    coverage_amount = Column(Numeric(15, 2))
    deductible_amount = Column(Numeric(15, 2))

    effective_date = Column(Date)
    expiration_date = Column(Date, nullable=False)

    is_required = Column(Boolean, nullable=False, default=False)
    status = Column(String(50), nullable=False, default="active")
    evidence_id = Column(GUID())

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    company = relationship("PCOSCompanyModel", back_populates="insurance_policies")

    __table_args__ = (
        Index("idx_pcos_insurance_tenant", "tenant_id"),
        Index("idx_pcos_insurance_company", "company_id"),
        Index("idx_pcos_insurance_expiry", "expiration_date"),
    )


class PCOSSafetyPolicyModel(Base):
    """Safety policy records (IIPP, WVPP)."""
    __tablename__ = "pcos_safety_policies"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(GUID(), ForeignKey("pcos_companies.id", ondelete="CASCADE"), nullable=False)

    policy_type = Column(String(50), nullable=False)
    policy_name = Column(String(255))

    effective_date = Column(Date)
    last_review_date = Column(Date)
    next_review_date = Column(Date)

    is_uploaded = Column(Boolean, nullable=False, default=False)
    evidence_id = Column(GUID())

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    company = relationship("PCOSCompanyModel", back_populates="safety_policies")

    __table_args__ = (
        Index("idx_pcos_safety_tenant", "tenant_id"),
        Index("idx_pcos_safety_company", "company_id"),
    )


class PCOSProjectModel(Base):
    """Production project."""
    __tablename__ = "pcos_projects"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(GUID(), ForeignKey("pcos_companies.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    code = Column(String(50))
    project_type = Column(String(30), nullable=False)

    is_commercial = Column(Boolean, nullable=False, default=False)
    client_name = Column(String(255))

    start_date = Column(Date)
    end_date = Column(Date)
    first_shoot_date = Column(Date)

    union_status = Column(String(50), default="non_union")
    minor_involved = Column(Boolean, nullable=False, default=False)

    # Gate state machine
    gate_state = Column(String(30), nullable=False, default="draft")
    gate_state_changed_at = Column(DateTime(timezone=True))
    gate_state_changed_by = Column(GUID(), ForeignKey("users.id"))

    # Risk assessment
    risk_score = Column(Integer, default=0)
    blocking_tasks_count = Column(Integer, default=0)

    notes = Column(Text)
    metadata_ = Column("metadata", JSONType(), nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(GUID(), ForeignKey("users.id"))
    updated_by = Column(GUID(), ForeignKey("users.id"))

    # Relationships
    company = relationship("PCOSCompanyModel", back_populates="projects")
    locations = relationship("PCOSLocationModel", back_populates="project", cascade="all, delete-orphan")
    engagements = relationship("PCOSEngagementModel", back_populates="project", cascade="all, delete-orphan")
    permit_packets = relationship("PCOSPermitPacketModel", back_populates="project", cascade="all, delete-orphan")
    tax_credit_applications = relationship("PCOSTaxCreditApplicationModel", back_populates="project", cascade="all, delete-orphan")
    generated_forms = relationship("PCOSGeneratedFormModel", back_populates="project", cascade="all, delete-orphan")
    compliance_snapshots = relationship("PCOSComplianceSnapshotModel", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_pcos_projects_tenant", "tenant_id"),
        Index("idx_pcos_projects_company", "company_id"),
        Index("idx_pcos_projects_gate", "gate_state"),
        Index("idx_pcos_projects_dates", "first_shoot_date", "start_date"),
    )


class PCOSLocationModel(Base):
    """Filming location."""
    __tablename__ = "pcos_locations"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"), nullable=False)

    name = Column(String(255), nullable=False)
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(2), default="CA")
    zip = Column(String(10))

    jurisdiction = Column(String(20), nullable=False)
    location_type = Column(String(30), nullable=False)

    # Filming footprint
    estimated_crew_size = Column(Integer)
    parking_spaces_needed = Column(Integer)
    filming_hours_start = Column(Time)
    filming_hours_end = Column(Time)
    has_generator = Column(Boolean, default=False)
    has_special_effects = Column(Boolean, default=False)
    noise_level = Column(String(20))

    # Permit tracking
    permit_required = Column(Boolean)
    permit_packet_id = Column(GUID())

    shoot_dates = Column(ARRAY(Date))

    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("PCOSProjectModel", back_populates="locations")

    __table_args__ = (
        Index("idx_pcos_locations_tenant", "tenant_id"),
        Index("idx_pcos_locations_project", "project_id"),
        Index("idx_pcos_locations_type", "location_type"),
    )


class PCOSPermitPacketModel(Base):
    """FilmLA permit tracking."""
    __tablename__ = "pcos_permit_packets"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"), nullable=False)
    location_id = Column(GUID(), ForeignKey("pcos_locations.id", ondelete="SET NULL"))

    permit_authority = Column(String(100), nullable=False, default="filmla")
    application_number = Column(String(100))

    submitted_at = Column(DateTime(timezone=True))
    approved_at = Column(DateTime(timezone=True))
    denied_at = Column(DateTime(timezone=True))
    denial_reason = Column(Text)

    permit_number = Column(String(100))
    permit_valid_from = Column(Date)
    permit_valid_to = Column(Date)

    status = Column(String(50), nullable=False, default="not_started")

    coi_evidence_id = Column(GUID())
    permit_evidence_id = Column(GUID())

    metadata_ = Column("metadata", JSONType(), nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("PCOSProjectModel", back_populates="permit_packets")

    __table_args__ = (
        Index("idx_pcos_permits_tenant", "tenant_id"),
        Index("idx_pcos_permits_project", "project_id"),
        Index("idx_pcos_permits_status", "status"),
    )


class PCOSPersonModel(Base):
    """People registry (crew/talent)."""
    __tablename__ = "pcos_people"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255))
    phone = Column(String(50))

    # Legal identification (encrypted at app layer)
    ssn_last_four = Column(String(4))
    date_of_birth = Column(Date)

    # Address
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(2))
    zip = Column(String(10))

    # Default classification preference
    preferred_classification = Column(String(20))

    # Vendor/contractor info
    is_loan_out = Column(Boolean, default=False)
    loan_out_company_name = Column(String(255))
    loan_out_ein = Column(String(20))

    # Emergency contact
    emergency_contact_name = Column(String(255))
    emergency_contact_phone = Column(String(50))
    emergency_contact_relation = Column(String(100))

    notes = Column(Text)
    status = Column(String(50), nullable=False, default="active")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    engagements = relationship("PCOSEngagementModel", back_populates="person", cascade="all, delete-orphan")
    visa_status = relationship("PCOSPersonVisaStatusModel", back_populates="person", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_pcos_people_tenant", "tenant_id"),
        Index("idx_pcos_people_name", "last_name", "first_name"),
        Index("idx_pcos_people_email", "email"),
    )


class PCOSEngagementModel(Base):
    """Engagement (person <-> project assignment)."""
    __tablename__ = "pcos_engagements"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"), nullable=False)
    person_id = Column(GUID(), ForeignKey("pcos_people.id", ondelete="CASCADE"), nullable=False)

    role_title = Column(String(255), nullable=False)
    department = Column(String(100))

    classification = Column(String(20), nullable=False)

    # Pay terms
    pay_rate = Column(Numeric(10, 2), nullable=False)
    pay_type = Column(String(50), nullable=False)
    overtime_eligible = Column(Boolean, nullable=False, default=True)

    # Work dates
    start_date = Column(Date)
    end_date = Column(Date)
    guaranteed_days = Column(Integer)

    # Classification documentation
    classification_memo_signed = Column(Boolean, nullable=False, default=False)
    classification_memo_date = Column(Date)

    # Required documents status
    w9_received = Column(Boolean, default=False)
    i9_received = Column(Boolean, default=False)
    w4_received = Column(Boolean, default=False)
    deal_memo_signed = Column(Boolean, default=False)

    status = Column(String(50), nullable=False, default="active")

    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    project = relationship("PCOSProjectModel", back_populates="engagements")
    person = relationship("PCOSPersonModel", back_populates="engagements")
    timecards = relationship("PCOSTimecardModel", back_populates="engagement", cascade="all, delete-orphan")
    classification_analyses = relationship("PCOSClassificationAnalysisModel", back_populates="engagement", cascade="all, delete-orphan")
    documents = relationship("PCOSEngagementDocumentModel", back_populates="engagement", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_pcos_engagements_tenant", "tenant_id"),
        Index("idx_pcos_engagements_project", "project_id"),
        Index("idx_pcos_engagements_person", "person_id"),
        Index("idx_pcos_engagements_classification", "classification"),
    )


class PCOSTimecardModel(Base):
    """Timecard for daily work hours."""
    __tablename__ = "pcos_timecards"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    engagement_id = Column(GUID(), ForeignKey("pcos_engagements.id", ondelete="CASCADE"), nullable=False)

    work_date = Column(Date, nullable=False)

    # Call/wrap times
    call_time = Column(Time)
    wrap_time = Column(Time)

    # Meal breaks
    meal_1_out = Column(Time)
    meal_1_in = Column(Time)
    meal_2_out = Column(Time)
    meal_2_in = Column(Time)

    # Calculated hours
    regular_hours = Column(Numeric(5, 2))
    overtime_hours = Column(Numeric(5, 2))
    double_time_hours = Column(Numeric(5, 2))
    meal_penalty_count = Column(Integer, default=0)

    # Validation
    jurisdiction = Column(String(20))
    wage_floor_met = Column(Boolean)
    wage_floor_rate = Column(Numeric(10, 2))

    # Approval workflow
    submitted_at = Column(DateTime(timezone=True))
    submitted_by = Column(GUID(), ForeignKey("users.id"))
    approved_at = Column(DateTime(timezone=True))
    approved_by = Column(GUID(), ForeignKey("users.id"))
    rejected_at = Column(DateTime(timezone=True))
    rejected_by = Column(GUID(), ForeignKey("users.id"))
    rejection_reason = Column(Text)

    status = Column(String(50), nullable=False, default="draft")

    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    engagement = relationship("PCOSEngagementModel", back_populates="timecards")

    __table_args__ = (
        Index("idx_pcos_timecards_tenant", "tenant_id"),
        Index("idx_pcos_timecards_engagement", "engagement_id"),
        Index("idx_pcos_timecards_date", "work_date"),
        Index("idx_pcos_timecards_status", "status"),
    )


class PCOSTaskModel(Base):
    """Compliance task."""
    __tablename__ = "pcos_tasks"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Link to domain object
    source_type = Column(String(50), nullable=False)
    source_id = Column(GUID(), nullable=False)

    # Task definition
    task_template_id = Column(String(100))
    task_type = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)

    # Assignment
    assigned_to = Column(GUID(), ForeignKey("users.id"))
    assigned_role = Column(String(100))

    # Dates
    due_date = Column(Date)
    reminder_sent_7d = Column(Boolean, default=False)
    reminder_sent_3d = Column(Boolean, default=False)
    reminder_sent_1d = Column(Boolean, default=False)

    # Status
    status = Column(String(20), nullable=False, default="pending")
    is_blocking = Column(Boolean, nullable=False, default=False)

    # Completion
    completed_at = Column(DateTime(timezone=True))
    completed_by = Column(GUID(), ForeignKey("users.id"))

    # Evidence requirement
    requires_evidence = Column(Boolean, default=False)
    required_evidence_types = Column(ARRAY(String))
    evidence_ids = Column(ARRAY(GUID()))

    # Rule that created this task
    rule_id = Column(String(100))
    rule_pack = Column(String(100), default="production_ca_la")

    notes = Column(Text)
    metadata_ = Column("metadata", JSONType(), nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    events = relationship("PCOSTaskEventModel", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_pcos_tasks_tenant", "tenant_id"),
        Index("idx_pcos_tasks_source", "source_type", "source_id"),
        Index("idx_pcos_tasks_status", "status"),
        Index("idx_pcos_tasks_due", "due_date"),
    )


class PCOSTaskEventModel(Base):
    """Task event audit trail."""
    __tablename__ = "pcos_task_events"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(GUID(), ForeignKey("pcos_tasks.id", ondelete="CASCADE"), nullable=False)

    event_type = Column(String(50), nullable=False)
    previous_value = Column(JSONType())
    new_value = Column(JSONType())

    actor_id = Column(GUID(), ForeignKey("users.id"))
    actor_type = Column(String(50), default="user")

    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    task = relationship("PCOSTaskModel", back_populates="events")

    __table_args__ = (
        Index("idx_pcos_task_events_tenant", "tenant_id"),
        Index("idx_pcos_task_events_task", "task_id"),
        Index("idx_pcos_task_events_created", "created_at"),
    )


class PCOSEvidenceModel(Base):
    """Evidence document in the evidence locker."""
    __tablename__ = "pcos_evidence"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Link to domain object
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(GUID(), nullable=False)

    # Document metadata
    evidence_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)

    # File storage
    file_name = Column(String(255))
    file_size_bytes = Column(Integer)
    mime_type = Column(String(100))
    s3_key = Column(Text, nullable=False)

    # Integrity
    sha256_hash = Column(String(64))

    # Validity period
    valid_from = Column(Date)
    valid_until = Column(Date)

    # E-sign tracking
    is_signed = Column(Boolean, default=False)
    signed_at = Column(DateTime(timezone=True))
    signer_name = Column(String(255))
    esign_envelope_id = Column(String(255))

    # Metadata
    uploaded_by = Column(GUID(), ForeignKey("users.id"))
    tags = Column(ARRAY(String))
    metadata_ = Column("metadata", JSONType(), nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("idx_pcos_evidence_tenant", "tenant_id"),
        Index("idx_pcos_evidence_entity", "entity_type", "entity_id"),
        Index("idx_pcos_evidence_type", "evidence_type"),
        Index("idx_pcos_evidence_validity", "valid_until"),
    )


class PCOSGateEvaluationModel(Base):
    """Gate evaluation snapshot."""
    __tablename__ = "pcos_gate_evaluations"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"), nullable=False)

    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())
    evaluated_by = Column(GUID(), ForeignKey("users.id"))
    trigger_type = Column(String(50))

    current_state = Column(String(30), nullable=False)
    target_state = Column(String(30))
    transition_allowed = Column(Boolean, nullable=False)

    blocking_tasks_count = Column(Integer, nullable=False, default=0)
    blocking_task_ids = Column(ARRAY(GUID()))

    missing_evidence = Column(ARRAY(String))
    risk_score = Column(Integer, nullable=False, default=0)

    reasons = Column(ARRAY(String))

    snapshot = Column(JSONType(), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_pcos_gate_evals_tenant", "tenant_id"),
        Index("idx_pcos_gate_evals_project", "project_id"),
        Index("idx_pcos_gate_evals_date", "evaluated_at"),
    )


class PCOSBudgetModel(Base):
    """Parsed budget from spreadsheet upload."""
    __tablename__ = "pcos_budgets"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"), nullable=False)

    # Source file
    source_file_name = Column(String(255), nullable=False)
    source_file_hash = Column(String(64))
    source_file_s3_key = Column(Text)

    # Parse metadata
    parsed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    parser_version = Column(String(20), default="1.0")
    sheet_name = Column(String(100))

    # Totals
    grand_total = Column(Numeric(15, 2), nullable=False)
    subtotal = Column(Numeric(15, 2), nullable=False)
    contingency_amount = Column(Numeric(15, 2), default=0)
    contingency_percent = Column(Numeric(5, 2), default=0)

    # Location/jurisdiction detected
    detected_location = Column(String(10))

    # Status
    status = Column(String(20), nullable=False, default="draft")
    is_active = Column(Boolean, nullable=False, default=True)

    # Compliance summary
    compliance_issue_count = Column(Integer, default=0)
    critical_issue_count = Column(Integer, default=0)
    risk_score = Column(Integer, default=0)

    # Metadata
    metadata_ = Column("metadata", JSONType(), nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(GUID(), ForeignKey("users.id"))

    # Relationships
    line_items = relationship("PCOSBudgetLineItemModel", back_populates="budget", cascade="all, delete-orphan")
    tax_credit_applications = relationship("PCOSTaxCreditApplicationModel", back_populates="budget")

    __table_args__ = (
        Index("idx_pcos_budgets_tenant", "tenant_id"),
        Index("idx_pcos_budgets_project", "project_id"),
    )


class PCOSBudgetLineItemModel(Base):
    """Parsed line item from budget spreadsheet."""
    __tablename__ = "pcos_budget_line_items"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    budget_id = Column(GUID(), ForeignKey("pcos_budgets.id", ondelete="CASCADE"), nullable=False)

    # Line item data
    row_number = Column(Integer, nullable=False)
    cost_code = Column(String(20))
    department = Column(String(100))
    description = Column(Text, nullable=False)

    # Financial
    rate = Column(Numeric(12, 2), default=0)
    quantity = Column(Numeric(10, 2), default=1)
    extension = Column(Numeric(15, 2), nullable=False)

    # Classification
    classification = Column(String(20))  # employee, contractor
    role_category = Column(String(50))  # principal, dp, gaffer, pa, etc.

    # Union detection
    is_union_covered = Column(Boolean, default=False)
    detected_union = Column(String(20))

    # Deal memo status
    deal_memo_status = Column(String(20))

    # Compliance flags
    compliance_flags = Column(ARRAY(String), default=list)

    # Raw data
    raw_row_data = Column(JSONType())

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    budget = relationship("PCOSBudgetModel", back_populates="line_items")
    rate_checks = relationship("PCOSUnionRateCheckModel", back_populates="line_item", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_pcos_budget_items_tenant", "tenant_id"),
        Index("idx_pcos_budget_items_budget", "budget_id"),
        Index("idx_pcos_budget_items_dept", "department"),
    )


class PCOSUnionRateCheckModel(Base):
    """Union rate validation result."""
    __tablename__ = "pcos_union_rate_checks"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Can link to budget line item OR engagement
    line_item_id = Column(GUID(), ForeignKey("pcos_budget_line_items.id", ondelete="CASCADE"))
    engagement_id = Column(GUID(), ForeignKey("pcos_engagements.id", ondelete="CASCADE"))

    # Union info
    union_code = Column(String(20), nullable=False)
    role_category = Column(String(50), nullable=False)

    # Rate comparison
    minimum_rate = Column(Numeric(10, 2), nullable=False)
    actual_rate = Column(Numeric(10, 2), nullable=False)
    is_compliant = Column(Boolean, nullable=False)
    shortfall_amount = Column(Numeric(10, 2), default=0)

    # Fringe
    fringe_percent_required = Column(Numeric(5, 2))
    fringe_amount_required = Column(Numeric(10, 2))

    # Provenance
    rate_table_version = Column(String(20), nullable=False)
    rate_table_effective_date = Column(Date)
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    notes = Column(Text)

    # Relationships
    line_item = relationship("PCOSBudgetLineItemModel", back_populates="rate_checks")

    __table_args__ = (
        Index("idx_pcos_rate_checks_tenant", "tenant_id"),
        Index("idx_pcos_rate_checks_line_item", "line_item_id"),
        Index("idx_pcos_rate_checks_engagement", "engagement_id"),
    )


class PCOSTaxCreditApplicationModel(Base):
    """Tax credit application tracking per project."""
    __tablename__ = "pcos_tax_credit_applications"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"), nullable=False)
    budget_id = Column(GUID(), ForeignKey("pcos_budgets.id", ondelete="SET NULL"))

    # Program identification
    program_code = Column(String(50), nullable=False)  # CA_FTC_4.0, GA_ENT, NY_FILM
    program_name = Column(String(255), nullable=False)
    program_year = Column(Integer, nullable=False)

    # Eligibility status
    eligibility_status = Column(String(50), nullable=False, default="pending")
    eligibility_score = Column(Numeric(5, 2))

    # Thresholds and requirements
    min_spend_threshold = Column(Numeric(15, 2))
    actual_qualified_spend = Column(Numeric(15, 2))
    qualified_spend_pct = Column(Numeric(5, 2))

    # Credit calculation
    base_credit_rate = Column(Numeric(5, 2))
    uplift_rate = Column(Numeric(5, 2))
    total_credit_rate = Column(Numeric(5, 2))
    estimated_credit_amount = Column(Numeric(15, 2))

    # Requirements checklist
    requirements_met = Column(JSONB, default=dict)
    requirements_notes = Column(Text)

    # Rule evaluation metadata
    rule_pack_version = Column(String(50))
    evaluated_at = Column(DateTime(timezone=True))
    evaluation_details = Column(JSONB)

    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(GUID(), ForeignKey("users.id"))

    # Relationships
    project = relationship("PCOSProjectModel", back_populates="tax_credit_applications")
    budget = relationship("PCOSBudgetModel", back_populates="tax_credit_applications")
    spend_categories = relationship("PCOSQualifiedSpendCategoryModel", back_populates="application", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_tax_credit_apps_tenant", "tenant_id"),
        Index("idx_tax_credit_apps_project", "project_id"),
        Index("idx_tax_credit_apps_program", "program_code", "program_year"),
    )


class PCOSQualifiedSpendCategoryModel(Base):
    """Breakdown of spend into qualified vs non-qualified categories."""
    __tablename__ = "pcos_qualified_spend_categories"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    application_id = Column(GUID(), ForeignKey("pcos_tax_credit_applications.id", ondelete="CASCADE"), nullable=False)

    # Category identification
    category_code = Column(String(100), nullable=False)
    category_name = Column(String(255), nullable=False)
    budget_department = Column(String(100))

    # Spend amounts
    total_spend = Column(Numeric(15, 2), nullable=False, default=0)
    qualified_spend = Column(Numeric(15, 2), nullable=False, default=0)
    non_qualified_spend = Column(Numeric(15, 2), nullable=False, default=0)

    # Qualification status
    qualification_status = Column(String(50), nullable=False, default="mixed")
    qualification_reason = Column(Text)

    # Rule details
    applicable_rules = Column(JSONB)
    exclusion_reason = Column(String(255))

    # Line item rollup
    line_item_count = Column(Integer, default=0)
    line_item_ids = Column(ARRAY(GUID()))

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    application = relationship("PCOSTaxCreditApplicationModel", back_populates="spend_categories")

    __table_args__ = (
        Index("idx_qualified_spend_tenant", "tenant_id"),
        Index("idx_qualified_spend_app", "application_id"),
    )


class PCOSTaxCreditRuleModel(Base):
    """Program-specific tax credit qualification rules."""
    __tablename__ = "pcos_tax_credit_rules"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)

    # Program scope
    program_code = Column(String(50), nullable=False)
    program_year = Column(Integer, nullable=False)
    rule_version = Column(String(20), nullable=False, default="1.0")

    # Rule definition
    rule_code = Column(String(100), nullable=False)
    rule_name = Column(String(255), nullable=False)
    rule_category = Column(String(100), nullable=False)

    # Rule logic
    rule_definition = Column(JSONB, nullable=False)

    # Documentation
    description = Column(Text)
    authority_reference = Column(String(255))
    effective_date = Column(Date)
    sunset_date = Column(Date)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("program_code", "program_year", "rule_code", name="uq_tax_rule_program_code"),
        Index("idx_tax_rules_program", "program_code", "program_year"),
    )


class PCOSFormTemplateModel(Base):
    """Form template definitions with field mappings."""
    __tablename__ = "pcos_form_templates"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)

    # Template identification
    template_code = Column(String(100), nullable=False, unique=True)
    template_name = Column(String(255), nullable=False)
    template_version = Column(String(20), nullable=False, default="1.0")

    # Form source
    form_authority = Column(String(100))
    form_url = Column(String(500))

    # Template type
    form_type = Column(String(50), nullable=False)
    jurisdiction = Column(String(20))

    # Field definitions
    field_mappings = Column(JSONB, nullable=False, default=list)

    # PDF template storage
    pdf_template_path = Column(String(500))
    pdf_template_hash = Column(String(64))

    # Metadata
    description = Column(Text)
    instructions = Column(Text)
    estimated_fill_time_minutes = Column(Integer)

    # Status
    is_active = Column(Boolean, nullable=False, default=True)
    requires_signature = Column(Boolean, nullable=False, default=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(GUID(), ForeignKey("users.id"))

    # Relationships
    generated_forms = relationship("PCOSGeneratedFormModel", back_populates="template")

    __table_args__ = (
        Index("idx_form_templates_code", "template_code"),
        Index("idx_form_templates_type", "form_type"),
    )


class PCOSGeneratedFormModel(Base):
    """Generated/filled PDF forms per project."""
    __tablename__ = "pcos_generated_forms"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(GUID(), ForeignKey("pcos_form_templates.id"), nullable=False)
    location_id = Column(GUID(), ForeignKey("pcos_locations.id", ondelete="SET NULL"))

    # Generation details
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    generated_by = Column(GUID(), ForeignKey("users.id"))

    # Source data snapshot
    source_data_snapshot = Column(JSONB, nullable=False, default=dict)

    # Generated PDF
    pdf_storage_path = Column(String(500))
    pdf_file_hash = Column(String(64))
    pdf_file_size_bytes = Column(Integer)

    # Status tracking
    status = Column(String(50), nullable=False, default="draft")
    submitted_at = Column(DateTime(timezone=True))
    approved_at = Column(DateTime(timezone=True))
    rejection_reason = Column(Text)

    # External reference
    external_reference = Column(String(100))

    # Signature tracking
    requires_signature = Column(Boolean, nullable=False, default=False)
    signature_status = Column(String(50), default="pending")
    signed_at = Column(DateTime(timezone=True))
    signed_by = Column(GUID(), ForeignKey("users.id"))

    notes = Column(Text)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    template = relationship("PCOSFormTemplateModel", back_populates="generated_forms")
    project = relationship("PCOSProjectModel", back_populates="generated_forms")
    location = relationship("PCOSLocationModel")

    __table_args__ = (
        Index("idx_generated_forms_tenant", "tenant_id"),
        Index("idx_generated_forms_project", "project_id"),
        Index("idx_generated_forms_status", "status"),
    )


class PCOSClassificationAnalysisModel(Base):
    """ABC Test classification analysis for engagements."""
    __tablename__ = "pcos_classification_analyses"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    engagement_id = Column(GUID(), ForeignKey("pcos_engagements.id", ondelete="CASCADE"), nullable=False)

    # Analysis metadata
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    analyzed_by = Column(GUID(), ForeignKey("users.id"))
    rule_version = Column(String(20), nullable=False, default="1.0")

    # Prong A: Free from control
    prong_a_passed = Column(Boolean)
    prong_a_score = Column(Integer)
    prong_a_factors = Column(JSONB, default=dict)
    prong_a_reasoning = Column(Text)

    # Prong B: Outside usual business
    prong_b_passed = Column(Boolean)
    prong_b_score = Column(Integer)
    prong_b_factors = Column(JSONB, default=dict)
    prong_b_reasoning = Column(Text)
    prong_b_questionnaire_completed = Column(Boolean, default=False)

    # Prong C: Independent trade
    prong_c_passed = Column(Boolean)
    prong_c_score = Column(Integer)
    prong_c_factors = Column(JSONB, default=dict)
    prong_c_reasoning = Column(Text)

    # Overall determination
    overall_result = Column(String(30), nullable=False)
    overall_score = Column(Integer, nullable=False)
    confidence_level = Column(String(20), nullable=False, default="medium")

    # Risk assessment
    risk_level = Column(String(20), nullable=False, default="medium")
    risk_factors = Column(JSONB, default=list)
    recommended_action = Column(String(100))

    # Exemption
    exemption_applicable = Column(Boolean, default=False)
    exemption_type = Column(String(100))
    exemption_reasoning = Column(Text)

    # Evidence
    supporting_evidence = Column(JSONB, default=list)
    notes = Column(Text)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    engagement = relationship("PCOSEngagementModel", back_populates="classification_analyses")
    questionnaire_responses = relationship("PCOSQuestionnaireResponseModel", back_populates="analysis", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_classification_tenant", "tenant_id"),
        Index("idx_classification_engagement", "engagement_id"),
        Index("idx_classification_result", "overall_result"),
    )


class PCOSQuestionnaireResponseModel(Base):
    """ABC Test questionnaire responses."""
    __tablename__ = "pcos_abc_questionnaire_responses"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    analysis_id = Column(GUID(), ForeignKey("pcos_classification_analyses.id", ondelete="CASCADE"), nullable=False)

    question_code = Column(String(50), nullable=False)
    question_text = Column(Text, nullable=False)
    question_category = Column(String(50), nullable=False)

    response_value = Column(String(50))
    response_details = Column(Text)
    response_weight = Column(Integer, default=1)

    supports_contractor = Column(Boolean)
    impact_score = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    analysis = relationship("PCOSClassificationAnalysisModel", back_populates="questionnaire_responses")

    __table_args__ = (
        Index("idx_questionnaire_analysis", "analysis_id"),
        Index("idx_questionnaire_tenant", "tenant_id"),
    )


class PCOSClassificationExemptionModel(Base):
    """AB5 exemption rules."""
    __tablename__ = "pcos_classification_exemptions"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)

    exemption_code = Column(String(50), nullable=False, unique=True)
    exemption_name = Column(String(255), nullable=False)
    exemption_category = Column(String(100), nullable=False)

    qualifying_criteria = Column(JSONB, nullable=False)

    description = Column(Text)
    legal_reference = Column(String(255))
    effective_date = Column(Date)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_exemptions_code", "exemption_code"),
        Index("idx_exemptions_category", "exemption_category"),
    )


class PCOSDocumentRequirementModel(Base):
    """Document requirements by engagement type."""
    __tablename__ = "pcos_document_requirements"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)

    requirement_code = Column(String(50), nullable=False, unique=True)
    requirement_name = Column(String(255), nullable=False)
    document_type = Column(String(100), nullable=False)

    applies_to_classification = Column(String(20))
    applies_to_union_status = Column(String(50))
    applies_to_minor = Column(Boolean, default=False)
    applies_to_visa_holder = Column(Boolean, default=False)

    description = Column(Text)
    legal_reference = Column(String(255))
    deadline_days_before_start = Column(Integer)
    deadline_type = Column(String(50), default="before_start")

    form_number = Column(String(50))
    issuing_authority = Column(String(100))
    template_id = Column(GUID(), ForeignKey("pcos_form_templates.id"))

    is_required = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_doc_requirements_type", "document_type"),
    )


class PCOSEngagementDocumentModel(Base):
    """Track document status per engagement."""
    __tablename__ = "pcos_engagement_documents"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    engagement_id = Column(GUID(), ForeignKey("pcos_engagements.id", ondelete="CASCADE"), nullable=False)
    requirement_id = Column(GUID(), ForeignKey("pcos_document_requirements.id"), nullable=False)

    status = Column(String(50), nullable=False, default="pending")

    requested_at = Column(DateTime(timezone=True))
    received_at = Column(DateTime(timezone=True))
    verified_at = Column(DateTime(timezone=True))
    verified_by = Column(GUID(), ForeignKey("users.id"))
    expires_at = Column(Date)

    evidence_id = Column(GUID(), ForeignKey("pcos_evidence.id"))
    file_name = Column(String(255))

    notes = Column(Text)
    waiver_reason = Column(Text)

    reminder_sent_at = Column(DateTime(timezone=True))
    reminder_count = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    engagement = relationship("PCOSEngagementModel", back_populates="documents")
    requirement = relationship("PCOSDocumentRequirementModel")

    __table_args__ = (
        Index("idx_engagement_docs_tenant", "tenant_id"),
        Index("idx_engagement_docs_engagement", "engagement_id"),
        Index("idx_engagement_docs_status", "status"),
        UniqueConstraint("engagement_id", "requirement_id", name="uq_engagement_doc"),
    )


class PCOSVisaCategoryModel(Base):
    """Visa types with processing times."""
    __tablename__ = "pcos_visa_categories"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)

    visa_code = Column(String(20), nullable=False, unique=True)
    visa_name = Column(String(255), nullable=False)
    visa_category = Column(String(50), nullable=False)

    work_authorized = Column(Boolean, nullable=False, default=True)
    employer_specific = Column(Boolean, nullable=False, default=False)
    duration_months = Column(Integer)
    renewable = Column(Boolean, default=True)

    standard_processing_days = Column(Integer)
    premium_processing_days = Column(Integer)
    premium_processing_available = Column(Boolean, default=False)

    requires_petition = Column(Boolean, default=True)
    requires_labor_certification = Column(Boolean, default=False)

    common_in_entertainment = Column(Boolean, default=False)
    notes = Column(Text)

    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_visa_categories_code", "visa_code"),
    )


class PCOSPersonVisaStatusModel(Base):
    """Visa status per person."""
    __tablename__ = "pcos_person_visa_status"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    person_id = Column(GUID(), ForeignKey("pcos_people.id", ondelete="CASCADE"), nullable=False)

    visa_category_id = Column(GUID(), ForeignKey("pcos_visa_categories.id"))
    visa_code = Column(String(20))

    status = Column(String(50), nullable=False, default="active")

    issue_date = Column(Date)
    expiration_date = Column(Date)
    last_entry_date = Column(Date)

    i94_number = Column(String(20))
    i94_expiration = Column(Date)

    ead_expiration = Column(Date)
    is_work_authorized = Column(Boolean, default=True)
    employer_restricted = Column(Boolean, default=False)
    restricted_to_employer = Column(String(255))

    evidence_id = Column(GUID(), ForeignKey("pcos_evidence.id"))
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    person = relationship("PCOSPersonModel", back_populates="visa_status")
    visa_category = relationship("PCOSVisaCategoryModel")

    __table_args__ = (
        Index("idx_person_visa_tenant", "tenant_id"),
        Index("idx_person_visa_person", "person_id"),
        Index("idx_person_visa_expiration", "expiration_date"),
    )


class PCOSRuleEvaluationModel(Base):
    """Rule evaluation records for provenance tracking."""
    __tablename__ = "pcos_rule_evaluations"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"), nullable=False)

    entity_type = Column(String(50), nullable=False)
    entity_id = Column(GUID(), nullable=False)

    rule_code = Column(String(100), nullable=False)
    rule_name = Column(String(255), nullable=False)
    rule_category = Column(String(100), nullable=False)
    rule_version = Column(String(20), nullable=False, default="1.0")

    result = Column(String(30), nullable=False)
    score = Column(Integer)
    severity = Column(String(20), default="medium")

    evaluation_input = Column(JSONB, nullable=False, default=dict)
    evaluation_output = Column(JSONB, nullable=False, default=dict)
    message = Column(Text)

    source_authorities = Column(JSONB, nullable=False, default=list)

    task_id = Column(GUID(), ForeignKey("pcos_tasks.id", ondelete="SET NULL"))
    finding_id = Column(GUID())

    evaluated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    evaluated_by = Column(GUID(), ForeignKey("users.id"))

    snapshot_id = Column(GUID())
    
    # Governance columns (per SCHEMA_CHANGE_POLICY.md invariants)
    analysis_run_id = Column(GUID(), ForeignKey("pcos_analysis_runs.id"))
    rule_version_id = Column(GUID())  # Reference to specific rule version
    fact_version_ids = Column(JSONB, default=list)  # Array of fact IDs used
    authority_ids = Column(JSONB, default=list)  # Array of authority IDs cited
    supersedes_id = Column(GUID(), ForeignKey("pcos_rule_evaluations.id"))  # For corrections

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    analysis_run = relationship("PCOSAnalysisRunModel", back_populates="evaluations")
    supersedes = relationship("PCOSRuleEvaluationModel", remote_side=[id])

    __table_args__ = (
        Index("idx_rule_evals_tenant", "tenant_id"),
        Index("idx_rule_evals_project", "project_id"),
        Index("idx_rule_evals_rule", "rule_code"),
        Index("idx_rule_evals_result", "result"),
        Index("idx_rule_evals_run", "analysis_run_id"),
    )


class PCOSComplianceSnapshotModel(Base):
    """Point-in-time compliance state."""
    __tablename__ = "pcos_compliance_snapshots"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"), nullable=False)

    snapshot_type = Column(String(50), nullable=False)
    snapshot_name = Column(String(255))

    triggered_by = Column(GUID(), ForeignKey("users.id"))
    trigger_reason = Column(Text)

    total_rules_evaluated = Column(Integer, nullable=False, default=0)
    rules_passed = Column(Integer, nullable=False, default=0)
    rules_failed = Column(Integer, nullable=False, default=0)
    rules_warning = Column(Integer, nullable=False, default=0)

    overall_score = Column(Integer)
    compliance_status = Column(String(50), nullable=False, default="unknown")

    category_scores = Column(JSONB, default=dict)

    previous_snapshot_id = Column(GUID(), ForeignKey("pcos_compliance_snapshots.id"))
    delta_summary = Column(JSONB)

    project_state = Column(JSONB, nullable=False, default=dict)

    is_attested = Column(Boolean, default=False)
    attested_at = Column(DateTime(timezone=True))
    attested_by = Column(GUID(), ForeignKey("users.id"))
    attestation_signature_id = Column(String(255))
    attestation_notes = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    project = relationship("PCOSProjectModel", back_populates="compliance_snapshots")

    __table_args__ = (
        Index("idx_snapshots_tenant", "tenant_id"),
        Index("idx_snapshots_project", "project_id"),
        Index("idx_snapshots_type", "snapshot_type"),
    )


class PCOSAuditEventModel(Base):
    """Audit log for significant compliance events."""
    __tablename__ = "pcos_audit_events"

    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(GUID(), ForeignKey("pcos_projects.id", ondelete="CASCADE"))

    event_type = Column(String(100), nullable=False)
    event_action = Column(String(100), nullable=False)

    actor_id = Column(GUID(), ForeignKey("users.id"))
    actor_email = Column(String(255))
    actor_role = Column(String(100))

    entity_type = Column(String(50))
    entity_id = Column(GUID())

    event_data = Column(JSONB, nullable=False, default=dict)
    previous_state = Column(JSONB)
    new_state = Column(JSONB)

    ip_address = Column(String(45))
    user_agent = Column(Text)
    request_id = Column(String(100))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_audit_events_tenant", "tenant_id"),
        Index("idx_audit_events_project", "project_id"),
        Index("idx_audit_events_type", "event_type"),
    )


# =============================================================================
# Pydantic Schemas (API Request/Response Models)
# =============================================================================

class AddressSchema(BaseModel):
    """Reusable address schema."""
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = "CA"
    zip: Optional[str] = None


# --- Company Schemas ---

class CompanyCreateSchema(BaseModel):
    """Schema for creating a company."""
    legal_name: str
    entity_type: EntityType
    ein: Optional[str] = None
    sos_entity_number: Optional[str] = None
    legal_address: Optional[AddressSchema] = None
    mailing_address: Optional[AddressSchema] = None
    has_la_city_presence: bool = False
    la_business_address: Optional[AddressSchema] = None
    owner_pay_mode: Optional[OwnerPayMode] = None


class CompanyUpdateSchema(BaseModel):
    """Schema for updating a company."""
    legal_name: Optional[str] = None
    entity_type: Optional[EntityType] = None
    ein: Optional[str] = None
    sos_entity_number: Optional[str] = None
    has_la_city_presence: Optional[bool] = None
    owner_pay_mode: Optional[OwnerPayMode] = None
    owner_pay_cpa_approved: Optional[bool] = None
    status: Optional[str] = None


class CompanyResponseSchema(BaseModel):
    """Schema for company response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    legal_name: str
    entity_type: str
    has_la_city_presence: bool
    owner_pay_mode: Optional[str] = None
    owner_pay_cpa_approved: bool
    status: str
    created_at: datetime


# --- Project Schemas ---

class ProjectCreateSchema(BaseModel):
    """Schema for creating a project."""
    name: str
    company_id: uuid_module.UUID
    code: Optional[str] = None
    project_type: ProjectType
    is_commercial: bool = False
    client_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    first_shoot_date: Optional[date] = None
    union_status: str = "non_union"
    minor_involved: bool = False


class ProjectUpdateSchema(BaseModel):
    """Schema for updating a project."""
    name: Optional[str] = None
    code: Optional[str] = None
    project_type: Optional[ProjectType] = None
    is_commercial: Optional[bool] = None
    client_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    first_shoot_date: Optional[date] = None
    union_status: Optional[str] = None
    minor_involved: Optional[bool] = None
    notes: Optional[str] = None


class ProjectResponseSchema(BaseModel):
    """Schema for project response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    company_id: uuid_module.UUID
    name: str
    code: Optional[str] = None
    project_type: str
    is_commercial: bool
    client_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    first_shoot_date: Optional[date] = None
    union_status: str
    minor_involved: bool
    gate_state: str
    risk_score: int
    blocking_tasks_count: int
    created_at: datetime


# --- Location Schemas ---

class LocationCreateSchema(BaseModel):
    """Schema for creating a location."""
    name: str
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: str = "CA"
    zip: Optional[str] = None
    jurisdiction: Jurisdiction
    location_type: LocationType
    estimated_crew_size: Optional[int] = None
    parking_spaces_needed: Optional[int] = None
    filming_hours_start: Optional[time] = None
    filming_hours_end: Optional[time] = None
    has_generator: bool = False
    has_special_effects: bool = False
    noise_level: Optional[str] = None
    shoot_dates: Optional[list[date]] = None


class LocationResponseSchema(BaseModel):
    """Schema for location response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    project_id: uuid_module.UUID
    name: str
    city: Optional[str] = None
    jurisdiction: str
    location_type: str
    permit_required: Optional[bool] = None
    created_at: datetime


# --- Engagement Schemas ---

class EngagementCreateSchema(BaseModel):
    """Schema for creating an engagement."""
    person_id: uuid_module.UUID
    role_title: str
    department: Optional[str] = None
    classification: ClassificationType
    pay_rate: Decimal
    pay_type: str  # 'hourly', 'daily', 'weekly', 'flat', 'kit_rental'
    overtime_eligible: bool = True
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    guaranteed_days: Optional[int] = None


class EngagementResponseSchema(BaseModel):
    """Schema for engagement response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    project_id: uuid_module.UUID
    person_id: uuid_module.UUID
    role_title: str
    department: Optional[str] = None
    classification: str
    pay_rate: Decimal
    pay_type: str
    status: str
    classification_memo_signed: bool
    w9_received: bool
    i9_received: bool
    w4_received: bool
    created_at: datetime


# --- Timecard Schemas ---

class TimecardCreateSchema(BaseModel):
    """Schema for creating a timecard."""
    work_date: date
    call_time: Optional[time] = None
    wrap_time: Optional[time] = None
    meal_1_out: Optional[time] = None
    meal_1_in: Optional[time] = None
    meal_2_out: Optional[time] = None
    meal_2_in: Optional[time] = None
    notes: Optional[str] = None


class TimecardResponseSchema(BaseModel):
    """Schema for timecard response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    engagement_id: uuid_module.UUID
    work_date: date
    call_time: Optional[time] = None
    wrap_time: Optional[time] = None
    regular_hours: Optional[Decimal] = None
    overtime_hours: Optional[Decimal] = None
    double_time_hours: Optional[Decimal] = None
    meal_penalty_count: int
    status: str
    wage_floor_met: Optional[bool] = None
    created_at: datetime


# --- Task Schemas ---

class TaskResponseSchema(BaseModel):
    """Schema for task response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    source_type: str
    source_id: uuid_module.UUID
    task_type: str
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: str
    is_blocking: bool
    requires_evidence: bool
    completed_at: Optional[datetime] = None
    created_at: datetime


class TaskUpdateSchema(BaseModel):
    """Schema for updating a task."""
    status: Optional[TaskStatus] = None
    notes: Optional[str] = None
    assigned_to: Optional[uuid_module.UUID] = None


# --- Gate Evaluation Schemas ---

class GateEvaluationResponseSchema(BaseModel):
    """Schema for gate evaluation response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    project_id: uuid_module.UUID
    current_state: str
    target_state: Optional[str] = None
    transition_allowed: bool
    blocking_tasks_count: int
    missing_evidence: Optional[list[str]] = None
    risk_score: int
    reasons: Optional[list[str]] = None
    evaluated_at: datetime


# --- Evidence Schemas ---

class EvidenceCreateSchema(BaseModel):
    """Schema for creating evidence."""
    entity_type: str
    entity_id: uuid_module.UUID
    evidence_type: EvidenceType
    title: str
    description: Optional[str] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None


class EvidenceResponseSchema(BaseModel):
    """Schema for evidence response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    entity_type: str
    entity_id: uuid_module.UUID
    evidence_type: str
    title: str
    file_name: Optional[str] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    is_signed: bool
    created_at: datetime


# --- Person Schemas ---

class PersonCreateSchema(BaseModel):
    """Schema for creating a person."""
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    address: Optional[AddressSchema] = None
    preferred_classification: Optional[ClassificationType] = None
    is_loan_out: bool = False
    loan_out_company_name: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    emergency_contact_relation: Optional[str] = None


class PersonResponseSchema(BaseModel):
    """Schema for person response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_module.UUID
    tenant_id: uuid_module.UUID
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    preferred_classification: Optional[str] = None
    is_loan_out: bool
    status: str
    created_at: datetime


# =============================================================================
# AUTHORITY & FACT LINEAGE MODELS
# =============================================================================

class PCOSAuthorityDocumentModel(Base):
    """
    Source authority documents: CBAs, statutes, regulations, municipal codes.
    
    Each document is hashed for integrity verification and serves as the
    ultimate source of truth for extracted facts.
    """
    __tablename__ = "pcos_authority_documents"
    
    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # Document identification
    document_code = Column(String(100), nullable=False)  # e.g., 'SAG_CBA_2023'
    document_name = Column(String(255), nullable=False)
    document_type = Column(String(50), nullable=False)   # 'cba', 'statute', 'regulation', etc.
    
    # Issuer information
    issuer_name = Column(String(255), nullable=False)
    issuer_type = Column(String(50))  # 'union', 'government', 'municipality'
    
    # Validity period
    effective_date = Column(Date, nullable=False)
    expiration_date = Column(Date)
    supersedes_document_id = Column(GUID(), ForeignKey("pcos_authority_documents.id"))
    
    # Document integrity
    document_hash = Column(String(64))  # SHA-256
    hash_algorithm = Column(String(20), default="SHA-256")
    original_file_path = Column(Text)
    content_type = Column(String(100))
    file_size_bytes = Column(Integer)
    
    # Extraction metadata
    ingested_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    ingested_by = Column(GUID())
    extraction_method = Column(String(50))  # 'manual', 'ocr', 'api'
    extraction_notes = Column(Text)
    
    # Status
    status = Column(String(20), nullable=False, default="active")
    verified_at = Column(DateTime(timezone=True))
    verified_by = Column(GUID())
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    extracted_facts = relationship("PCOSExtractedFactModel", back_populates="authority_document")
    supersedes = relationship("PCOSAuthorityDocumentModel", remote_side=[id])


class PCOSExtractedFactModel(Base):
    """
    Versioned facts extracted from authority documents.
    
    Each fact has validity conditions that determine when it applies
    (e.g., budget tier, date range, union affiliation).
    """
    __tablename__ = "pcos_extracted_facts"
    
    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    authority_document_id = Column(GUID(), ForeignKey("pcos_authority_documents.id", ondelete="CASCADE"), nullable=False)
    
    # Fact identification
    fact_key = Column(String(100), nullable=False)  # e.g., 'SAG_MIN_DAY_RATE'
    fact_category = Column(String(50), nullable=False)  # 'rate', 'threshold', 'deadline'
    fact_name = Column(String(255), nullable=False)
    fact_description = Column(Text)
    
    # Fact value (polymorphic)
    fact_value_type = Column(String(20), nullable=False)  # 'decimal', 'integer', 'string', etc.
    fact_value_decimal = Column(Numeric(15, 4))
    fact_value_integer = Column(Integer)
    fact_value_string = Column(Text)
    fact_value_boolean = Column(Boolean)
    fact_value_date = Column(Date)
    fact_value_json = Column(JSONB)
    fact_unit = Column(String(50))  # 'USD', 'percent', 'hours'
    
    # Validity conditions
    validity_conditions = Column(JSONB, nullable=False, default=dict)
    
    # Cryptographic Integrity
    fact_hash = Column(String(64))  # SHA-256(key|value|conditions|provenance)

    # Version tracking
    version = Column(Integer, nullable=False, default=1)
    previous_fact_id = Column(GUID(), ForeignKey("pcos_extracted_facts.id"))
    is_current = Column(Boolean, nullable=False, default=True)
    
    # Extraction provenance
    source_page = Column(Integer)
    source_section = Column(String(255))
    source_quote = Column(Text)  # Verbatim quote
    
    extraction_confidence = Column(Numeric(3, 2))  # 0.00 to 1.00
    extraction_method = Column(String(50))
    extraction_notes = Column(Text)
    
    # Audit
    extracted_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    extracted_by = Column(GUID())
    verified_at = Column(DateTime(timezone=True))
    verified_by = Column(GUID())
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    authority_document = relationship("PCOSAuthorityDocumentModel", back_populates="extracted_facts")
    citations = relationship("PCOSFactCitationModel", back_populates="extracted_fact")
    previous_version = relationship("PCOSExtractedFactModel", remote_side=[id])
    
    def get_value(self) -> Any:
        """Return the fact value based on type."""
        type_map = {
            "decimal": self.fact_value_decimal,
            "integer": self.fact_value_integer,
            "string": self.fact_value_string,
            "boolean": self.fact_value_boolean,
            "date": self.fact_value_date,
            "json": self.fact_value_json,
        }
        return type_map.get(self.fact_value_type)


class PCOSFactCitationModel(Base):
    """
    Links compliance verdicts back to the facts they used.
    
    Creates an audit trail showing exactly which authoritative facts
    were applied to reach a compliance decision.
    """
    __tablename__ = "pcos_fact_citations"
    
    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # What is being cited (polymorphic reference)
    citing_entity_type = Column(String(50), nullable=False)  # 'rule_evaluation', 'rate_check'
    citing_entity_id = Column(GUID(), nullable=False)
    
    # The fact being cited
    extracted_fact_id = Column(GUID(), ForeignKey("pcos_extracted_facts.id", ondelete="CASCADE"), nullable=False)
    
    # Citation context
    fact_value_used = Column(Text, nullable=False)  # Copy of value at citation time
    context_applied = Column(JSONB)  # Production context that matched
    
    # Citation purpose
    citation_type = Column(String(50), nullable=False)  # 'rate_comparison', 'threshold_check'
    citation_notes = Column(Text)
    
    # Result of applying this fact
    evaluation_result = Column(String(20))  # 'pass', 'fail', 'warning'
    comparison_operator = Column(String(20))  # 'gte', 'lte', 'eq'
    input_value = Column(Text)  # What was compared
    
    # Timestamps
    cited_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    # Relationships
    extracted_fact = relationship("PCOSExtractedFactModel", back_populates="citations")


# =============================================================================
# SCHEMA GOVERNANCE MODELS
# =============================================================================

class SchemaVersionModel(Base):
    """
    Schema migrations registry.
    
    Every migration must self-register here. If a migration runs
    without recording itself, it is invalid by definition.
    """
    __tablename__ = "schema_migrations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=False, unique=True)
    checksum = Column(String(64), nullable=False)  # SHA-256
    git_sha = Column(String(40))
    description = Column(Text)
    applied_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    applied_by = Column(String(100))
    execution_time_ms = Column(Integer)
    success = Column(Boolean, nullable=False, default=True)


class PCOSAnalysisRunModel(Base):
    """
    Analysis run tracking.
    
    Every analysis MUST have an AnalysisRun. This is the invariant
    that ensures all verdicts are traceable to a specific execution context.
    """
    __tablename__ = "pcos_analysis_runs"
    
    id = Column(GUID(), primary_key=True, default=uuid_module.uuid4)
    tenant_id = Column(GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    
    # Run identification
    run_type = Column(String(50), nullable=False)  # 'compliance_check', 'rate_validation'
    run_status = Column(String(20), nullable=False, default="pending")  # 'pending', 'running', 'completed', 'failed'
    
    # What was analyzed
    project_id = Column(GUID(), ForeignKey("pcos_projects.id"))
    entity_type = Column(String(50))
    entity_id = Column(GUID())
    
    # Run context (immutable snapshot)
    run_parameters = Column(JSONB, nullable=False, default=dict)
    rule_pack_version = Column(String(50))
    fact_snapshot_time = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    # Results
    total_evaluations = Column(Integer, default=0)
    pass_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    indeterminate_count = Column(Integer, default=0)
    
    # Execution metadata
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    execution_time_ms = Column(Integer)
    error_message = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    
    # Relationships
    project = relationship("PCOSProjectModel")
    evaluations = relationship("PCOSRuleEvaluationModel", back_populates="analysis_run")
    
    def mark_running(self):
        """Mark the run as started."""
        if self.run_status != "pending":
            raise ValueError("Can only start a pending run")
        self.run_status = "running"
        self.started_at = datetime.now(timezone.utc)
    
    def mark_completed(self, pass_count: int, fail_count: int, warning_count: int, indeterminate_count: int):
        """Mark the run as completed with results."""
        if self.run_status not in ("pending", "running"):
            raise ValueError("Can only complete a pending/running run")
        self.run_status = "completed"
        self.completed_at = datetime.now(timezone.utc)
        self.pass_count = pass_count
        self.fail_count = fail_count
        self.warning_count = warning_count
        self.indeterminate_count = indeterminate_count
        self.total_evaluations = pass_count + fail_count + warning_count + indeterminate_count
        if self.started_at:
            self.execution_time_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)
    
    def mark_failed(self, error: str):
        """Mark the run as failed."""
        if self.run_status not in ("pending", "running"):
            raise ValueError("Can only fail a pending/running run")
        self.run_status = "failed"
        self.completed_at = datetime.now(timezone.utc)
        self.error_message = error
        if self.started_at:
            self.execution_time_ms = int((self.completed_at - self.started_at).total_seconds() * 1000)


