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
