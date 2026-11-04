"""CANONICAL_LEGACY_DUAL_WRITE=off skips the legacy write and counts it (WI-12 PR B).

Mocks the SQLAlchemy session like test_canonical_dual_write_strict_1277.py,
so no database is needed: the assertion is that ``INSERT INTO fsma.cte_events``
is never executed while the flag is off, that the canonical insert still
commits, and that ``legacy_dual_write_skipped_total`` moves.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared.canonical_persistence import legacy_dual_write as migration
from shared.canonical_persistence.writer import CanonicalEventStore

from tests.shared.test_canonical_persistence_hardening import FakeSession, _FakeResult, _make_event


def _counter_value(path: str) -> float:
    return migration.LEGACY_DUAL_WRITE_SKIPPED.labels(path=path)._value.get()


def _session_without_legacy_rows() -> FakeSession:
    session = FakeSession()
    session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
    session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
    session.add_rule(
        r"INSERT INTO fsma\.traceability_events",
        _FakeResult(rows=[(str(uuid4()), "sha", "chain")]),
    )

    def _legacy_insert(sql, params):
        raise AssertionError("flag off: INSERT INTO fsma.cte_events must not run")

    session.add_rule(r"INSERT INTO fsma\.cte_events", _legacy_insert)
    return session


@pytest.mark.parametrize("value", ["off", "0", "false", "no", " OFF "])
def test_off_values_disable_the_dual_write(monkeypatch, value):
    monkeypatch.setenv(migration.DUAL_WRITE_FLAG_ENV, value)
    assert migration.legacy_dual_write_enabled() is False


@pytest.mark.parametrize("value", [None, "on", "1", "true", "yes", "anything-else"])
def test_default_and_on_values_keep_the_dual_write(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(migration.DUAL_WRITE_FLAG_ENV, raising=False)
    else:
        monkeypatch.setenv(migration.DUAL_WRITE_FLAG_ENV, value)
    assert migration.legacy_dual_write_enabled() is True


def test_single_write_skips_legacy_and_counts_when_off(monkeypatch):
    monkeypatch.setenv(migration.DUAL_WRITE_FLAG_ENV, "off")
    session = _session_without_legacy_rows()
    before = _counter_value("single")

    store = CanonicalEventStore(session=session, dual_write=True, skip_chain_write=True)
    result = store.persist_event(_make_event())

    assert result.success is True
    assert result.legacy_event_id is None
    assert not [sql for sql, _ in session.calls if "cte_events" in sql]
    assert _counter_value("single") == before + 1


def test_batch_write_skips_legacy_and_counts_each_event_when_off(monkeypatch):
    monkeypatch.setenv(migration.DUAL_WRITE_FLAG_ENV, "off")
    session = FakeSession()
    session.add_rule(r"SELECT idempotency_key, event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
    session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
    tenant = uuid4()
    events = [_make_event(tenant_id=tenant, idemp_key=f"k-{i}") for i in range(3)]
    session.add_rule(
        r"INSERT INTO fsma\.traceability_events",
        _FakeResult(rows=[(str(e.event_id),) for e in events]),
    )

    def _legacy_insert(sql, params):
        raise AssertionError("flag off: INSERT INTO fsma.cte_events must not run")

    session.add_rule(r"INSERT INTO fsma\.cte_events", _legacy_insert)
    before = _counter_value("batch")

    store = CanonicalEventStore(session=session, dual_write=True, skip_chain_write=True)
    store.persist_events_batch(events)

    assert not [sql for sql, _ in session.calls if "cte_events" in sql]
    assert _counter_value("batch") == before + 3


def test_on_keeps_the_legacy_write_and_the_counter_still(monkeypatch):
    monkeypatch.setenv(migration.DUAL_WRITE_FLAG_ENV, "on")
    session = FakeSession()
    session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
    session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
    session.add_rule(
        r"INSERT INTO fsma\.traceability_events",
        _FakeResult(rows=[(str(uuid4()), "sha", "chain")]),
    )
    before = _counter_value("single")

    store = CanonicalEventStore(session=session, dual_write=True, skip_chain_write=True)
    store.persist_event(_make_event())

    assert [sql for sql, _ in session.calls if "INSERT INTO fsma.cte_events" in sql]
    assert _counter_value("single") == before
