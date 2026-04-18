"""Tests for #1332 — cte_persistence advisory lock.

The chain-head read uses ``SELECT … FOR UPDATE LIMIT 1`` which locks
the returned row, not the "next slot". On a tenant's first event the
SELECT returns zero rows and locks nothing, so two concurrent
first-event writers both see ``chain_head=None`` and both compute
``sequence_num=1``.

After the fix: ``_acquire_chain_lock`` calls
``pg_advisory_xact_lock(hashtext(tenant_id))`` at the top of both
write paths, serializing chain growth per tenant.

These tests mock the SQLAlchemy session and assert on SQL call
ordering — no live Postgres required.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from shared.cte_persistence.core import CTEPersistence

from tests.shared.test_cte_persistence_hardening import (
    FakeSession,
    _FakeResult,
)


def _base_event_args(**overrides):
    args = dict(
        tenant_id=str(uuid4()),
        event_type="shipping",
        traceability_lot_code="TLC-1",
        product_description="Apples",
        quantity=10.0,
        unit_of_measure="kg",
        event_timestamp="2026-04-18T00:00:00+00:00",
        source="api",
        location_gln="0614141000005",
        location_name="Facility A",
        kdes={},
    )
    args.update(overrides)
    return args


class TestAdvisoryLock_Issue1332:
    def test_store_event_acquires_advisory_lock_before_idempotency_check(self):
        """``_acquire_chain_lock`` must fire before any idempotency or
        chain-head SELECT so two concurrent first-event writers
        serialize instead of both computing sequence_num=1."""
        session = FakeSession()
        session.add_rule(
            r"SELECT id, sha256_hash, chain_hash\s+FROM fsma\.cte_events",
            _FakeResult(rows=[]),
        )
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        store = CTEPersistence(session=session)
        store.store_event(**_base_event_args())

        lock_idx = next(
            (i for i, c in enumerate(session.calls) if "pg_advisory_xact_lock" in c[0]),
            None,
        )
        idemp_idx = next(
            (i for i, c in enumerate(session.calls)
             if "FROM fsma.cte_events" in c[0] and "sha256_hash" in c[0]),
            None,
        )
        chain_idx = next(
            (i for i, c in enumerate(session.calls) if "FROM fsma.hash_chain" in c[0]),
            None,
        )
        assert lock_idx is not None, (
            "store_event must acquire an advisory lock (#1332)"
        )
        assert idemp_idx is not None, "idempotency SELECT must have fired"
        assert chain_idx is not None, "chain-head SELECT must have fired"
        assert lock_idx < idemp_idx, (
            "advisory lock must precede the idempotency check"
        )
        assert lock_idx < chain_idx, (
            "advisory lock must precede the chain-head read"
        )

    def test_store_events_batch_acquires_advisory_lock(self):
        """Batch path needs the same lock as single-event path."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        store = CTEPersistence(session=session)
        args = _base_event_args()
        tenant_id = args.pop("tenant_id")
        # Keep timestamps on the batch shape
        events = [args]
        store.store_events_batch(tenant_id, events)

        assert any(
            "pg_advisory_xact_lock" in c[0] for c in session.calls
        ), "batch path must acquire the advisory lock (#1332)"

    def test_advisory_lock_is_keyed_by_tenant(self):
        """Lock param must be the event's tenant_id so unrelated
        tenants do not serialize on each other."""
        session = FakeSession()
        session.add_rule(
            r"SELECT id, sha256_hash, chain_hash\s+FROM fsma\.cte_events",
            _FakeResult(rows=[]),
        )
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        store = CTEPersistence(session=session)
        args = _base_event_args()
        tid = args["tenant_id"]
        store.store_event(**args)

        lock_calls = [c for c in session.calls if "pg_advisory_xact_lock" in c[0]]
        assert lock_calls, "lock call expected"
        sql, params = lock_calls[0]
        assert "hashtext(:tid)" in sql
        assert params["tid"] == tid
