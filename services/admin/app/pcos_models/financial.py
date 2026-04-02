"""Task and evidence domain models for PCOS."""
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
