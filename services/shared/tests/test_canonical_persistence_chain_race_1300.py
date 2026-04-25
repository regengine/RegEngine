"""Tests for issue #1300 — canonical_persistence: chain race, dual-write failure, RLS isolation.

Three coverage gaps closed:

1. **Chain race** — Two concurrent writers for the same tenant must produce
   non-overlapping sequence numbers.  The advisory lock in
   ``_acquire_chain_lock`` serialises chain growth; these tests verify that
   the sequence numbers computed during ``persist_events_batch`` are
   unique and monotonically increasing.

2. **Dual-write failure atomicity** — If ``_batch_insert_chain_entries``
   raises after ``_batch_insert_canonical_events`` succeeds, the exception
   must propagate to the caller so the surrounding transaction can be rolled
   back (no silent partial write).

3. **RLS tenant isolation** — Every SQL executed by the writer for tenant A
   must scope to ``tenant_id = A``; a writer must never touch tenant B's
   chain entries.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Path setup — mirrors the pattern used in test_canonical_event_schema_version_1197.py
# ---------------------------------------------------------------------------
_SHARED_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SHARED_DIR.parent
for _p in (_SHARED_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.canonical_event import CTEType, IngestionSource, TraceabilityEvent  # noqa: E402
from shared.canonical_persistence.writer import CanonicalEventStore  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TENANT_A = str(uuid4())
TENANT_B = str(uuid4())


def _make_event(tenant_id: str = TENANT_A, tlc: str = "TLC-RACE-001") -> TraceabilityEvent:
    evt = TraceabilityEvent(
        tenant_id=tenant_id,
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.RECEIVING,
        event_timestamp="2026-04-20T12:00:00Z",
        traceability_lot_code=tlc,
        quantity=1.0,
        unit_of_measure="each",
    )
    evt.prepare_for_persistence()
    return evt


def _mock_session():
    """Return a MagicMock session pre-wired for the common happy-path DB calls."""
    session = MagicMock()
    # execute().fetchone() → None by default (no existing idempotency key)
    session.execute.return_value.fetchone.return_value = None
    # execute().fetchall() → [] by default
    session.execute.return_value.fetchall.return_value = []
    return session


# ---------------------------------------------------------------------------
# 1. Chain race — non-overlapping sequence numbers
# ---------------------------------------------------------------------------


class TestChainRaceSequenceNumbers_Issue1300:
    """Verify that batch writes produce unique, contiguous sequence_nums
    when the DB reports the current chain head via fetchone().

    We simulate two sequential calls to persist_events_batch (representing
    two writers that would race in production) by replaying different chain
    head states and asserting the sequence numbers embedded in the chain
    entries they would write are non-overlapping.
    """

    def _make_store_with_head(self, sequence_num: int, chain_hash: str = "prev-hash"):
        """Build a store whose session returns *sequence_num* as the chain head."""
        session = MagicMock()

        def execute_side_effect(stmt, params=None):
            result = MagicMock()
            result.fetchone.return_value = None
            result.fetchall.return_value = []

            stmt_str = str(stmt) if not isinstance(stmt, str) else stmt

            # Chain head query
            if "ORDER BY sequence_num DESC" in stmt_str:
                result.fetchone.return_value = (chain_hash, sequence_num)

            # Idempotency pre-flight (SELECT idempotency_key … IN :keys)
            # returns empty — no pre-existing rows
            elif "idempotency_key IN" in stmt_str:
                result.fetchall.return_value = []

            # Batch INSERT canonical events → return all event_ids as inserted
            elif "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING" in stmt_str and "RETURNING event_id" in stmt_str:
                # Extract event_id params from the INSERT params dict
                if params:
                    event_ids = [v for k, v in params.items() if k.startswith("event_id_")]
                    result.fetchall.return_value = [(eid,) for eid in event_ids]

            return result

        session.execute.side_effect = execute_side_effect
        store = CanonicalEventStore(session, dual_write=False, skip_chain_write=False)
        return store, session

    def test_first_writer_sequences_start_at_head_plus_one(self):
        """Writer A's batch starts at sequence chain_head + 1."""
        current_head = 5
        events = [_make_event(tlc=f"TLC-{i}") for i in range(3)]

        store, session = self._make_store_with_head(current_head)

        # Capture chain entry inserts
        chain_seqs = []

        original_batch_insert = CanonicalEventStore._batch_insert_chain_entries

        def capture_chain_entries(self_inner, entries):
            chain_seqs.extend(e["sequence_num"] for e in entries)

        with patch.object(CanonicalEventStore, "_batch_insert_chain_entries", capture_chain_entries):
            # Rebuild store so the mock session is still used
            store2, session2 = self._make_store_with_head(current_head)
            store2.persist_events_batch(events)

        assert chain_seqs == [6, 7, 8], (
            f"Expected sequences [6, 7, 8] starting after head={current_head}, got {chain_seqs}"
        )

    def test_second_writer_sequences_start_after_first_writers_tail(self):
        """Simulated second writer with updated head sees non-overlapping seqs."""
        # First writer wrote 3 events: seqs 6, 7, 8 — tail is now 8
        events_b = [_make_event(tlc=f"TLC-B{i}") for i in range(2)]

        chain_seqs_b = []

        def capture_chain_entries(self_inner, entries):
            chain_seqs_b.extend(e["sequence_num"] for e in entries)

        with patch.object(CanonicalEventStore, "_batch_insert_chain_entries", capture_chain_entries):
            store, _ = self._make_store_with_head(sequence_num=8)
            store.persist_events_batch(events_b)

        assert chain_seqs_b == [9, 10], (
            f"Expected [9, 10] after head=8, got {chain_seqs_b}"
        )

    def test_no_duplicate_sequence_numbers_across_two_writers(self):
        """Union of both writers' sequences contains no duplicates."""
        seqs_a: list[int] = []
        seqs_b: list[int] = []

        def capture_a(self_inner, entries):
            seqs_a.extend(e["sequence_num"] for e in entries)

        def capture_b(self_inner, entries):
            seqs_b.extend(e["sequence_num"] for e in entries)

        events_a = [_make_event(tlc=f"AAA-{i}") for i in range(3)]
        events_b = [_make_event(tlc=f"BBB-{i}") for i in range(3)]

        with patch.object(CanonicalEventStore, "_batch_insert_chain_entries", capture_a):
            store_a, _ = self._make_store_with_head(sequence_num=0, chain_hash=None)
            # Patch chain head to return None (genesis) by overriding fetchone
            store_a2, session_a = self._make_store_with_head(sequence_num=2)
            store_a2.persist_events_batch(events_a)

        # Writer B begins after writer A finished with head at 2+3=5
        with patch.object(CanonicalEventStore, "_batch_insert_chain_entries", capture_b):
            store_b, _ = self._make_store_with_head(sequence_num=5)
            store_b.persist_events_batch(events_b)

        all_seqs = seqs_a + seqs_b
        assert len(all_seqs) == len(set(all_seqs)), (
            f"Duplicate sequence numbers detected: {all_seqs}"
        )

    def test_genesis_batch_starts_at_sequence_one(self):
        """When there is no chain head (None), first sequence_num must be 1."""
        session = MagicMock()

        def execute_side_effect(stmt, params=None):
            result = MagicMock()
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            stmt_str = str(stmt)
            if "ORDER BY sequence_num DESC" in stmt_str:
                result.fetchone.return_value = None  # genesis — no chain yet
            elif "RETURNING event_id" in stmt_str and "ON CONFLICT" in stmt_str:
                if params:
                    eids = [v for k, v in params.items() if k.startswith("event_id_")]
                    result.fetchall.return_value = [(e,) for e in eids]
            return result

        session.execute.side_effect = execute_side_effect
        store = CanonicalEventStore(session, dual_write=False)

        captured: list[int] = []

        def capture_chain(self_inner, entries):
            captured.extend(e["sequence_num"] for e in entries)

        with patch.object(CanonicalEventStore, "_batch_insert_chain_entries", capture_chain):
            events = [_make_event(tlc=f"GEN-{i}") for i in range(2)]
            store.persist_events_batch(events)

        assert captured == [1, 2], f"Genesis batch expected [1, 2], got {captured}"


