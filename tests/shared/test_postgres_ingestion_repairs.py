"""Regressions from the real-PostgreSQL ingest/export measurement."""

from datetime import timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from shared.canonical_event import normalize_webhook_event
from shared.canonical_persistence import CanonicalEventStore
from shared.canonical_persistence.verification import _recompute_event_sha256
from shared.cte_persistence.core import ALERT_INSERT_SQL, CTEPersistence
from shared.rules.engine import RulesEngine
from shared.rules.types import RuleEvaluationResult

from tests.shared.test_cte_persistence_hardening import FakeSession, _FakeResult


def _event():
    return SimpleNamespace(
        cte_type="shipping",
        traceability_lot_code="PG-REPAIR-1",
        product_description="Synthetic romaine",
        quantity=0.25,
        unit_of_measure="kg",
        location_gln=None,
        location_name="Synthetic origin",
        timestamp="2026-09-04T12:00:00Z",
        kdes={"ship_to_location": "Synthetic destination"},
    )


def _persist(session, event, tenant, *, batch, canonical=None):
    values = dict(
        event_type=event.cte_type,
        traceability_lot_code=event.traceability_lot_code,
        product_description=event.product_description,
        quantity=event.quantity,
        unit_of_measure=event.unit_of_measure,
        event_timestamp=event.timestamp,
        location_gln=event.location_gln,
        location_name=event.location_name,
        kdes=event.kdes,
    )
    store = CTEPersistence(session)
    if batch:
        if canonical is not None:
            values["_canonical_event"] = canonical
        return store.store_events_batch(tenant, [values], source="repair-test")[0]
    return store.store_event(tenant_id=tenant, **values, source="repair-test", canonical_event=canonical)


@pytest.mark.parametrize("batch", [False, True])
def test_webhook_digest_matches_canonical_content_without_trusting_cached_hash(batch):
    event, tenant = _event(), str(uuid4())
    canonical = normalize_webhook_event(event, tenant, source="repair-test")
    original_id = canonical.event_id
    canonical.sha256_hash = "0" * 64
    session = FakeSession()
    result = _persist(session, event, tenant, batch=batch, canonical=canonical)
    expected = canonical.model_copy(update={"event_id": UUID(result.event_id)}).compute_sha256_hash()
    assert result.sha256_hash == expected
    assert canonical.event_id == original_id
    assert canonical.sha256_hash == "0" * 64


@pytest.mark.parametrize("batch", [False, True])
def test_canonical_digest_rejects_another_tenants_event(batch):
    event = _event()
    canonical = normalize_webhook_event(event, str(uuid4()))
    session = FakeSession()
    with pytest.raises(ValueError, match="tenant"):
        _persist(session, event, str(uuid4()), batch=batch, canonical=canonical)
    assert not any("INSERT INTO" in statement for statement, _ in session.calls)


def test_canonical_projection_cannot_relabel_an_incompatible_ledger_entry():
    event = normalize_webhook_event(_event(), str(uuid4()))
    session = FakeSession()
    session.add_rule(r"SELECT event_hash, chain_hash, sequence_num", _FakeResult(rows=[("0" * 64, "chain", 1)]))
    with pytest.raises(ValueError, match="does not match the existing ledger"):
        CanonicalEventStore(session, dual_write=False, skip_chain_write=True).persist_event(event)
    assert not any("INSERT INTO" in statement for statement, _ in session.calls)


@pytest.mark.parametrize("batch", [False, True])
def test_chain_growth_uses_advisory_lock_without_update_privilege(batch):
    session = FakeSession()
    if batch:
        _persist(session, _event(), str(uuid4()), batch=True)
    else:
        # Existing legacy callers need no canonical object.
        values = _event()
        CTEPersistence(session).store_event(
            tenant_id=str(uuid4()),
            event_type=values.cte_type,
            traceability_lot_code=values.traceability_lot_code,
            product_description=values.product_description,
            quantity=values.quantity,
            unit_of_measure=values.unit_of_measure,
            event_timestamp=values.timestamp,
        )
    statements = [statement for statement, _ in session.calls]
    assert "pg_advisory_xact_lock" in statements[0]
    assert all("FOR UPDATE" not in statement for statement in statements)


def test_alert_insert_populates_both_legacy_and_compatibility_anchors():
    columns = ALERT_INSERT_SQL.split("(", 1)[1].split(")", 1)[0]
    assert "cte_event_id" in {c.strip() for c in columns.split(",")}
    assert ":cte_event_id" in ALERT_INSERT_SQL


@pytest.mark.parametrize("offset", [0, 330, -420])
def test_canonical_verifier_round_trips_database_timezone_without_hiding_tamper(offset):
    canonical = normalize_webhook_event(_event(), str(uuid4()), source="repair-test")
    canonical.event_timestamp = canonical.event_timestamp.astimezone(timezone(timedelta(minutes=offset)))
    values = dict(
        event_id=str(canonical.event_id),
        event_type=canonical.event_type.value,
        traceability_lot_code=canonical.traceability_lot_code,
        product_reference=canonical.product_reference,
        quantity=canonical.quantity,
        unit_of_measure=canonical.unit_of_measure,
        from_facility_reference=canonical.from_facility_reference,
        to_facility_reference=canonical.to_facility_reference,
        event_timestamp=canonical.event_timestamp.astimezone(timezone(timedelta(hours=-7))),
        timestamp_hint=canonical.event_timestamp.isoformat(),
        kdes=canonical.kdes,
    )
    assert _recompute_event_sha256(**values) == canonical.compute_sha256_hash()
    values["event_timestamp"] += timedelta(minutes=1)
    assert _recompute_event_sha256(**values) != canonical.compute_sha256_hash()


@pytest.mark.parametrize("mode,expected", [("single", 1), ("batch", 2), ("salvage", 1)])
def test_successful_evaluation_savepoints_do_not_accumulate(mode, expected):
    session = MagicMock()
    verdict = RuleEvaluationResult(rule_id="repair-rule", rule_version=1, result="pass", confidence=1.0)
    engine = RulesEngine(session)
    if mode == "single":
        engine._persist_evaluations("tenant", "event", [verdict])
    elif mode == "batch":
        engine._batch_persist_evaluations("tenant", [("event", verdict)] * 101)
    else:
        engine._salvage_rows("tenant", [("event", {})], "INSERT")
    assert session.begin_nested.return_value.commit.call_count == expected
    session.begin_nested.return_value.rollback.assert_not_called()
