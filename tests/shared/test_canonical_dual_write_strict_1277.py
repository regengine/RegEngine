"""
Regression tests for #1277 — ``dual_write_legacy`` used to swallow any
exception and return ``None``, so a canonical row could land in
``fsma.traceability_events`` without a matching row in the legacy
``fsma.cte_events`` table. Since FDA-export code still reads from the
legacy table during migration, the regulator-facing audit output then
silently diverged from the canonical source of truth — the same
failure mode behind the #1106 FDA-export tenant-bypass class of bugs.

The fix makes dual-write strict: ``dual_write_legacy`` propagates
exceptions, ``persist_event`` / ``persist_events_batch`` no longer wrap
those calls in try/except, and the surrounding transaction aborts on
legacy-write failure so canonical is rolled back too. Either both
tables have the event or NEITHER does.

These tests mock the SQLAlchemy session so they run without a live
Postgres instance; they assert on exception propagation and return-
type semantics, which are the parts the regression depends on.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from shared.canonical_persistence import legacy_dual_write as migration
from shared.canonical_persistence.writer import CanonicalEventStore

from tests.shared.test_canonical_persistence_hardening import (
    FakeSession,
    _FakeResult,
    _make_event,
)


# ---------------------------------------------------------------------------
# migration.dual_write_legacy contract
# ---------------------------------------------------------------------------


class TestDualWriteLegacyStrictContract_Issue1277:
    """``dual_write_legacy`` must raise on failure — not swallow and
    return None. Callers depend on the "both tables or neither"
    invariant; a None return quietly violates it."""

    def test_raises_when_cte_events_insert_fails(self):
        session = FakeSession()

        def _fail_on_cte_events_insert(sql, params):
            raise RuntimeError("simulated: legacy write failed (e.g. FK violation)")

        session.add_rule(r"INSERT INTO fsma\.cte_events", _fail_on_cte_events_insert)

        event = _make_event()

        # Before the fix this would have been caught internally, a
        # warning logged, and None returned. After the fix we expect a
        # loud exception that callers CAN respond to (and transactions
        # will roll back around).
        with pytest.raises(RuntimeError, match="legacy write failed"):
            migration.dual_write_legacy(session, event)

    def test_returns_str_not_optional_on_success(self):
        """The return type narrows from ``Optional[str]`` to ``str``
        because failure now raises. Tests depending on the old
        ``None``-on-failure pattern will see the exception directly."""
        session = FakeSession()
        event = _make_event()

        result = migration.dual_write_legacy(session, event)
        assert isinstance(result, str)
        assert result == str(event.event_id)

    def test_kde_write_failure_is_still_isolated(self):
        """Behavior preserved: a single malformed KDE rolls back its
        savepoint and the CTE event write survives. That inner
        isolation is intentional (KDEs are annotations), distinct from
        the outer invariant the #1277 fix protects."""
        session = FakeSession()
        event = _make_event()
        event.kdes = {"gtin": "ok", "bad_kde": "trouble"}

        def _sometimes_fail(sql, params):
            if params.get("kde_key") == "bad_kde":
                raise RuntimeError("simulated KDE failure")
            return _FakeResult()

        session.add_rule(r"INSERT INTO fsma\.cte_kdes", _sometimes_fail)

        # Must NOT raise — KDE inner savepoint handles it.
        result = migration.dual_write_legacy(session, event)
        assert result == str(event.event_id)


# ---------------------------------------------------------------------------
# CanonicalEventStore.persist_event propagates dual-write failure
# ---------------------------------------------------------------------------


