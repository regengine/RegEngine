"""Canonical rule evidence must reference the stored event, including retries."""

from __future__ import annotations

import asyncio
import json
import sys
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import HTTPException
from shared.canonical_event import normalize_webhook_event
from shared.canonical_persistence import CanonicalEventStore
from shared.canonical_persistence.models import CanonicalStoreResult

from services.ingestion.tests import test_webhook_compat_enforcement as harness

TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"
STORED_IDS = {
    TENANT_A: "33333333-3333-4333-8333-333333333333",
    TENANT_B: "44444444-4444-4444-8444-444444444444",
}


def _install(monkeypatch, *, summary, replay=True, invalid_result=False, result=None):
    session, persistence, captured = harness._install(monkeypatch, summary=summary)
    captured.update(canonicals=[], snapshots=[], evaluations=[], exceptions=[], sql=[], stored={}, reads=[])
    session.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    for tenant_id, event_id in STORED_IDS.items():
        stored = normalize_webhook_event(harness._make_event(), tenant_id)
        stored.event_id = UUID(event_id)
        stored.prepare_for_persistence()
        captured["stored"][tenant_id] = stored

    def execute(statement, params):
        sql = str(statement)
        captured["sql"].append((sql, params))
        if "FROM fsma.traceability_events" in sql:
            assert "tenant_id = :tid" in sql
            if "event_id = :eid" in sql:
                stored = captured["stored"][params["tid"]]
                if stored is None:
                    return SimpleNamespace(fetchone=lambda: None)
                row = (
                    stored.event_id,
                    stored.tenant_id,
                    stored.source_system.value,
                    None,
                    stored.event_type.value,
                    stored.event_timestamp,
                    stored.event_timezone,
                    stored.product_reference,
                    stored.lot_reference,
                    stored.traceability_lot_code,
                    stored.quantity,
                    stored.unit_of_measure,
                    stored.from_entity_reference,
                    stored.to_entity_reference,
                    stored.from_facility_reference,
                    stored.to_facility_reference,
                    stored.transport_reference,
                    json.dumps(stored.kdes, default=str),
                    "{}",
                    "{}",
                    "{}",
                    stored.confidence_score,
                    stored.status.value,
                    None,
                    stored.schema_version,
                    stored.sha256_hash,
                    stored.chain_hash,
                    None,
                    None,
                )
                return SimpleNamespace(fetchone=lambda: row)
            return SimpleNamespace(fetchone=lambda: (STORED_IDS[params["tid"]], "stored-sha", "stored-chain"))
        return SimpleNamespace(fetchone=lambda: None)

    session.execute = execute

    class Store:
        def __init__(self, db_session, dual_write):
            assert db_session is session
            assert dual_write is False

        def persist_event(self, canonical):
            captured["canonicals"].append(canonical)
            captured["snapshots"].append(canonical.model_dump())
            if invalid_result:
                return result
            if replay:
                # Exercise the real tenant-qualified idempotent return, not
                # a fake that happens to mutate the caller's candidate ID.
                return CanonicalEventStore(session, dual_write=False).persist_event(canonical)
            return CanonicalStoreResult(success=True, event_id=str(canonical.event_id), idempotent=False)

        def get_event(self, tenant_id, event_id):
            captured["reads"].append((tenant_id, event_id))
            return CanonicalEventStore(session, dual_write=False).get_event(tenant_id, event_id)

    class Engine:
        def __init__(self, db_session):
            assert db_session is session

        def evaluate_event(self, event_data, persist, tenant_id):
            assert persist is True
            captured["evaluations"].append((event_data, tenant_id))
            return summary

    class Exceptions:
        def __init__(self, db_session):
            assert db_session is session

        def create_exceptions_from_evaluation(self, tenant_id, evaluation):
            captured["exceptions"].append((tenant_id, evaluation.event_id))

    monkeypatch.setattr(sys.modules["shared.canonical_event"], "normalize_webhook_event", normalize_webhook_event)
    monkeypatch.setattr(sys.modules["shared.canonical_persistence"], "CanonicalEventStore", Store)
    monkeypatch.setattr(sys.modules["shared.rules_engine"], "RulesEngine", Engine)
    monkeypatch.setattr(sys.modules["shared.exception_queue"], "ExceptionQueueService", Exceptions)
    monkeypatch.setattr(harness.wc, "logger", Mock())
    return session, persistence, captured


