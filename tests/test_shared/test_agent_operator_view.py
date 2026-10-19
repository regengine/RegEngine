"""Tests for the AgentReviewItem operator read model."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from shared.agent_operator_view import (
    AgentArtifactTimelineResponse,
    AgentReviewDecisionRequest,
    AgentReviewDecisionResponse,
    AgentReviewItem,
    fetch_agent_artifact_timeline,
    fetch_agent_review_items,
    upsert_agent_artifact_review,
)

SHA256 = "d" * 64


class _FakeResult:
    def __init__(self, *, rows=None, row=None, scalar=None):
        self._rows = rows or []
        self._row = row
        self._scalar = scalar

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def one(self):
        if not self._rows:
            raise AssertionError("expected one row")
        return self._rows[0]

    def one_or_none(self):
        if self._rows:
            return self._rows[0]
        return self._row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows

    def scalar_one(self):
        return self._scalar


class _FakeSession:
    def __init__(
        self,
        *,
        item_rows,
        receipt_rows=None,
        total=None,
        artifact_lookup_row=None,
        upsert_row=None,
        run_row=None,
        timeline_receipt_rows=None,
    ):
        self.item_rows = item_rows
        self.receipt_rows = receipt_rows or []
        self.total = total if total is not None else len(item_rows)
        self.artifact_lookup_row = artifact_lookup_row
        self.upsert_row = upsert_row
        self.run_row = run_row
        self.timeline_receipt_rows = timeline_receipt_rows or []
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.calls.append((sql, params))
        if "COUNT(*)" in sql:
            return _FakeResult(scalar=self.total)
        if "INSERT INTO fsma.agent_artifact_reviews" in sql:
            return _FakeResult(rows=[self.upsert_row] if self.upsert_row else [])
        if "FROM fsma.agent_artifacts aa" in sql and "aa.artifact_id = :artifact_id" in sql:
            return _FakeResult(rows=[self.artifact_lookup_row] if self.artifact_lookup_row else [])
        if "receipt_scope" in sql:
            # Operator-view item list: its tenant-scoped CTEs also name
            # fsma.ingestion_runs, so route it before the run-ledger read.
            return _FakeResult(rows=self.item_rows)
        if "FROM fsma.ingestion_runs" in sql:
            return _FakeResult(row=self.run_row)
        if "FROM fsma.ingestion_run_receipts" in sql and "ORDER BY sequence_num ASC" in sql:
            return _FakeResult(rows=self.timeline_receipt_rows)
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


def _item_row(
    *,
    tenant_id,
    artifact_id,
    run_id,
    receipt_id=None,
    receipt_hash="a" * 64,
):
    created_at = datetime(2026, 5, 13, 15, 0, tzinfo=timezone.utc)
    return {
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
        "advisory_receipt_state": "needs_review" if receipt_id else None,
        "receipt_hash": receipt_hash if receipt_id else None,
        "evidence_ids": [],
        "canonical_event_ids": [],
        "source_hashes": [SHA256],
        "rule_id": None,
        "rule_version": None,
        "artifact": _artifact_json(artifact_id, tenant_id, run_id),
    }


def _timeline_receipt_tuple(
    *,
    receipt_id,
    sequence_num,
    receipt_hash,
    previous_receipt_hash,
):
    return (
        receipt_id,
        sequence_num,
        "needs_review",
        datetime(2026, 5, 13, 15, 1, tzinfo=timezone.utc),
        "agent:fsma-risk-agent",
        None,
        None,
        None,
        None,
        None,
        {},
        "b" * 64,
        previous_receipt_hash,
        receipt_hash,
        datetime(2026, 5, 13, 15, 1, tzinfo=timezone.utc),
    )


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


def test_upsert_agent_artifact_review_inserts_terminal_decision_with_latest_receipt():
    tenant_id = uuid4()
    artifact_id = uuid4()
    run_id = uuid4()
    receipt_id = uuid4()
    review_id = uuid4()
    reviewer_id = uuid4()
    reviewed_at = datetime(2026, 5, 14, 9, 30, tzinfo=timezone.utc)
    db = _FakeSession(
        item_rows=[],
        artifact_lookup_row={
            "artifact_id": artifact_id,
            "tenant_id": tenant_id,
            "ingestion_run_id": run_id,
            "advisory_receipt_id": receipt_id,
        },
        upsert_row={
            "review_id": review_id,
            "artifact_id": artifact_id,
            "tenant_id": tenant_id,
            "status": "accepted",
            "reviewed_by": reviewer_id,
            "reviewed_at": reviewed_at,
            "ingestion_run_id": run_id,
            "advisory_receipt_id": receipt_id,
        },
    )

    response = upsert_agent_artifact_review(
        db,
        tenant_id=str(tenant_id),
        artifact_id=str(artifact_id),
        status="accepted",
        reviewed_by=str(reviewer_id),
        notes="Evidence verified.",
    )

    assert isinstance(response, AgentReviewDecisionResponse)
    assert response.review_id == str(review_id)
    assert response.artifact_id == str(artifact_id)
    assert response.tenant_id == str(tenant_id)
    assert response.status == "accepted"
    assert response.reviewed_by == str(reviewer_id)
    assert response.reviewed_at == reviewed_at
    assert response.ingestion_run_id == str(run_id)
    assert response.advisory_receipt_id == str(receipt_id)

    lookup_sql, lookup_params = db.calls[0]
    assert "FROM fsma.agent_artifacts aa" in lookup_sql
    assert "LEFT JOIN LATERAL" in lookup_sql
    assert "metadata->'agent_artifact'->>'artifact_id'" in lookup_sql
    assert lookup_params == {"tenant_id": str(tenant_id), "artifact_id": str(artifact_id)}

    upsert_sql, upsert_params = db.calls[1]
    assert "INSERT INTO fsma.agent_artifact_reviews" in upsert_sql
    assert "ON CONFLICT (tenant_id, artifact_id) DO UPDATE" in upsert_sql
    assert "reviewed_at" in upsert_sql
    assert "now()" in upsert_sql
    assert "operator_notes" in upsert_sql
    assert upsert_params["tenant_id"] == str(tenant_id)
    assert upsert_params["artifact_id"] == str(artifact_id)
    assert upsert_params["ingestion_run_id"] == str(run_id)
    assert upsert_params["advisory_receipt_id"] == str(receipt_id)
    assert upsert_params["status"] == "accepted"
    assert upsert_params["reviewed_by"] == str(reviewer_id)
    assert upsert_params["notes"] == "Evidence verified."


def test_upsert_agent_artifact_review_rejects_pending_status():
    db = _FakeSession(item_rows=[])

    with pytest.raises(ValueError, match="status must be one of"):
        upsert_agent_artifact_review(
            db,
            tenant_id=str(uuid4()),
            artifact_id=str(uuid4()),
            status="pending",
            reviewed_by=str(uuid4()),
        )

    assert db.calls == []


def test_upsert_agent_artifact_review_raises_lookup_for_missing_artifact():
    tenant_id = uuid4()
    artifact_id = uuid4()
    db = _FakeSession(item_rows=[], artifact_lookup_row=None)

    with pytest.raises(LookupError, match="not found for tenant"):
        upsert_agent_artifact_review(
            db,
            tenant_id=str(tenant_id),
            artifact_id=str(artifact_id),
            status="rejected",
            reviewed_by=str(uuid4()),
        )

    assert len(db.calls) == 1
    assert "INSERT INTO fsma.agent_artifact_reviews" not in db.calls[0][0]


def test_fetch_agent_artifact_timeline_returns_item_timeline_and_chain_valid():
    tenant_id = uuid4()
    artifact_id = uuid4()
    run_id = uuid4()
    receipt_one = uuid4()
    receipt_two = uuid4()
    db = _FakeSession(
        item_rows=[],
        artifact_lookup_row=_item_row(
            tenant_id=tenant_id,
            artifact_id=artifact_id,
            run_id=run_id,
            receipt_id=receipt_two,
            receipt_hash="c" * 64,
        ),
        run_row=(
            run_id,
            "csv_upload",
            "receiving.csv",
            "e" * 64,
            128,
            10,
            8,
            2,
            "processing",
            "mapper.v1",
            "schema.v1",
            "operator@example.com",
            datetime(2026, 5, 13, 15, 0, tzinfo=timezone.utc),
            None,
            [],
        ),
        timeline_receipt_rows=[
            _timeline_receipt_tuple(
                receipt_id=receipt_one,
                sequence_num=1,
                receipt_hash="a" * 64,
                previous_receipt_hash=None,
            ),
            _timeline_receipt_tuple(
                receipt_id=receipt_two,
                sequence_num=2,
                receipt_hash="c" * 64,
                previous_receipt_hash="a" * 64,
            ),
        ],
    )

    response = fetch_agent_artifact_timeline(
        db,
        tenant_id=str(tenant_id),
        artifact_id=str(artifact_id),
    )

    assert isinstance(response, AgentArtifactTimelineResponse)
    assert response.item.artifact_id == str(artifact_id)
    assert response.item.chain_valid is True
    assert response.timeline is not None
    assert response.timeline.run.id == str(run_id)
    assert [receipt.sequence_num for receipt in response.timeline.receipts] == [1, 2]
    assert response.chain_valid is True

    item_sql, item_params = db.calls[0]
    assert "FROM fsma.agent_artifacts aa" in item_sql
    assert "aa.artifact_id = :artifact_id" in item_sql
    assert item_params == {"tenant_id": str(tenant_id), "artifact_id": str(artifact_id)}
    assert "FROM fsma.ingestion_runs" in db.calls[1][0]
    assert db.calls[1][1] == {"tid": str(tenant_id), "rid": str(run_id)}
    assert "ORDER BY sequence_num ASC" in db.calls[2][0]


def test_fetch_agent_artifact_timeline_raises_lookup_for_missing_artifact():
    tenant_id = uuid4()
    artifact_id = uuid4()
    db = _FakeSession(item_rows=[], artifact_lookup_row=None)

    with pytest.raises(LookupError, match="not found for tenant"):
        fetch_agent_artifact_timeline(
            db,
            tenant_id=str(tenant_id),
            artifact_id=str(artifact_id),
        )


def test_operator_decision_models_forbid_unknown_fields():
    tenant_id = str(uuid4())
    artifact_id = str(uuid4())
    review_id = str(uuid4())
    reviewed_by = str(uuid4())
    reviewed_at = datetime(2026, 5, 14, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        AgentReviewDecisionRequest(
            status="accepted",
            notes="Evidence verified.",
            decision_metadata={"source": "unit-test"},
            unexpected=True,
        )

    with pytest.raises(ValidationError):
        AgentReviewDecisionResponse(
            review_id=review_id,
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            status="accepted",
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            ingestion_run_id=None,
            advisory_receipt_id=None,
            unexpected=True,
        )

    with pytest.raises(ValidationError):
        AgentArtifactTimelineResponse(
            item=AgentReviewItem(
                artifact_id=artifact_id,
                tenant_id=tenant_id,
                artifact_type="field_mapping_suggestion",
                created_at=reviewed_at,
                agent_name="agent",
                suggestion="Review this mapping.",
                confidence=0.9,
                requires_human_review=True,
                review_status="pending",
                risk_score=1.0,
                risk_breakdown={
                    "score": 1.0,
                    "uncapped_score": 1.0,
                    "confidence_risk": 0.0,
                    "review_risk": 1.0,
                    "artifact_type_risk": 0.0,
                    "evidence_gap_risk": 0.0,
                    "rule_gap_risk": 0.0,
                },
                compliance_gap_count=0,
                compliance_gaps=[],
            ),
            timeline=None,
            chain_valid=None,
            unexpected=True,
        )
