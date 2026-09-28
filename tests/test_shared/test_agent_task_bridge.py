"""Tests for the advisory agent-artifact task bridge."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import shared.agent_task_bridge as bridge
from jsonschema import Draft202012Validator, ValidationError as JsonSchemaValidationError
from pydantic import ValidationError
from shared.agent_artifacts import (
    AgentArtifact,
    AgentArtifactContext,
    FieldMappingSuggestionPayload,
)
from shared.agent_task_bridge import (
    AGENT_ARTIFACT_TASK_TYPE,
    AGENT_ARTIFACT_TASK_VERSION,
    AgentArtifactTaskPayload,
    append_agent_artifact_receipt,
    build_agent_artifact_task_payload,
    enqueue_agent_artifact_task,
    handle_agent_artifact_task,
    persist_agent_artifact,
    register_agent_bridge_handlers,
)

SCHEMA_PATH = Path("data-schemas/events/agent.task.schema.json")
SHA256 = "b" * 64


def _artifact(**overrides) -> AgentArtifact:
    defaults = {
        "artifact_id": uuid4(),
        "artifact_version": "agent-artifact.v1",
        "artifact_type": "field_mapping_suggestion",
        "tenant_id": uuid4(),
        "created_at": datetime(2026, 5, 13, 13, 30, tzinfo=timezone.utc),
        "agent_name": "fsma-field-mapper",
        "agent_version": "1.2.3",
        "model_name": "gpt-5",
        "suggestion": "Map Supplier TLC to traceability_lot_code.",
        "confidence": 0.91,
        "requires_human_review": False,
        "context": AgentArtifactContext(
            evidence_ids=[uuid4()],
            canonical_event_ids=[uuid4()],
            ingestion_run_id=uuid4(),
            source_hashes=[SHA256],
            rule_id="fsma-receiving-tlc-source",
            rule_version=3,
            citation_reference="21 CFR 1.1345(b)(3)",
            request_id="req-agent-bridge-001",
        ),
        "payload": FieldMappingSuggestionPayload(
            source_field="Supplier TLC",
            source_value="LOT-123",
            target_canonical_field="traceability_lot_code",
            normalized_value="LOT-123",
            rationale="The supplier column carries the traceability lot code.",
        ),
    }
    defaults.update(overrides)
    return AgentArtifact(**defaults)


def test_build_agent_artifact_task_payload_flattens_traceability_context():
    artifact = _artifact()

    payload = build_agent_artifact_task_payload(artifact)

    assert payload.task_version == AGENT_ARTIFACT_TASK_VERSION
    assert payload.task_type == AGENT_ARTIFACT_TASK_TYPE
    assert payload.artifact_id == artifact.artifact_id
    assert payload.tenant_id == artifact.tenant_id
    assert payload.evidence_ids == artifact.context.evidence_ids
    assert payload.canonical_event_ids == artifact.context.canonical_event_ids
    assert payload.ingestion_run_id == artifact.context.ingestion_run_id
    assert payload.source_hashes == artifact.context.source_hashes
    assert payload.rule_id == artifact.context.rule_id
    assert payload.rule_version == artifact.context.rule_version
    assert payload.artifact.context.source_hashes == [SHA256]


def test_agent_artifact_task_payload_rejects_embedded_artifact_mismatches():
    payload = build_agent_artifact_task_payload(_artifact()).model_dump(mode="json")
    payload["artifact"]["tenant_id"] = str(uuid4())

    with pytest.raises(ValidationError, match="tenant_id"):
        AgentArtifactTaskPayload(**payload)

    payload = build_agent_artifact_task_payload(_artifact()).model_dump(mode="json")
    payload["artifact"]["context"]["source_hashes"] = ["c" * 64]

    with pytest.raises(ValidationError, match="source_hashes"):
        AgentArtifactTaskPayload(**payload)


def test_enqueue_agent_artifact_task_uses_idempotent_tenant_scoped_queue_key(monkeypatch):
    artifact = _artifact()
    calls = []

    def fake_enqueue(db_session, task_type, payload, **kwargs):
        calls.append(
            {
                "db_session": db_session,
                "task_type": task_type,
                "payload": payload,
                "kwargs": kwargs,
            }
        )
        return 42

    monkeypatch.setattr(bridge, "enqueue_task", fake_enqueue)

    task_id = enqueue_agent_artifact_task("session", artifact)

    assert task_id == 42
    assert calls == [
        {
            "db_session": "session",
            "task_type": AGENT_ARTIFACT_TASK_TYPE,
            "payload": build_agent_artifact_task_payload(artifact).model_dump(mode="json"),
            "kwargs": {
                "tenant_id": str(artifact.tenant_id),
                "priority": 50,
                "idempotency_key": (
                    f"{AGENT_ARTIFACT_TASK_TYPE}:{artifact.tenant_id}:{artifact.artifact_id}:agent-artifact.v1"
                ),
                "scheduled_at": None,
                "visibility_timeout_seconds": 120,
            },
        }
    ]


def test_enqueue_agent_artifact_task_prioritizes_required_human_review(monkeypatch):
    artifact = _artifact(confidence=0.7, requires_human_review=True)
    captured = {}

    def fake_enqueue(db_session, task_type, payload, **kwargs):  # noqa: ARG001
        captured.update(kwargs)
        return 7

    monkeypatch.setattr(bridge, "enqueue_task", fake_enqueue)

    assert enqueue_agent_artifact_task("session", artifact) == 7
    assert captured["priority"] == 80


class _FakeInsertResult:
    def __init__(self, row=("receipt-001", "d" * 64)):
        self.row = row

    def fetchone(self):
        return self.row


class _FakeSession:
    def __init__(self, artifact_already_recorded=False):
        self.executed = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.artifact_already_recorded = artifact_already_recorded

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params or {}))
        if "INSERT INTO fsma.agent_artifacts" in str(statement) and self.artifact_already_recorded:
            # ON CONFLICT ... DO NOTHING RETURNING yields no row.
            return _FakeInsertResult(None)
        return _FakeInsertResult()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_append_agent_artifact_receipt_records_advisory_metadata():
    artifact = _artifact(confidence=0.7, requires_human_review=True)
    payload = build_agent_artifact_task_payload(artifact)
    session = _FakeSession()

    result = append_agent_artifact_receipt(session, payload)

    assert result.ledger_receipt_appended is True
    assert result.ledger_state == "needs_review"
    assert result.receipt_id == "receipt-001"
    assert result.receipt_hash == "d" * 64
    assert len(session.executed) == 1
    sql, params = session.executed[0]
    assert "INSERT INTO fsma.ingestion_run_receipts" in sql
    assert params["tenant_id"] == str(artifact.tenant_id)
    assert params["ingestion_run_id"] == str(artifact.context.ingestion_run_id)
    assert params["state"] == "needs_review"
    metadata = json.loads(params["metadata"])
    assert metadata["agent_artifact"]["artifact_id"] == str(artifact.artifact_id)
    assert metadata["agent_artifact"]["artifact_type"] == artifact.artifact_type
    assert metadata["traceability"]["evidence_ids"] == [str(value) for value in artifact.context.evidence_ids]
    assert metadata["traceability"]["source_hashes"] == [SHA256]
    assert metadata["advisory_contract"] == "propose_never_decide"


def test_persist_agent_artifact_inserts_flattened_operator_fields():
    artifact = _artifact()
    payload = build_agent_artifact_task_payload(artifact)
    session = _FakeSession()

    assert persist_agent_artifact(session, payload) is True

    assert len(session.executed) == 1
    sql, params = session.executed[0]
    assert "INSERT INTO fsma.agent_artifacts" in sql
    # Tenant-scoped arbiter: another tenant's id raises on the primary key
    # instead of being dropped silently; RETURNING reports whether it landed.
    assert "ON CONFLICT (artifact_id, tenant_id) DO NOTHING" in sql
    assert "RETURNING artifact_id" in sql
    assert params["artifact_id"] == str(artifact.artifact_id)
    assert params["tenant_id"] == str(artifact.tenant_id)
    assert params["artifact_type"] == artifact.artifact_type
    assert params["ingestion_run_id"] == str(artifact.context.ingestion_run_id)
    assert params["evidence_ids"] == [str(value) for value in artifact.context.evidence_ids]
    assert params["canonical_event_ids"] == [str(value) for value in artifact.context.canonical_event_ids]
    assert params["source_hashes"] == [SHA256]


def test_append_agent_artifact_receipt_noops_without_ingestion_run_anchor():
    artifact = _artifact(
        context=AgentArtifactContext(
            evidence_ids=[],
            canonical_event_ids=[],
            ingestion_run_id=None,
            source_hashes=[SHA256],
        )
    )
    session = _FakeSession()

    result = append_agent_artifact_receipt(
        session,
        build_agent_artifact_task_payload(artifact),
    )

    assert result.ledger_receipt_appended is False
    assert result.skip_reason == "missing_ingestion_run_id"
    assert session.executed == []


def test_handle_agent_artifact_task_applies_tenant_context_and_commits(monkeypatch):
    artifact = _artifact(confidence=0.7, requires_human_review=True)
    payload = build_agent_artifact_task_payload(artifact).model_dump(mode="json")
    session = _FakeSession()
    tenant_contexts = []

    monkeypatch.setattr(bridge, "_get_session", lambda: session)
    monkeypatch.setattr(
        bridge,
        "set_tenant_guc",
        lambda db_session, tenant_id: tenant_contexts.append((db_session, tenant_id)),
    )

    handle_agent_artifact_task(**payload)

    assert tenant_contexts == [(session, str(artifact.tenant_id))]
    assert any("INSERT INTO fsma.agent_artifacts" in sql for sql, _ in session.executed)
    assert any("INSERT INTO fsma.ingestion_run_receipts" in sql for sql, _ in session.executed)
    assert session.committed is True
    assert session.rolled_back is False
    assert session.closed is True


def test_redelivered_task_records_no_second_receipt(monkeypatch):
    artifact = _artifact(confidence=0.7, requires_human_review=True)
    payload = build_agent_artifact_task_payload(artifact).model_dump(mode="json")
    session = _FakeSession(artifact_already_recorded=True)

    monkeypatch.setattr(bridge, "_get_session", lambda: session)
    monkeypatch.setattr(bridge, "set_tenant_guc", lambda db_session, tenant_id: None)

    handle_agent_artifact_task(**payload)

    assert persist_agent_artifact(_FakeSession(artifact_already_recorded=True), payload) is False
    assert any("INSERT INTO fsma.agent_artifacts" in sql for sql, _ in session.executed)
    assert not any("INSERT INTO fsma.ingestion_run_receipts" in sql for sql, _ in session.executed)
    assert session.committed is True
    assert session.closed is True


def test_register_agent_bridge_handlers_registers_task_type(monkeypatch):
    registrations = []

    monkeypatch.setattr(
        bridge,
        "register_task_handler",
        lambda task_type, handler: registrations.append((task_type, handler)),
    )

    register_agent_bridge_handlers()

    assert registrations == [(AGENT_ARTIFACT_TASK_TYPE, handle_agent_artifact_task)]


def _checked_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _normalize_schema(value):
    if isinstance(value, dict):
        return {key: _normalize_schema(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize_schema(item) for item in value]
    return value


def test_checked_json_schema_validates_good_agent_task_payload():
    artifact = _artifact()
    payload = build_agent_artifact_task_payload(artifact).model_dump(mode="json")

    Draft202012Validator(_checked_schema()).validate(payload)


def test_checked_json_schema_rejects_extra_fields():
    artifact = _artifact()
    payload = build_agent_artifact_task_payload(artifact).model_dump(mode="json")
    payload["extra"] = "field"

    with pytest.raises(JsonSchemaValidationError):
        Draft202012Validator(_checked_schema()).validate(payload)


def test_checked_json_schema_matches_generated_pydantic_schema():
    generated = AgentArtifactTaskPayload.model_json_schema(ref_template="#/$defs/{model}")

    assert _normalize_schema(_checked_schema()) == _normalize_schema(generated)
