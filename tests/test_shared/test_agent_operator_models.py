"""Tests for operator-view SQLAlchemy persistence mappings."""

from __future__ import annotations

from shared.agent_operator_models import (
    AdvisoryReceiptModel,
    AgentArtifactModel,
    AgentArtifactReviewModel,
    IngestionRunModel,
)
from sqlalchemy.dialects import postgresql


def test_operator_models_map_core_tables_to_fsma_schema():
    assert AgentArtifactModel.__tablename__ == "agent_artifacts"
    assert AgentArtifactModel.__table__.schema == "fsma"
    assert AgentArtifactReviewModel.__tablename__ == "agent_artifact_reviews"
    assert AgentArtifactReviewModel.__table__.schema == "fsma"
    assert IngestionRunModel.__tablename__ == "ingestion_runs"
    assert IngestionRunModel.__table__.schema == "fsma"
    assert AdvisoryReceiptModel.__tablename__ == "ingestion_run_receipts"
    assert AdvisoryReceiptModel.__table__.schema == "fsma"


def test_agent_artifact_model_exposes_operator_review_fields():
    columns = AgentArtifactModel.__table__.columns

    for column_name in [
        "artifact_id",
        "tenant_id",
        "artifact_version",
        "artifact_type",
        "created_at",
        "agent_name",
        "agent_version",
        "model_name",
        "suggestion",
        "confidence",
        "requires_human_review",
        "evidence_ids",
        "canonical_event_ids",
        "ingestion_run_id",
        "source_hashes",
        "rule_id",
        "rule_version",
        "citation_reference",
        "request_id",
        "artifact",
        "payload",
        "artifact_hash",
    ]:
        assert column_name in columns

    assert isinstance(columns["artifact"].type, postgresql.JSONB)
    assert isinstance(columns["payload"].type, postgresql.JSONB)
    assert isinstance(columns["evidence_ids"].type, postgresql.ARRAY)
    assert isinstance(columns["source_hashes"].type, postgresql.ARRAY)


def test_agent_artifact_review_model_exposes_decision_fields():
    columns = AgentArtifactReviewModel.__table__.columns

    for column_name in [
        "review_id",
        "tenant_id",
        "artifact_id",
        "ingestion_run_id",
        "advisory_receipt_id",
        "status",
        "reviewed_by",
        "reviewed_at",
        "review_reason",
        "operator_notes",
        "decision_metadata",
        "created_at",
        "updated_at",
    ]:
        assert column_name in columns

    assert isinstance(columns["decision_metadata"].type, postgresql.JSONB)


def test_agent_review_model_declares_tenant_safe_foreign_keys():
    constraints = {
        constraint.name: constraint for constraint in AgentArtifactReviewModel.__table__.constraints if constraint.name
    }

    assert "fk_agent_reviews_artifact_tenant" in constraints
    assert "fk_agent_reviews_run_tenant" in constraints
    assert "fk_agent_reviews_receipt_tenant" in constraints
    assert "ux_agent_artifact_reviews_tenant_artifact" in constraints