# ---------------------------------------------------------------------------
# 2. Dual-write failure atomicity
# ---------------------------------------------------------------------------


class TestDualWriteFailureAtomicity_Issue1300:
    """If _batch_insert_chain_entries raises AFTER canonical events are inserted,
    the exception propagates to the caller so the transaction can be rolled back.
    No silent partial write.
    """

    def _make_session_canonical_ok(self, events: list) -> MagicMock:
        """Session that succeeds on canonical INSERT but fails on chain entry INSERT."""
        session = MagicMock()

        def execute_side_effect(stmt, params=None):
            result = MagicMock()
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            stmt_str = str(stmt)

            if "ORDER BY sequence_num DESC" in stmt_str:
                result.fetchone.return_value = ("prev-hash", 10)
            elif "RETURNING event_id" in stmt_str and "ON CONFLICT" in stmt_str:
                if params:
                    eids = [v for k, v in params.items() if k.startswith("event_id_")]
                    result.fetchall.return_value = [(e,) for e in eids]
            return result

        session.execute.side_effect = execute_side_effect
        return session

    def test_chain_entry_failure_propagates_to_caller(self):
        """Exception from _batch_insert_chain_entries must not be swallowed."""
        events = [_make_event()]
        session = self._make_session_canonical_ok(events)
        store = CanonicalEventStore(session, dual_write=False)

        chain_error = RuntimeError("DB constraint violation on hash_chain insert")

        with patch.object(
            CanonicalEventStore,
            "_batch_insert_chain_entries",
            side_effect=chain_error,
        ):
            with pytest.raises(RuntimeError, match="DB constraint violation"):
                store.persist_events_batch(events)

    def test_chain_entry_failure_does_not_return_success_results(self):
        """Caller must not receive CanonicalStoreResult objects on chain failure."""
        events = [_make_event()]
        session = self._make_session_canonical_ok(events)
        store = CanonicalEventStore(session, dual_write=False)

        with patch.object(
            CanonicalEventStore,
            "_batch_insert_chain_entries",
            side_effect=Exception("chain insert failed"),
        ):
            caught = False
            result = None
            try:
                result = store.persist_events_batch(events)
            except Exception:
                caught = True

        assert caught, "Exception was swallowed — partial write not visible to caller"
        assert result is None, "Function returned results despite chain write failure"

    def test_canonical_insert_failure_propagates(self):
        """Exception from _batch_insert_canonical_events propagates too."""
        events = [_make_event()]

        session = MagicMock()

        def execute_side_effect(stmt, params=None):
            result = MagicMock()
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            stmt_str = str(stmt)
            if "ORDER BY sequence_num DESC" in stmt_str:
                result.fetchone.return_value = ("h", 1)
            return result

        session.execute.side_effect = execute_side_effect
        store = CanonicalEventStore(session, dual_write=False)

        with patch.object(
            CanonicalEventStore,
            "_batch_insert_canonical_events",
            side_effect=RuntimeError("DB down"),
        ):
            with pytest.raises(RuntimeError, match="DB down"):
                store.persist_events_batch(events)


