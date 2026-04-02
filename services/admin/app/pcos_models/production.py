"""Production domain models for PCOS."""
from __future__ import annotations
import uuid as uuid_module
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, Time, func, ARRAY, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from ..sqlalchemy_models import Base, GUID, JSONType


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
