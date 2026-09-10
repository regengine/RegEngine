"""Repeated events in one request must not create discarded chain predecessors."""

from uuid import uuid4

import pytest
from shared.canonical_persistence import CanonicalEventStore
from shared.cte_persistence import CTEPersistence, compute_chain_hash

from tests.shared.test_canonical_persistence_hardening import _make_event
from tests.shared.test_cte_persistence_hardening import FakeSession, _base_event, _FakeResult


@pytest.mark.parametrize("canonical", [False, True])
def test_repeated_batch_event_does_not_advance_chain(canonical):
    session = FakeSession()
    tenant = uuid4()
    if canonical:
        first = _make_event(tenant_id=tenant, idemp_key="first")
        duplicate = first.model_copy(update={"event_id": uuid4()})
        last = _make_event(tenant_id=tenant, idemp_key="last")
        last.traceability_lot_code = "LAST"
        session.add_rule(
            r"INSERT INTO fsma\.traceability_events",
            lambda sql, params: _FakeResult(rows=[(v,) for k, v in params.items() if k.startswith("event_id_")]),
        )
        results = CanonicalEventStore(session, dual_write=False).persist_events_batch([first, duplicate, last])
        chain_calls = [p for s, p in session.calls if "INSERT INTO fsma.hash_chain" in s]
        chains = [
            (p[f"seq_{i}"], p[f"eh_{i}"], p[f"pch_{i}"], p[f"ch_{i}"]) for p in chain_calls for i in range(len(p) // 6)
        ]
    else:
        first, last = _base_event(), _base_event(traceability_lot_code="LAST")
        session.add_rule(
            r"INSERT INTO fsma\.cte_events",
            lambda sql, params: _FakeResult(rows=[(v,) for k, v in params.items() if k.startswith("id_")]),
        )
        results = CTEPersistence(session).store_events_batch(str(tenant), [first, dict(first), last])
        chains = [
            (p["sequence_num"], p["event_hash"], p["previous_chain_hash"], p["chain_hash"])
            for s, p in session.calls
            if "INSERT INTO fsma.hash_chain" in s
        ]
    assert len(results) == 3
    assert results[0].event_id == results[1].event_id
    assert results[0].idempotent is False
    assert results[1].idempotent is True
    assert results[0].chain_hash == results[1].chain_hash
    assert [r[0] for r in chains] == [1, 2]
    assert chains[1][2] == chains[0][3]
    assert all(compute_chain_hash(row[1], row[2]) == row[3] for row in chains)
