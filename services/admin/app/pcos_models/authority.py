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
