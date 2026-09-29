"""V2 retries must evaluate stored facts, not attach changed facts to an old ID."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from shared.canonical_event import normalize_webhook_event
from shared.canonical_persistence import CanonicalEventStore
from shared.canonical_persistence.models import CanonicalStoreResult

from services.ingestion.tests import test_webhook_router_v2_1342 as harness

TENANT_A = "11111111-1111-4111-8111-111111111111"
TENANT_B = "22222222-2222-4222-8222-222222222222"
STORED_IDS = {
    TENANT_A: "33333333-3333-4333-8333-333333333333",
    TENANT_B: "44444444-4444-4444-8444-444444444444",
}
EVENT_TIME = datetime.now(timezone.utc).isoformat()


def _event(**changes):
    payload = harness._make_shipping_event(timestamp=EVENT_TIME)
    payload.update(changes)
    return harness.IngestEvent(**payload)


def _install(monkeypatch, *, replay=True, result_override=False, result=None, fallback=False):
    session = harness._FakeSession()
    persistence = harness._FakePersistence(session, batch_raises=ValueError("retry batch") if fallback else None)
    client, _, _ = harness._client(monkeypatch, session=session, persistence=persistence)
    captured = SimpleNamespace(
        candidates=[], snapshots=[], reads=[], evaluations=[], summaries=[], exceptions=[], sql=[]
    )
    captured.summary = SimpleNamespace(compliant=False, results=[object()], event_id="unbound")
    captured.stored = {}
    for tenant_id, event_id in STORED_IDS.items():
        canonical = normalize_webhook_event(_event(), tenant_id)
        canonical.event_id = UUID(event_id)
        canonical.prepare_for_persistence()
        captured.stored[tenant_id] = canonical
    session.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    def execute(statement, params):
        sql = str(statement)
        captured.sql.append((sql, params))
        if "FROM fsma.traceability_events" not in sql:
            return SimpleNamespace(fetchone=lambda: None)
        assert "tenant_id = :tid" in sql
        if "idempotency_key = :key" in sql:
            stored = captured.stored[params["tid"]]
            if stored is not None:
                assert params["key"] == stored.idempotency_key
            return SimpleNamespace(fetchone=lambda: (STORED_IDS[params["tid"]], "stored-sha", "stored-chain"))
        assert "event_id = :eid" in sql
        stored = captured.stored[params["tid"]]
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

    session.execute = execute

    class Store:
        def __init__(self, db_session, *, dual_write, skip_chain_write):
            assert db_session is session
            assert dual_write is False
            assert skip_chain_write is True

        def persist_event(self, canonical):
            captured.candidates.append(canonical)
            captured.snapshots.append(deepcopy(canonical.model_dump()))
            if result_override:
                return result
            if replay:
                return CanonicalEventStore(session, dual_write=False, skip_chain_write=True).persist_event(canonical)
            return CanonicalStoreResult(success=True, event_id=str(canonical.event_id), idempotent=False)

        def get_event(self, tenant_id, event_id):
            captured.reads.append((tenant_id, event_id))
            return CanonicalEventStore(session, dual_write=False).get_event(tenant_id, event_id)

    class Engine:
        def __init__(self, db_session):
            assert db_session is session

        def evaluate_event(self, event_data, *, persist, tenant_id):
            assert persist is True
            captured.evaluations.append((event_data, tenant_id))
            return captured.summary

        def persist_summary(self, summary, *, tenant_id, event_id):
            captured.summaries.append((summary, tenant_id, event_id))

    class Exceptions:
        def __init__(self, db_session):
            assert db_session is session

        def create_exceptions_from_evaluation(self, tenant_id, summary):
            captured.exceptions.append((tenant_id, summary.event_id))

    monkeypatch.setattr(harness.wr, "normalize_webhook_event", normalize_webhook_event)
    monkeypatch.setattr(sys.modules["shared.canonical_persistence"], "CanonicalEventStore", Store)
    monkeypatch.setattr(sys.modules["shared.rules_engine"], "RulesEngine", Engine)
    monkeypatch.setattr(sys.modules["shared.exception_queue"], "ExceptionQueueService", Exceptions)
    monkeypatch.setattr(harness.wr, "logger", Mock())
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    captured.graph = Mock()
    monkeypatch.setattr(harness.wr, "_publish_graph_sync", captured.graph)
    return session, client, captured


def _persist(session, *, event=None, tenant_id=TENANT_A, precomputed=None):
    harness.wr._persist_required_canonical_and_eval(session, event or _event(), tenant_id, precomputed)


@pytest.mark.parametrize("tenant_id", [TENANT_A, TENANT_B])
@pytest.mark.parametrize("precomputed", [False, True])
def test_identical_replay_evaluates_authoritative_stored_facts(monkeypatch, tenant_id, precomputed):
    session, _, captured = _install(monkeypatch)
    earlier = SimpleNamespace(compliant=True, results=[object()], event_id="candidate-preeval") if precomputed else None

    _persist(session, tenant_id=tenant_id, precomputed=earlier)

    data, evaluated_tenant = captured.evaluations[0]
    assert data["event_id"] == STORED_IDS[tenant_id]
    assert evaluated_tenant == tenant_id
    assert captured.summary.event_id == STORED_IDS[tenant_id]
    assert captured.exceptions == [(tenant_id, STORED_IDS[tenant_id])]
    assert captured.summaries == []
    assert captured.reads == [(tenant_id, STORED_IDS[tenant_id])]
    assert data["kdes"] == captured.stored[tenant_id].kdes
    assert data["kdes"] is not captured.candidates[0].kdes
    assert captured.candidates[0].model_dump() == captured.snapshots[0]
    assert str(captured.candidates[0].event_id) != data["event_id"]
    if earlier:
        assert earlier.event_id == "candidate-preeval"


@pytest.mark.parametrize("precomputed", [False, True])
def test_fresh_event_keeps_precomputed_fast_path(monkeypatch, precomputed):
    session, _, captured = _install(monkeypatch, replay=False)
    earlier = (
        SimpleNamespace(compliant=False, results=[object()], event_id="candidate-preeval") if precomputed else None
    )

    _persist(session, precomputed=earlier)

    expected_id = str(captured.candidates[0].event_id)
    assert captured.reads == []
    if earlier:
        assert captured.summaries == [(earlier, TENANT_A, expected_id)]
        assert captured.evaluations == []
        assert earlier.event_id == expected_id
    else:
        assert captured.evaluations[0][0]["event_id"] == expected_id
    assert captured.exceptions == [(TENANT_A, expected_id)]


@pytest.mark.parametrize(
    "changes", [{"quantity": 99}, {"unit_of_measure": "kg"}, {"product_description": "Other Romaine Hearts"}]
)
@pytest.mark.parametrize("precomputed", [False, True])
def test_real_same_key_replay_with_changed_content_fails_before_evidence(monkeypatch, changes, precomputed):
    session, _, captured = _install(monkeypatch)
    earlier = SimpleNamespace(compliant=True, results=[object()], event_id="candidate-preeval") if precomputed else None

    with pytest.raises(harness.wr._CanonicalPersistenceError):
        _persist(session, event=_event(**changes), precomputed=earlier)

    assert captured.candidates[0].idempotency_key == captured.stored[TENANT_A].idempotency_key
    assert captured.evaluations == captured.summaries == captured.exceptions == []
    assert captured.candidates[0].model_dump() == captured.snapshots[0]


@pytest.mark.parametrize(
    "field",
    [
        "event_type",
        "traceability_lot_code",
        "product_reference",
        "quantity",
        "unit_of_measure",
        "from_facility_reference",
        "to_facility_reference",
        "from_entity_reference",
        "to_entity_reference",
        "kdes",
    ],
)
def test_every_current_rule_input_is_compared_before_attaching_evidence(monkeypatch, field):
    session, _, captured = _install(monkeypatch)
    # Keep the key fixed to model a mismatched authoritative lookup; entity
    # references also are absent from the hash, so comparing hashes is unsafe.
    stored = captured.stored[TENANT_A]
    stored.__dict__[field] = {"different": True} if field == "kdes" else (99 if field == "quantity" else "different")
    if field == "event_type":
        stored.__dict__[field] = SimpleNamespace(value="receiving")

    with pytest.raises(harness.wr._CanonicalPersistenceError):
        _persist(session)

    assert captured.evaluations == captured.summaries == captured.exceptions == []


@pytest.mark.parametrize(
    "result",
    [
        None,
        SimpleNamespace(event_id=STORED_IDS[TENANT_A]),
        CanonicalStoreResult(success=False, event_id=STORED_IDS[TENANT_A]),
        CanonicalStoreResult(success=True),
        CanonicalStoreResult(success=True, event_id="bad-id"),
    ],
)
def test_invalid_persistence_result_never_writes_evidence(monkeypatch, result):
    session, _, captured = _install(monkeypatch, result_override=True, result=result)

    with pytest.raises(harness.wr._CanonicalPersistenceError):
        _persist(session, precomputed=SimpleNamespace(compliant=True, results=[object()]))

    assert captured.evaluations == captured.summaries == captured.exceptions == []


@pytest.mark.parametrize("invalid", ["missing", "tenant", "event-id"])
def test_missing_or_wrong_identity_authoritative_row_fails_closed(monkeypatch, invalid):
    session, _, captured = _install(monkeypatch)
    if invalid == "missing":
        captured.stored[TENANT_A] = None
    elif invalid == "tenant":
        captured.stored[TENANT_A].tenant_id = UUID(TENANT_B)
    else:
        captured.stored[TENANT_A].event_id = UUID(STORED_IDS[TENANT_B])

    with pytest.raises(harness.wr._CanonicalPersistenceError):
        _persist(session)

    assert captured.evaluations == captured.summaries == captured.exceptions == []


def test_identical_kdes_use_persisted_json_representation(monkeypatch):
    session, _, captured = _install(monkeypatch)
    event = _event()
    event.kdes["reference_id"] = UUID(STORED_IDS[TENANT_A])
    captured.stored[TENANT_A] = normalize_webhook_event(event, TENANT_A)
    captured.stored[TENANT_A].event_id = UUID(STORED_IDS[TENANT_A])

    _persist(session, event=event)

    assert captured.evaluations[0][0]["kdes"]["reference_id"] == STORED_IDS[TENANT_A]


@pytest.mark.parametrize("fallback", [False, True], ids=["batch", "per-event-fallback"])
def test_conflicting_replay_rolls_back_entire_request_before_publication(monkeypatch, fallback):
    session, client, captured = _install(monkeypatch, fallback=fallback)
    client.app.dependency_overrides[harness.get_ingestion_principal] = lambda: harness.IngestionPrincipal(
        key_id="test-key", scopes=["*"], tenant_id=TENANT_A, auth_mode="test"
    )
    monkeypatch.setattr(harness.wr, "_check_obligations", lambda *args: None)

    response = client.post(
        "/api/v1/webhooks/ingest",
        json={"source": "webhook_api", "tenant_id": TENANT_A, "events": [_event(quantity=99).model_dump(mode="json")]},
        headers={"Idempotency-Key": "conflicting-canonical-replay"},
    )

    assert response.status_code == 500, response.text
    assert session.rolled_back is True
    assert session.committed is False
    assert captured.evaluations == captured.summaries == captured.exceptions == []
    captured.graph.assert_not_called()
