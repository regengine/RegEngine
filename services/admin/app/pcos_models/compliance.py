"""Compliance and classification domain models for PCOS."""
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

    content_hash = Column(String(64))
    status_snapshot = Column(JSONB, default=dict)
    alerts_snapshot = Column(JSONB, default=list)
    profile_snapshot = Column(JSONB, default=dict)

    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime(timezone=True))
    verified_by = Column(String(100))

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

    @classmethod
    def compute_hash(cls, status: Dict, alerts: List, profile: Dict) -> str:
        """Compute a deterministic hash of the snapshot state."""
        import hashlib
        import json
        payload = {
            "status": status,
            "alerts": sorted(alerts, key=lambda x: str(x.get("id", ""))),
            "profile": profile
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def verify_integrity(self) -> bool:
        """Verify the stored hash against recomputed state."""
        computed = self.compute_hash(
            self.status_snapshot or {},
            self.alerts_snapshot or [],
            self.profile_snapshot or {}
        )
        return self.content_hash == computed

    def to_export_dict(self) -> Dict[str, Any]:
        """Convert to audit-ready export dictionary."""
        return {
            "snapshot_id": str(self.id),
            "snapshot_name": self.snapshot_name,
            "status": self.compliance_status,
            "score": self.overall_score,
            "created_at": self.created_at.isoformat(),
            "content_hash": self.content_hash,
            "integrity_verified": self.is_verified,
            "is_attested": self.is_attested,
            "attested_at": self.attested_at.isoformat() if self.attested_at else None,
            "attested_by": str(self.attested_by) if self.attested_by else None,
        }


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
