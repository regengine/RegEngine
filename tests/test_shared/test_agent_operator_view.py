"""Tests for the AgentReviewItem operator read model."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from shared.agent_operator_view import (
    AgentReviewItem,
    fetch_agent_review_items,
)


SHA256 = "d" * 64


class _FakeResult:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._scalar


class _FakeSession:
    def __init__(self, *, item_rows, receipt_rows=None, total=None):
        self.item_rows = item_rows
        self.receipt_rows = receipt_rows or []
        self.total = total if total is not None else len(item_rows)
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, params))
        if "COUNT(*)" in sql:
            return _FakeResult(scalar=self.total)
        if "FROM fsma.ingestion_run_receipts" in sql and "ORDER BY ingestion_run_id" in sql:
            return _FakeResult(rows=self.receipt_rows)
        return _FakeResult(rows=self.item_rows)


def _artifact_json(artifact_id, tenant_id, run_id, *, confidence=0.82):
    return {
        "artifact_id": str(artifact_id),
        "artifact_version": "agent-artifact.v1",
        "artifact_type": "field_mapping_suggestion",
        "tenant_id": str(tenant_id),
        "created_at": "2026-05-13T15:00:00Z",
        "agent_name": "fsma-risk-agent",
        "agent_version": "1.0.0",
        "model_name": "gpt-5",
        "suggestion": "Map Supplier TLC to traceability_lot_code.",
        "confidence": confidence,
        "requires_human_review": True,
        "context": {
            "evidence_ids": [],
            "canonical_event_ids": [],
            "ingestion_run_id": str(run_id),
            "source_hashes": [SHA256],
            "rule_id": None,
            "rule_version": None,
        },
        "payload": {
            "source_field": "Supplier TLC",
            "source_value": "LOT-123",
            "target_canonical_field": "traceability_lot_code",
            "normalized_value": "LOT-123",
            "rationale": "The supplier column carries the traceability lot code.",
        },
    }


def test_fetch_agent_review_items_assembles_contract_and_risk_fields():
    tenant_id = uuid4()
    artifact_id = uuid4()
    run_id = uuid4()
    receipt_id = uuid4()
    created_at = datetime(2026, 5, 13, 15, 0, tzinfo=timezone.utc)
    db = _FakeSession(
        item_rows=[
            {
                "artifact_id": artifact_id,
                "tenant_id": tenant_id,
                "artifact_type": "field_mapping_suggestion",
                "created_at": created_at,
                "agent_name": "fsma-risk-agent",
                "suggestion": "Map Supplier TLC to traceability_lot_code.",
                "confidence": 0.82,
                "requires_human_review": True,
                "review_id": None,
                "review_status": "pending",
                "reviewed_by": None,
                "reviewed_at": None,
                "ingestion_run_id": run_id,
                "ingestion_run_status": "processing",
                "source_system": "csv_upload",
                "source_file_name": "receiving.csv",
                "advisory_receipt_id": receipt_id,
                "advisory_receipt_state": "needs_review",
                "receipt_hash": "a" * 64,
                "evidence_ids": [],
                "canonical_event_ids": [],
                "source_hashes": [SHA256],
                "rule_id": None,
                "rule_version": None,
                "artifact": _artifact_json(artifact_id, tenant_id, run_id),
            }
        ],
        receipt_rows=[
            {
                "ingestion_run_id": run_id,
                "receipt_id": str(uuid4()),
                "sequence_num": 1,
                "state": "needs_review",
                "occurred_at": created_at,
                "actor": "agent:fsma-risk-agent",
                "request_id": None,
                "canonical_event_id": None,
                "evidence_attachment_id": None,
                "rule_evaluation_id": None,
                "export_log_id": None,
                "metadata": {},
                "payload_hash": "b" * 64,
                "previous_receipt_hash": None,
                "receipt_hash": "a" * 64,
                "created_at": created_at,
            }
        ],
    )

    response = fetch_agent_review_items(db, tenant_id=str(tenant_id), limit=25, offset=0)

    assert response.total == 1
    assert response.limit == 25
    assert response.offset == 0
    item = response.items[0]
    assert isinstance(item, AgentReviewItem)
    assert item.artifact_id == str(artifact_id)
    assert item.review_status == "pending"
    assert item.risk_score == 72.2
    assert item.compliance_gap_count == 4
    assert [gap.code for gap in item.compliance_gaps] == [
        "low_confidence",
        "human_review_required",
        "missing_evidence_anchor",
        "missing_rule_reference",
    ]
    assert item.ingestion_run_id == str(run_id)
    assert item.advisory_receipt_id == str(receipt_id)
    assert item.receipt_hash == "a" * 64
    assert item.chain_valid is True


def test_fetch_agent_review_items_applies_filters_and_pagination():
    tenant_id = uuid4()
    run_id = uuid4()
    created_after = datetime(2026, 5, 1, tzinfo=timezone.utc)
    created_before = datetime(2026, 5, 14, tzinfo=timezone.utc)
    db = _FakeSession(item_rows=[])

    fetch_agent_review_items(
        db,
        tenant_id=str(tenant_id),
        ingestion_run_id=str(run_id),
        review_status="accepted",
        artifact_type="identity_match_suggestion",
        created_after=created_after,
        created_before=created_before,
        limit=10,
        offset=20,
    )

    sql, params = db.calls[1]
    assert "aa.tenant_id = :tenant_id" in sql
    assert "aa.ingestion_run_id = :ingestion_run_id" in sql
    assert "COALESCE(ar.status, 'pending') = :review_status" in sql
    assert "aa.artifact_type = :artifact_type" in sql
    assert "aa.created_at >= :created_after" in sql
    assert "aa.created_at <= :created_before" in sql
    assert params["tenant_id"] == str(tenant_id)
    assert params["ingestion_run_id"] == str(run_id)
    assert params["limit"] == 10
    assert params["offset"] == 20


def test_fetch_agent_review_items_marks_unlinked_receipts_as_gap():
    tenant_id = uuid4()
    artifact_id = uuid4()
    run_id = uuid4()
    db = _FakeSession(
        item_rows=[
            {
                "artifact_id": artifact_id,
                "tenant_id": tenant_id,
                "artifact_type": "field_mapping_suggestion",
                "created_at": datetime(2026, 5, 13, tzinfo=timezone.utc),
                "agent_name": "agent",
                "suggestion": "Review",
                "confidence": 0.95,
                "requires_human_review": False,
                "review_id": None,
                "review_status": "pending",
                "reviewed_by": None,
                "reviewed_at": None,
                "ingestion_run_id": run_id,
                "ingestion_run_status": "processing",
                "source_system": None,
                "source_file_name": None,
                "advisory_receipt_id": None,
                "advisory_receipt_state": None,
                "receipt_hash": None,
                "evidence_ids": [uuid4()],
                "canonical_event_ids": [],
                "source_hashes": [SHA256],
                "rule_id": "rule",
                "rule_version": 1,
                "artifact": _artifact_json(artifact_id, tenant_id, run_id, confidence=0.95)
                | {
                    "requires_human_review": False,
                    "context": {
                        "evidence_ids": [str(uuid4())],
                        "canonical_event_ids": [],
                        "ingestion_run_id": str(run_id),
                        "source_hashes": [SHA256],
                        "rule_id": "rule",
                        "rule_version": 1,
                    },
                },
            }
        ],
    )

    item = fetch_agent_review_items(db, tenant_id=str(tenant_id)).items[0]

    assert item.chain_valid is None
    assert [gap.code for gap in item.compliance_gaps] == ["ledger_unlinked"]


def test_fetch_agent_review_items_rejects_invalid_limit():
    db = _FakeSession(item_rows=[])

    try:
        fetch_agent_review_items(db, tenant_id=str(uuid4()), limit=0)
    except ValueError as exc:
        assert "limit must be between 1 and 200" in str(exc)
    else:
        raise AssertionError("expected ValueError")
