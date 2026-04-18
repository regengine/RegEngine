"""Tests for #1266 — batch insert partial-failure tolerance.

Before the fix: ``_batch_insert_canonical_events`` did a plain multi-row
INSERT. If one row collided on ``(tenant_id, idempotency_key)`` the
whole 50-row chunk aborted; 49 good events lost.

After the fix: the INSERT carries ``ON CONFLICT ... DO NOTHING
RETURNING event_id``. The caller reconciles the returned set against
the input list; rows that lost the idempotency race are marked
``idempotent=True`` in the per-event result after re-selecting the
winner's sha256_hash / chain_hash.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from shared.canonical_persistence.writer import CanonicalEventStore

from tests.shared.test_canonical_persistence_hardening import (
    FakeSession,
    _FakeResult,
    _make_event,
)


class TestBatchInsertConflict_Issue1266:
    def test_batch_insert_sql_has_on_conflict_do_nothing(self):
        """The INSERT emitted by _batch_insert_canonical_events must
        include ON CONFLICT (tenant_id, idempotency_key) DO NOTHING so
        one colliding row does not abort the whole chunk."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        # The batch INSERT returns 2 rows (both landed).
        session.add_rule(
            r"INSERT INTO fsma\.traceability_events",
            lambda _sql, params: _FakeResult(rows=[
                (str(uuid4()),), (str(uuid4()),),
            ]),
        )

        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        shared_tid = uuid4()
        evts = [
            _make_event(tenant_id=shared_tid, idemp_key="a"),
            _make_event(tenant_id=shared_tid, idemp_key="b"),
        ]
        store.persist_events_batch(evts)

        insert_calls = [c for c in session.calls if "INSERT INTO fsma.traceability_events" in c[0]]
        assert insert_calls, "batch INSERT should have executed"
        sql = insert_calls[0][0]
        assert "ON CONFLICT" in sql.upper(), (
            "batch INSERT must carry ON CONFLICT to survive lost idempotency races"
        )
        assert "DO NOTHING" in sql.upper()
        assert "RETURNING" in sql.upper(), (
            "batch INSERT must RETURNING event_id so the caller can reconcile"
        )

    def test_lost_race_event_marked_idempotent(self):
        """A writer that lost the race for one of two events should still
        persist the other and should receive an ``idempotent=True``
        result for the lost row, populated from the winning row's
        sha256_hash / chain_hash."""
        winner_event_id = uuid4()
        winner_sha = "w" * 64
        winner_chain = "c" * 64

        # Build the events first so we can use the real (post-prepare)
        # idempotency_key in the reconcile mock. ``_make_event`` calls
        # ``prepare_for_persistence`` which hashes the raw key.
        shared_tid = uuid4()
        evt_a = _make_event(tenant_id=shared_tid, idemp_key="a")
        evt_b = _make_event(tenant_id=shared_tid, idemp_key="b")

        session = FakeSession()
        # The pre-flight idempotency check and the post-INSERT reconcile
        # SELECT share the same SQL shape. Distinguish them by call
        # order: first call is pre-flight (nobody pre-existing), second
        # call is the reconcile (our winner row for evt_b).
        idemp_select_calls: list[int] = []

        def _idemp_or_reconcile(_sql, _params):
            idemp_select_calls.append(1)
            if len(idemp_select_calls) == 1:
                # Pre-flight: nothing pre-existing.
                return _FakeResult(rows=[])
            # Reconcile: winner row for evt_b. Use the hashed key the
            # writer stored on the event — that's what the reconcile
            # SELECT would return from the DB.
            return _FakeResult(rows=[
                (
                    evt_b.idempotency_key,
                    str(winner_event_id),
                    winner_sha,
                    winner_chain,
                ),
            ])

        session.add_rule(
            r"SELECT idempotency_key, event_id, sha256_hash, chain_hash",
            _idemp_or_reconcile,
        )
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        # Batch INSERT returns only ONE row (event 'a' landed, 'b' lost).
        def _insert(_sql, params):
            # Grab the event_id we just inserted — that's the one returned.
            return _FakeResult(rows=[(params["event_id_0"],)])
        session.add_rule(r"INSERT INTO fsma\.traceability_events", _insert)

        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        results = store.persist_events_batch([evt_a, evt_b])

        assert len(results) == 2
        # evt_a landed
        assert results[0].idempotent is False
        assert results[0].event_id == str(evt_a.event_id)
        # evt_b lost the race — should be marked idempotent and carry
        # the winner's hashes, not our pre-computed ones.
        assert results[1].idempotent is True, (
            "lost-race event must be reported as idempotent"
        )
        assert results[1].event_id == str(winner_event_id)
        assert results[1].sha256_hash == winner_sha
        assert results[1].chain_hash == winner_chain

    def test_no_lost_race_no_reselect_query(self):
        """When every event in the batch lands, we must not issue a
        second SELECT for lost-race reconciliation — the fast path
        stays fast."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        session.add_rule(
            r"INSERT INTO fsma\.traceability_events",
            lambda _sql, params: _FakeResult(rows=[
                (params["event_id_0"],), (params["event_id_1"],),
            ]),
        )

        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        shared_tid = uuid4()
        results = store.persist_events_batch([
            _make_event(tenant_id=shared_tid, idemp_key="a"),
            _make_event(tenant_id=shared_tid, idemp_key="b"),
        ])

        # The pre-flight idempotency check fires once; on the fast path
        # (nothing lost) the reconcile SELECT must not fire a second
        # time. Same SQL shape, so assert the SELECT count is exactly 1.
        select_calls = [
            c for c in session.calls
            if "SELECT idempotency_key, event_id, sha256_hash, chain_hash" in c[0]
        ]
        assert len(select_calls) == 1, (
            "fast path must not issue the lost-race reconcile SELECT; "
            f"got {len(select_calls)} idempotency-select calls, expected 1"
        )
        assert all(not r.idempotent for r in results)