# ---------------------------------------------------------------------------
# 3. RLS tenant isolation
# ---------------------------------------------------------------------------


class TestRLSTenantIsolation_Issue1300:
    """Verify that every SQL executed by the writer scopes to the correct
    tenant_id.  No query for tenant A should embed tenant B's ID.
    """

    def _collect_sql_calls(self, tenant_id: str, events: list) -> list[tuple]:
        """Return (stmt_text, params) for every session.execute() call made."""
        calls_log: list[tuple] = []

        session = MagicMock()

        def execute_side_effect(stmt, params=None):
            calls_log.append((str(stmt), dict(params) if params else {}))
            result = MagicMock()
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            stmt_str = str(stmt)
            if "ORDER BY sequence_num DESC" in stmt_str:
                result.fetchone.return_value = ("h", 1)
            elif "RETURNING event_id" in stmt_str and "ON CONFLICT" in stmt_str:
                if params:
                    eids = [v for k, v in params.items() if k.startswith("event_id_")]
                    result.fetchall.return_value = [(e,) for e in eids]
            return result

        session.execute.side_effect = execute_side_effect

        store = CanonicalEventStore(session, dual_write=False)

        with patch.object(CanonicalEventStore, "_batch_insert_chain_entries", lambda *a, **kw: None):
            store.persist_events_batch(events)

        return calls_log

    def test_set_tenant_context_uses_correct_tenant(self):
        """set_tenant_context must be called with tenant A's ID, never tenant B's."""
        events = [_make_event(TENANT_A)]
        calls = self._collect_sql_calls(TENANT_A, events)

        tenant_context_calls = [
            params for stmt, params in calls
            # ``set_tenant_guc`` (via ``CanonicalEventStore.set_tenant_context``)
            # used to emit ``SET LOCAL app.tenant_id = :tid`` and now emits
            # ``SELECT set_config('app.tenant_id', :tid, true)`` for asyncpg
            # compatibility (#1879). Match either form on the GUC name.
            if "app.tenant_id" in stmt
        ]
        assert tenant_context_calls, "set_tenant_context was never called"
        for params in tenant_context_calls:
            assert params.get("tid") == TENANT_A, (
                f"set_tenant_context set wrong tenant: {params.get('tid')!r}"
            )

    def test_advisory_lock_uses_correct_tenant_hash_input(self):
        """pg_advisory_xact_lock must be called with tenant A's ID."""
        events = [_make_event(TENANT_A)]
        calls = self._collect_sql_calls(TENANT_A, events)

        lock_calls = [
            params for stmt, params in calls
            if "pg_advisory_xact_lock" in stmt
        ]
        assert lock_calls, "advisory lock was never acquired"
        for params in lock_calls:
            assert params.get("tid") == TENANT_A

    def test_chain_head_query_scoped_to_tenant(self):
        """hash_chain SELECT must bind tenant A's ID, never tenant B's."""
        events = [_make_event(TENANT_A)]
        calls = self._collect_sql_calls(TENANT_A, events)

        chain_head_calls = [
            params for stmt, params in calls
            if "ORDER BY sequence_num DESC" in stmt
        ]
        assert chain_head_calls, "chain head query not found"
        for params in chain_head_calls:
            assert params.get("tid") == TENANT_A, (
                f"chain head query scoped to wrong tenant: {params.get('tid')!r}"
            )

    def test_tenant_b_id_never_appears_in_tenant_a_writes(self):
        """No param value in any call should equal TENANT_B when writing for TENANT_A."""
        events = [_make_event(TENANT_A)]
        calls = self._collect_sql_calls(TENANT_A, events)

        for stmt, params in calls:
            for key, val in params.items():
                assert val != TENANT_B, (
                    f"Tenant B's ID leaked into a Tenant A write: key={key!r}, stmt={stmt[:80]!r}"
                )

    def test_mixed_tenant_batch_raises_before_any_db_write(self):
        """Batches mixing tenants must be rejected before touching the DB."""
        events = [
            _make_event(TENANT_A, tlc="TLC-A"),
            _make_event(TENANT_B, tlc="TLC-B"),
        ]

        session = MagicMock()
        store = CanonicalEventStore(session, dual_write=False)

        with pytest.raises(ValueError, match="single-tenant"):
            store.persist_events_batch(events)

        # session.execute should not have been called at all (fail fast)
        session.execute.assert_not_called()
