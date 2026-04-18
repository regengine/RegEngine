"""
Tenant-context tests for shared.canonical_persistence.CanonicalEventStore.

Exercises the fix for:

- #1265 — ``persist_event`` / ``persist_events_batch`` / ``create_ingestion_run``
  never called ``set_tenant_context``, so every RLS policy on the six-plus
  tables these methods touch was silently bypassed whenever the caller
  forgot to set ``app.tenant_id`` first. After the fix, the writer sets
  the GUC on entry regardless of caller discipline; RLS becomes true
  defense-in-depth, not callsite-discipline.

These tests mock the SQLAlchemy session so they run without a live
Postgres instance; they assert on SQL text + call ordering.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest

from shared.canonical_persistence.writer import CanonicalEventStore

from tests.shared.test_canonical_persistence_hardening import (
    FakeSession,
    _FakeResult,
    _make_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_call_containing(session: FakeSession, needle: str) -> int | None:
    """Return the index of the first execute() call whose SQL contains ``needle``."""
    for i, (sql, _params) in enumerate(session.calls):
        if needle in sql:
            return i
    return None


def _set_tenant_context_params(session: FakeSession) -> List[Dict[str, Any]]:
    """Return the params of every ``SET LOCAL app.tenant_id`` call in order."""
    return [
        params for sql, params in session.calls
        if "SET LOCAL app.tenant_id" in sql
    ]


# ---------------------------------------------------------------------------
# #1265 — persist_event binds the GUC before any chain operation
# ---------------------------------------------------------------------------


class TestTenantContext_Issue1265_PersistEvent:
    def test_persist_event_sets_tenant_context_before_advisory_lock(self):
        session = FakeSession()
        session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        evt = _make_event()
        store.persist_event(evt)

        set_idx = _first_call_containing(session, "SET LOCAL app.tenant_id")
        lock_idx = _first_call_containing(session, "pg_advisory_xact_lock")
        assert set_idx is not None, (
            "persist_event must set the RLS tenant context (#1265)"
        )
        assert lock_idx is not None, "advisory lock call should exist"
        assert set_idx < lock_idx, (
            "SET LOCAL app.tenant_id must execute before the first "
            "chain-lock acquisition so every RLS policy evaluated "
            "thereafter has the correct tenant bound"
        )

    def test_persist_event_binds_tenant_id_from_event(self):
        session = FakeSession()
        session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        tid = uuid4()
        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        evt = _make_event(tenant_id=tid)
        store.persist_event(evt)

        set_params = _set_tenant_context_params(session)
        assert set_params, "no SET LOCAL app.tenant_id call was issued"
        # The writer binds str(tenant_id) under the :tid key.
        assert set_params[0].get("tid") == str(tid), (
            f"GUC bound to wrong tenant: expected {tid}, "
            f"got {set_params[0].get('tid')!r}"
        )


# ---------------------------------------------------------------------------
# #1265 — persist_events_batch: GUC set + single-tenant invariant
# ---------------------------------------------------------------------------


class TestTenantContext_Issue1265_PersistEventsBatch:
    def test_batch_sets_tenant_context_before_advisory_lock(self):
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        tid = uuid4()
        store.persist_events_batch([_make_event(tenant_id=tid)])

        set_idx = _first_call_containing(session, "SET LOCAL app.tenant_id")
        lock_idx = _first_call_containing(session, "pg_advisory_xact_lock")
        assert set_idx is not None, "batch must set RLS tenant context (#1265)"
        assert set_idx < lock_idx, "GUC must be set before chain-lock acquisition"

    def test_batch_rejects_mixed_tenant_events(self):
        """A batch spanning two tenants would pin the GUC to one tenant
        and then write rows as the other — silent cross-tenant write.
        The writer fails loud instead."""
        session = FakeSession()
        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        evt_a = _make_event(tenant_id=uuid4(), idemp_key="a")
        evt_b = _make_event(tenant_id=uuid4(), idemp_key="b")

        with pytest.raises(ValueError, match="single-tenant batch"):
            store.persist_events_batch([evt_a, evt_b])

        # And no GUC / no chain write should have been issued — invariant
        # is checked before any SQL touches the DB.
        assert not any(
            "SET LOCAL app.tenant_id" in sql for sql, _ in session.calls
        ), "must not SET tenant context on invalid batch"
        assert not any(
            "pg_advisory_xact_lock" in sql for sql, _ in session.calls
        ), "must not acquire chain lock on invalid batch"

    def test_batch_empty_returns_without_setting_context(self):
        session = FakeSession()
        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        result = store.persist_events_batch([])
        assert result == []
        assert not any(
            "SET LOCAL app.tenant_id" in sql for sql, _ in session.calls
        ), "empty batch must not issue SET"


# ---------------------------------------------------------------------------
# #1265 — create_ingestion_run sets tenant context before INSERT
# ---------------------------------------------------------------------------


class TestTenantContext_Issue1265_CreateIngestionRun:
    def test_create_ingestion_run_sets_tenant_context_before_insert(self):
        from shared.canonical_event import IngestionRun, IngestionSource

        tid = uuid4()
        run = IngestionRun(
            id=uuid4(),
            tenant_id=tid,
            source_system=IngestionSource.WEBHOOK_API,
            source_file_name="fixture.xml",
            source_file_hash="a" * 64,
            source_file_size=128,
            record_count=1,
            mapper_version="v1",
            schema_version="v1",
            status="processing",
            initiated_by="test",
        )

        session = FakeSession()
        store = CanonicalEventStore(
            session=session, dual_write=False, skip_chain_write=True,
        )
        store.create_ingestion_run(run)

        set_idx = _first_call_containing(session, "SET LOCAL app.tenant_id")
        insert_idx = _first_call_containing(
            session, "INSERT INTO fsma.ingestion_runs"
        )
        assert set_idx is not None, (
            "create_ingestion_run must set RLS tenant context (#1265)"
        )
        assert insert_idx is not None, "INSERT must execute"
        assert set_idx < insert_idx, (
            "SET LOCAL app.tenant_id must execute before INSERT so the "
            "tenant_isolation policy on fsma.ingestion_runs can authorize"
        )

        set_params = _set_tenant_context_params(session)
        assert set_params[0].get("tid") == str(tid)