def _ingest(tenant_id=TENANT_A, *, principal=None, event=None):
    return asyncio.run(
        harness.wc.ingest_events(
            payload=harness._make_payload([event or harness._make_event()], tenant_id=tenant_id),
            principal_tenant_id=principal or tenant_id,
            x_regengine_api_key="test-key",  # pragma: allowlist secret - synthetic test credential
        )
    )


@pytest.mark.parametrize("replay", [False, True], ids=["fresh", "replay"])
@pytest.mark.parametrize("tenant_id", [TENANT_A, TENANT_B], ids=["tenant-a", "tenant-b"])
def test_rules_and_summary_anchor_to_persisted_identity_without_mutating_candidate(monkeypatch, replay, tenant_id):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    summary = harness._compliant_summary()
    session, _, captured = _install(monkeypatch, summary=summary, replay=replay)

    response = _ingest(tenant_id)

    canonical = captured["canonicals"][0]
    expected_id = STORED_IDS[tenant_id] if replay else str(canonical.event_id)
    assert captured["evaluations"][0][0]["event_id"] == expected_id
    assert captured["evaluations"][0][1] == tenant_id
    assert summary.event_id == expected_id
    assert str(canonical.tenant_id) == tenant_id
    assert canonical.model_dump() == captured["snapshots"][0]
    assert response.accepted == 1
    assert session.commit_count == 1
    if replay:
        assert str(canonical.event_id) != expected_id
        lookup = [(sql, params) for sql, params in captured["sql"] if "idempotency_key = :key" in sql]
        assert len(lookup) == 1
        assert lookup[0][1] == {"key": canonical.idempotency_key, "tid": tenant_id}
        assert captured["reads"] == [(tenant_id, expected_id)]
        assert captured["evaluations"][0][0]["kdes"] is not canonical.kdes


def test_advisory_exceptions_use_replayed_identity(monkeypatch):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    summary = harness._warning_only_summary()
    _, _, captured = _install(monkeypatch, summary=summary)

    assert _ingest().accepted == 1
    assert captured["exceptions"] == [(TENANT_A, STORED_IDS[TENANT_A])]


def test_rejection_audit_uses_replayed_identity(monkeypatch):
    import shared.rules.rejection_audit as audit

    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "cte_only")
    rejection_writer = Mock()
    monkeypatch.setattr(audit, "record_rejection", rejection_writer)
    summary = harness._critical_summary()
    session, _, captured = _install(monkeypatch, summary=summary)

    response = _ingest()

    assert response.rejected == 1
    assert rejection_writer.call_args.kwargs["event_id"] == STORED_IDS[TENANT_A]
    assert rejection_writer.call_args.kwargs["tenant_id"] == TENANT_A
    assert summary.event_id == STORED_IDS[TENANT_A]
    assert session.savepoints[0].rolled_back
    assert captured["publish_graph_calls"] == []


@pytest.mark.parametrize(
    "result",
    [
        None,
        SimpleNamespace(success=True),
        CanonicalStoreResult(success=True),
        CanonicalStoreResult(success=True, event_id=""),
        CanonicalStoreResult(success=True, event_id="not-a-uuid"),
        CanonicalStoreResult(success=False, event_id=STORED_IDS[TENANT_A]),
    ],
    ids=["no-result", "missing-id", "null-id", "empty-id", "malformed-id", "failed-result"],
)
def test_invalid_persisted_identity_aborts_before_rules_or_publication(monkeypatch, result):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    session, _, captured = _install(
        monkeypatch, summary=harness._compliant_summary(), invalid_result=True, result=result
    )

    with pytest.raises(HTTPException) as exc:
        _ingest()

    assert exc.value.status_code == 500
    assert exc.value.detail["error"] == "RULES_ENGINE_EVAL_FAILED"
    UUID(exc.value.detail["correlation_id"])
    assert exc.value.__suppress_context__
    assert session.commit_count == 0
    assert session.rollback_count == 1
    assert session.savepoints[1].rolled_back
    assert captured["evaluations"] == []
    assert captured["exceptions"] == []
    assert captured["publish_graph_calls"] == []


