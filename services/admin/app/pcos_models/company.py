"""Company domain models for PCOS."""
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