class TestPersistEventPropagatesDualWriteFailure_Issue1277:
    def test_persist_event_raises_when_dual_write_fails(self):
        """#1277: persist_event must not swallow a dual-write failure.
        The caller (and the surrounding transaction) need to see the
        exception so canonical state can be rolled back."""
        session = FakeSession()
        session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        # Canonical INSERT succeeds...
        session.add_rule(
            r"INSERT INTO fsma\.traceability_events",
            _FakeResult(rows=[(str(uuid4()), "sha", "chain")]),
        )
        # ...but legacy INSERT blows up.
        def _fail(sql, params):
            raise RuntimeError("legacy write exploded")
        session.add_rule(r"INSERT INTO fsma\.cte_events", _fail)

        store = CanonicalEventStore(
            session=session, dual_write=True, skip_chain_write=True,
        )
        evt = _make_event()

        with pytest.raises(RuntimeError, match="legacy write exploded"):
            store.persist_event(evt)

    def test_persist_event_with_dual_write_false_skips_legacy_entirely(self):
        """Callers that don't need legacy-write (canonical_router,
        epcis.persistence, webhook_router_v2) must still work — the
        opt-out path must not touch dual_write_legacy at all."""
        session = FakeSession()
        session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        session.add_rule(
            r"INSERT INTO fsma\.traceability_events",
            _FakeResult(rows=[(str(uuid4()), "sha", "chain")]),
        )
        # A rule that would explode if hit — proves the code never calls it.
        def _fail(sql, params):
            raise AssertionError(
                "dual_write=False must NOT execute INSERT INTO fsma.cte_events"
            )
        session.add_rule(r"INSERT INTO fsma\.cte_events", _fail)

        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        result = store.persist_event(_make_event())
        assert result.success is True
        assert result.legacy_event_id is None


# ---------------------------------------------------------------------------
# CanonicalEventStore.persist_events_batch propagates dual-write failure
# ---------------------------------------------------------------------------


class TestPersistEventsBatchPropagatesDualWriteFailure_Issue1277:
    """The batch path previously had its own try/except around
    dual_write_legacy — even stricter to remove, because one failed
    legacy write in a batch of N could leave N-1 canonical rows with
    no legacy twin, invisibly biasing FDA exports."""

    def test_batch_raises_if_any_dual_write_fails(self):
        session = FakeSession()
        session.add_rule(
            r"SELECT idempotency_key, event_id, sha256_hash, chain_hash",
            _FakeResult(rows=[]),
        )
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        # Batch insert returns both event IDs as inserted.
        tenant = uuid4()
        evts = [_make_event(tenant_id=tenant, idemp_key=f"k-{i}") for i in range(2)]
        inserted_ids = {str(e.event_id) for e in evts}
        session.add_rule(
            r"INSERT INTO fsma\.traceability_events",
            _FakeResult(rows=[(eid,) for eid in inserted_ids]),
        )

        calls = {"cte_events": 0}

        def _cte_events_rule(sql, params):
            calls["cte_events"] += 1
            if calls["cte_events"] == 2:
                raise RuntimeError("second event's legacy write failed")
            return _FakeResult()

        session.add_rule(r"INSERT INTO fsma\.cte_events", _cte_events_rule)

        store = CanonicalEventStore(
            session=session, dual_write=True, skip_chain_write=True,
        )

        with pytest.raises(RuntimeError, match="second event's legacy write failed"):
            store.persist_events_batch(evts)

    def test_batch_with_dual_write_false_never_touches_legacy(self):
        """Opt-out path stays silent regardless of strict mode."""
        session = FakeSession()
        session.add_rule(
            r"SELECT idempotency_key, event_id, sha256_hash, chain_hash",
            _FakeResult(rows=[]),
        )
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        tenant = uuid4()
        evts = [_make_event(tenant_id=tenant, idemp_key=f"k-{i}") for i in range(3)]
        session.add_rule(
            r"INSERT INTO fsma\.traceability_events",
            _FakeResult(rows=[(str(e.event_id),) for e in evts]),
        )

        def _fail(sql, params):
            raise AssertionError("dual_write=False must skip legacy INSERTs")
        session.add_rule(r"INSERT INTO fsma\.cte_events", _fail)

        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        results = store.persist_events_batch(evts)
        assert len(results) == 3
        assert all(r.success for r in results)