def test_mismatched_tenant_never_reaches_persistence_or_rules(monkeypatch):
    session, persistence, captured = _install(monkeypatch, summary=harness._compliant_summary())

    with pytest.raises(PermissionError, match="does not match authenticated principal"):
        _ingest(TENANT_B, principal=TENANT_A)

    assert persistence.store_calls == []
    assert captured["canonicals"] == []
    assert captured["evaluations"] == []
    assert captured["sql"] == []
    assert session.commit_count == 0


@pytest.mark.parametrize(
    "field,replacement",
    [("quantity", 99), ("unit_of_measure", "cases"), ("product_description", "Cherry tomatoes")],
)
def test_same_key_with_changed_content_fails_before_persisted_rules(monkeypatch, field, replacement):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    session, _, captured = _install(monkeypatch, summary=harness._compliant_summary())
    original = captured["stored"][TENANT_A].model_dump()
    event = harness._make_event()
    setattr(event, field, replacement)

    with pytest.raises(HTTPException) as exc:
        _ingest(event=event)

    assert exc.value.status_code == 500
    assert captured["canonicals"][0].idempotency_key == original["idempotency_key"]
    assert captured["stored"][TENANT_A].model_dump() == original
    assert captured["evaluations"] == []
    assert captured["exceptions"] == []
    assert captured["publish_graph_calls"] == []
    assert session.commit_count == 0
    assert session.rollback_count == 1


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("from_entity_reference", "different-sender"),
        ("to_entity_reference", "different-receiver"),
        ("from_facility_reference", "different-facility"),
        ("to_facility_reference", "different-destination"),
        ("kdes", {"different": "evidence"}),
        ("event_id", UUID("55555555-5555-4555-8555-555555555555")),
        ("tenant_id", UUID(TENANT_B)),
    ],
)
def test_stored_fact_or_identity_conflict_fails_before_rules(monkeypatch, field, replacement):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    session, _, captured = _install(monkeypatch, summary=harness._compliant_summary())
    setattr(captured["stored"][TENANT_A], field, replacement)
    original = deepcopy(captured["stored"][TENANT_A].model_dump())

    with pytest.raises(HTTPException) as exc:
        _ingest()

    assert exc.value.status_code == 500
    assert captured["stored"][TENANT_A].model_dump() == original
    assert captured["evaluations"] == []
    assert captured["publish_graph_calls"] == []
    assert session.rollback_count == 1


def test_missing_stored_replay_fails_before_rules(monkeypatch):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    session, _, captured = _install(monkeypatch, summary=harness._compliant_summary())
    captured["stored"][TENANT_A] = None

    with pytest.raises(HTTPException) as exc:
        _ingest()

    assert exc.value.status_code == 500
    assert captured["evaluations"] == []
    assert captured["publish_graph_calls"] == []
    assert session.rollback_count == 1


def test_identical_replay_uses_persisted_json_representation(monkeypatch):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    _, _, captured = _install(monkeypatch, summary=harness._compliant_summary())
    event = harness._make_event()
    event.kdes = {"reference": UUID(STORED_IDS[TENANT_A]), "count": 1}
    stored = captured["stored"][TENANT_A]
    stored.kdes.update({**event.kdes, "count": 1.0})

    assert _ingest(event=event).accepted == 1
    evaluated_kdes = captured["evaluations"][0][0]["kdes"]
    assert evaluated_kdes["reference"] == STORED_IDS[TENANT_A]
    assert isinstance(evaluated_kdes["count"], float)
