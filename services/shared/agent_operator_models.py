"""SQLAlchemy mappings for the agent operator persistence surface.

These models intentionally mirror the fsma tables used by the first operator
view. They are lightweight mappings for query/service code; the Alembic
migrations remain the source of truth for DDL and RLS.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
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
        # The database enforces this as a UNIQUE INDEX (v079), not a table
        # constraint — declare it the same way so autogenerate agrees.
        Index("ux_ingestion_runs_id_tenant", "id", "tenant_id", unique=True),
        {
            "schema": "fsma",
            "comment": "Batch provenance — one row per file upload, API call, or EPCIS document import",
        },
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    source_system = Column(Text, nullable=False)
    source_file_name = Column(Text)
    source_file_hash = Column(Text)
    source_file_size = Column(BigInteger)
    record_count = Column(Integer, nullable=False, server_default=text("0"))
    accepted_count = Column(Integer, nullable=False, server_default=text("0"))
    rejected_count = Column(Integer, nullable=False, server_default=text("0"))
    status = Column(Text, nullable=False, server_default=text("'processing'"))
    mapper_version = Column(Text, nullable=False, server_default=text("'1.0.0'"))
    schema_version = Column(Text, nullable=False, server_default=text("'1.0.0'"))
    initiated_by = Column(Text)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at = Column(DateTime(timezone=True))
    errors = Column(JSONB, server_default=text("'[]'::jsonb"))


class AdvisoryReceiptModel(Base):
    """Existing append-only ingestion run receipt ledger."""

    __tablename__ = "ingestion_run_receipts"
    __table_args__ = (
        # UNIQUE INDEX in the database (v079) — the composite-FK target for
        # agent_artifact_reviews.advisory_receipt_id.
        Index("ux_ingestion_run_receipts_id_tenant", "receipt_id", "tenant_id", unique=True),
        # Named table constraints from the v079 CREATE TABLE.
        UniqueConstraint("tenant_id", "receipt_hash", name="ux_ingestion_run_receipts_hash"),
        UniqueConstraint(
            "tenant_id",
            "ingestion_run_id",
            "sequence_num",
            name="ux_ingestion_run_receipts_run_sequence",
        ),
        # Composite tenant-scoped FK to the one referenced table that has an
        # ORM model. Name and ON DELETE RESTRICT match the v079 DDL exactly
        # so autogenerate agrees. The sibling v079 FKs (event, evidence,
        # rule-eval, export) point at raw-SQL-managed tables with no ORM
        # model, so they cannot be declared here: an unresolvable string
        # reference raises NoReferencedTableError during autogenerate
        # comparison (use_alter does not help; the comparator still
        # resolves). Those four stay covered by the one-directional
        # foreign_key_constraint rule in alembic/env.py, which ignores
        # database-only FKs the same way it ignores database-only indexes
        # and CHECK constraints. Do NOT "complete" this set without adding
        # ORM models for the referenced tables first.
        ForeignKeyConstraint(
            ["ingestion_run_id", "tenant_id"],
            ["fsma.ingestion_runs.id", "fsma.ingestion_runs.tenant_id"],
            name="fk_ingestion_run_receipts_run_tenant",
            ondelete="RESTRICT",
        ),
        {
            "schema": "fsma",
            "comment": "Tenant-scoped append-only state receipt ledger for ingestion runs.",
        },
    )

    receipt_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    ingestion_run_id = Column(UUID(as_uuid=True), nullable=False)
    sequence_num = Column(BigInteger, nullable=False)
    state = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    actor = Column(Text, nullable=False, server_default=text("'system'"))
    request_id = Column(Text)
    canonical_event_id = Column(UUID(as_uuid=True))
    evidence_attachment_id = Column(UUID(as_uuid=True))
    rule_evaluation_id = Column(UUID(as_uuid=True))
    export_log_id = Column(UUID(as_uuid=True))
    metadata_ = Column("metadata", JSONB, nullable=False)
    payload_hash = Column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of the receipt metadata JSONB payload.",
    )
    previous_receipt_hash = Column(
        String(64),
        comment="Hash of the previous receipt for the same ingestion run; NULL for sequence 1.",
    )
    receipt_hash = Column(
        String(64),
        nullable=False,
        comment=(
            "SHA-256 hash over receipt identity, state, links, payload hash, "
            "and previous receipt hash."
        ),
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


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
        # Names match the v080 DDL that actually created these constraints.
        # They used to be ck_agent_artifacts_version / _confidence, which meant
        # autogenerate saw an ORM constraint the database did not have and a
        # database constraint the ORM did not claim — invisible while alembic
        # ignored CHECK constraints, an add/remove pair from 1.19 onward.
        CheckConstraint("artifact_version = 'agent-artifact.v1'", name="agent_artifacts_artifact_version_check"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="agent_artifacts_confidence_check"),
        # NOTE: the database versions of these indexes order created_at DESC
        # (v080). SQLAlchemy reflection cannot round-trip the DESC element,
        # so they are name-quarantined from the drift gate in alembic/env.py.
        Index("idx_agent_artifacts_tenant_created", "tenant_id", "created_at"),
        Index("idx_agent_artifacts_tenant_run", "tenant_id", "ingestion_run_id"),
        {
            "schema": "fsma",
            "comment": "Tenant-scoped append-only storage for validated advisory agent artifacts.",
        },
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
    artifact_hash = Column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of the persisted artifact JSONB payload.",
    )


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
        # Name matches the v080 DDL — see the note on agent_artifacts above.
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'needs_more_evidence')",
            name="agent_artifact_reviews_status_check",
        ),
        # Database version orders created_at DESC (v080) — name-quarantined
        # from the drift gate (see alembic/env.py).
        Index("idx_agent_reviews_tenant_status", "tenant_id", "status", "created_at"),
        Index("idx_agent_reviews_tenant_artifact", "tenant_id", "artifact_id"),
        {
            "schema": "fsma",
            "comment": "Tenant-scoped operator review outcomes for advisory agent artifacts.",
        },
    )

    review_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), nullable=False)
    artifact_id = Column(UUID(as_uuid=True), nullable=False)
    ingestion_run_id = Column(UUID(as_uuid=True))
    advisory_receipt_id = Column(UUID(as_uuid=True))
    status = Column(
        Text,
        nullable=False,
        server_default=text("'pending'"),
        comment="Operator review status: pending, accepted, rejected, or needs_more_evidence.",
    )
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
