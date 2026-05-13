"""SQLAlchemy mappings for the agent operator persistence surface.

These models intentionally mirror the fsma tables used by the first operator
view. They are lightweight mappings for query/service code; the Alembic
migrations remain the source of truth for DDL and RLS.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class IngestionRunModel(Base):
    """Existing ingestion run state-machine table."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="ux_ingestion_runs_id_tenant"),
        {"schema": "fsma"},
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    source_system = Column(Text)
    source_file_name = Column(Text)
    source_file_hash = Column(Text)
    source_file_size = Column(Integer)
    record_count = Column(Integer)
    accepted_count = Column(Integer)
    rejected_count = Column(Integer)
    status = Column(Text)
    mapper_version = Column(Text)
    schema_version = Column(Text)
    initiated_by = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    errors = Column(JSONB)


class AdvisoryReceiptModel(Base):
    """Existing append-only ingestion run receipt ledger."""

    __tablename__ = "ingestion_run_receipts"
    __table_args__ = (
        UniqueConstraint("receipt_id", "tenant_id", name="ux_ingestion_run_receipts_id_tenant"),
        {"schema": "fsma"},
    )

    receipt_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    ingestion_run_id = Column(UUID(as_uuid=True), nullable=False)
    sequence_num = Column(Integer, nullable=False)
    state = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True))
    actor = Column(Text)
    request_id = Column(Text)
    canonical_event_id = Column(UUID(as_uuid=True))
    evidence_attachment_id = Column(UUID(as_uuid=True))
    rule_evaluation_id = Column(UUID(as_uuid=True))
    export_log_id = Column(UUID(as_uuid=True))
    metadata_ = Column("metadata", JSONB, nullable=False)
    payload_hash = Column(String(64), nullable=False)
    previous_receipt_hash = Column(String(64))
    receipt_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True))


class AgentArtifactModel(Base):
    """Persisted, append-only advisory agent artifact."""

    __tablename__ = "agent_artifacts"
    __table_args__ = (
        UniqueConstraint("artifact_id", "tenant_id", name="ux_agent_artifacts_artifact_tenant"),
        ForeignKeyConstraint(
            ["ingestion_run_id", "tenant_id"],
            ["fsma.ingestion_runs.id", "fsma.ingestion_runs.tenant_id"],
            name="fk_agent_artifacts_run_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("artifact_version = 'agent-artifact.v1'", name="ck_agent_artifacts_version"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_agent_artifacts_confidence"),
        Index("idx_agent_artifacts_tenant_created", "tenant_id", "created_at"),
        Index("idx_agent_artifacts_tenant_run", "tenant_id", "ingestion_run_id"),
        {"schema": "fsma"},
    )

    artifact_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    artifact_version = Column(Text, nullable=False)
    artifact_type = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    agent_name = Column(Text, nullable=False)
    agent_version = Column(Text, nullable=False)
    model_name = Column(Text)
    suggestion = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    requires_human_review = Column(Boolean, nullable=False)
    evidence_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("ARRAY[]::uuid[]"))
    canonical_event_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("ARRAY[]::uuid[]"))
    ingestion_run_id = Column(UUID(as_uuid=True))
    source_hashes = Column(ARRAY(Text), nullable=False, server_default=text("ARRAY[]::text[]"))
    rule_id = Column(Text)
    rule_version = Column(Integer)
    citation_reference = Column(Text)
    request_id = Column(Text)
    artifact = Column(JSONB, nullable=False)
    payload = Column(JSONB, nullable=False)
    artifact_hash = Column(String(64), nullable=False)


class AgentArtifactReviewModel(Base):
    """Operator review outcome for an advisory artifact."""

    __tablename__ = "agent_artifact_reviews"
    __table_args__ = (
        UniqueConstraint("tenant_id", "artifact_id", name="ux_agent_artifact_reviews_tenant_artifact"),
        ForeignKeyConstraint(
            ["artifact_id", "tenant_id"],
            ["fsma.agent_artifacts.artifact_id", "fsma.agent_artifacts.tenant_id"],
            name="fk_agent_reviews_artifact_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ingestion_run_id", "tenant_id"],
            ["fsma.ingestion_runs.id", "fsma.ingestion_runs.tenant_id"],
            name="fk_agent_reviews_run_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["advisory_receipt_id", "tenant_id"],
            ["fsma.ingestion_run_receipts.receipt_id", "fsma.ingestion_run_receipts.tenant_id"],
            name="fk_agent_reviews_receipt_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'needs_more_evidence')",
            name="ck_agent_reviews_status",
        ),
        Index("idx_agent_reviews_tenant_status", "tenant_id", "status", "created_at"),
        Index("idx_agent_reviews_tenant_artifact", "tenant_id", "artifact_id"),
        {"schema": "fsma"},
    )

    review_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    artifact_id = Column(UUID(as_uuid=True), nullable=False)
    ingestion_run_id = Column(UUID(as_uuid=True))
    advisory_receipt_id = Column(UUID(as_uuid=True))
    status = Column(Text, nullable=False, server_default=text("'pending'"))
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime(timezone=True))
    review_reason = Column(Text)
    operator_notes = Column(Text)
    decision_metadata = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


__all__ = [
    "AdvisoryReceiptModel",
    "AgentArtifactModel",
    "AgentArtifactReviewModel",
    "Base",
    "IngestionRunModel",
]
