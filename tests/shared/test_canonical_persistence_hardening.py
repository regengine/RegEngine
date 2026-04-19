"""
Hardening tests for shared.canonical_persistence.CanonicalEventStore.

Exercises the fixes for:
- #1251 — hash chain race: per-tenant advisory lock taken at entry
- #1252 — ON CONFLICT idempotency: first-writer wins, loser returns idempotent
- #1254 — parameterized SQL in query_events_by_tlc (no f-string injection)
- #1262 — supersede collapsed to a single UPDATE ... RETURNING (idempotent)

These tests mock the SQLAlchemy session; they assert on SQL text and
parameters so we do not require a live Postgres instance.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from shared.canonical_persistence.writer import CanonicalEventStore


# ---------------------------------------------------------------------------
# Minimal fake session that records every executed SQL text + params
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: List[Tuple[Any, ...]] | None = None, scalar: Any = None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar


class FakeSession:
    """Collects every `execute()` call.  Supports scripted responses keyed by
    regex match against the SQL text."""

    def __init__(self):
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        # Each rule is (pattern, _FakeResult or callable(sql, params) -> _FakeResult)
        self._rules: List[Tuple[re.Pattern[str], Any]] = []

    def add_rule(self, pattern: str, result):
        self._rules.append((re.compile(pattern, re.IGNORECASE | re.DOTALL), result))

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))
        for pat, result in self._rules:
            if pat.search(sql):
                if callable(result):
                    return result(sql, params or {})
                return result
        return _FakeResult()

    def begin_nested(self):
        ns = MagicMock()
        ns.rollback = MagicMock()
        return ns


def _make_event(event_id=None, tenant_id=None, idemp_key="idem-key-1"):
    """Construct a minimal TraceabilityEvent-compatible stub with only the
    attributes the writer touches."""
    from shared.canonical_event import (
        CTEType,
        EventStatus,
        IngestionSource,
        ProvenanceMetadata,
        TraceabilityEvent,
    )

    prov = ProvenanceMetadata()

    evt = TraceabilityEvent(
        event_id=event_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        source_system=IngestionSource.WEBHOOK_API,
        source_record_id="rec-1",
        event_type=CTEType.SHIPPING,
        event_timestamp=datetime.now(timezone.utc),
        event_timezone="UTC",
        product_reference="urn:gs1:01:09506000134352",
        lot_reference="LOT-1",
        traceability_lot_code="TLC-1",
        quantity=10.0,
        unit_of_measure="kg",
        from_entity_reference="urn:gs1:417:0614141000005",
        to_entity_reference="urn:gs1:417:0614141000012",
        from_facility_reference="urn:gs1:414:0614141000005",
        to_facility_reference="urn:gs1:414:0614141000012",
        kdes={"gtin": "09506000134352"},
        raw_payload={"k": "v"},
        normalized_payload={},
        provenance_metadata=prov,
        confidence_score=1.0,
        status=EventStatus.ACTIVE,
        idempotency_key=idemp_key,
    )
    if hasattr(evt, "prepare_for_persistence"):
        evt.prepare_for_persistence()
    return evt


# ---------------------------------------------------------------------------
# #1251 — advisory lock is acquired before any chain read
# ---------------------------------------------------------------------------


class TestAdvisoryLock_Issue1251:
    def test_persist_event_acquires_advisory_lock_before_chain_read(self):
        session = FakeSession()
        # Idempotency SELECT returns nothing (new event)
        session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
        # Chain head returns no rows (genesis)
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        evt = _make_event()
        store.persist_event(evt)

        # Find the advisory lock call and assert it came before any chain-head SELECT
        lock_idx = next(
            (i for i, c in enumerate(session.calls) if "pg_advisory_xact_lock" in c[0]),
            None,
        )
        chain_idx = next(
            (i for i, c in enumerate(session.calls) if "FROM fsma.hash_chain" in c[0]),
            None,
        )
        assert lock_idx is not None, "advisory lock must be acquired"
        assert chain_idx is not None, "chain head must be read"
        assert lock_idx < chain_idx, "lock must precede chain read"

    def test_persist_events_batch_acquires_advisory_lock(self):
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        evt = _make_event()
        store.persist_events_batch([evt])

        assert any("pg_advisory_xact_lock" in c[0] for c in session.calls), (
            "batch path must also acquire the advisory lock"
        )

    def test_advisory_lock_is_keyed_by_tenant(self):
        session = FakeSession()
        session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        evt = _make_event()
        store.persist_event(evt)

        lock_calls = [c for c in session.calls if "pg_advisory_xact_lock" in c[0]]
        assert lock_calls, "lock call expected"
        sql, params = lock_calls[0]
        assert "hashtext(:tid)" in sql
        assert params["tid"] == str(evt.tenant_id)


# ---------------------------------------------------------------------------
# #1262 — supersede uses a single UPDATE (no pre-check race window)
# ---------------------------------------------------------------------------


class TestSupersedeNoPreCheck_Issue1262:
    def test_supersede_does_not_issue_separate_status_select(self):
        """No pre-flight ``SELECT status`` on traceability_events: the UPDATE
        itself filters ``status='active'`` and returning zero rows is the
        idempotent signal."""
        session = FakeSession()
        session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        # Fake the supersede UPDATE returning one row (success)
        session.add_rule(
            r"UPDATE fsma\.traceability_events\s+SET status = 'superseded'",
            _FakeResult(rows=[("active",)]),
        )

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        evt = _make_event()
        evt.supersedes_event_id = uuid4()
        store.persist_event(evt)

        # The new code must not issue a `SELECT status FROM fsma.traceability_events`
        # — that check-then-update pattern is the race this fixes.
        preselects = [
            c for c in session.calls
            if "SELECT status FROM fsma.traceability_events" in c[0].replace("\n", " ")
        ]
        assert not preselects, (
            "race-prone pre-check SELECT must be removed — the UPDATE RETURNING is the source of truth"
        )

    def test_supersede_already_superseded_is_idempotent(self):
        """When the UPDATE returns zero rows (target already superseded or
        missing), persist_event must not raise ValueError — the race-loser
        simply proceeds without mutating the target row."""
        session = FakeSession()
        session.add_rule(r"SELECT event_id, sha256_hash, chain_hash", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        # UPDATE RETURNING returns no rows — the row was already superseded
        session.add_rule(
            r"UPDATE fsma\.traceability_events\s+SET status = 'superseded'",
            _FakeResult(rows=[]),
        )

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        evt = _make_event()
        evt.supersedes_event_id = uuid4()

        # Must not raise
        result = store.persist_event(evt)
        assert result.success is True


# ---------------------------------------------------------------------------
# #1254 — query_events_by_tlc builds SQL from static literals only
# ---------------------------------------------------------------------------


class TestParameterizedSQL_Issue1254:
    def test_query_events_by_tlc_uses_only_literal_predicates(self):
        session = FakeSession()
        session.add_rule(r"FROM fsma\.traceability_events", _FakeResult(rows=[]))

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        store.query_events_by_tlc(
            tenant_id="11111111-1111-1111-1111-111111111111",
            tlc="TLC-INJECTION'; DROP TABLE fsma.traceability_events; --",
            start_date="2026-01-01",
            end_date="2026-04-01",
        )
        assert session.calls, "query should have executed"
        sql, params = session.calls[-1]
        # TLC string from the user must appear only as a bound parameter —
        # never interpolated into SQL text.
        assert "DROP TABLE" not in sql
        assert params.get("tlc", "").startswith("TLC-INJECTION")

    def test_query_events_by_tlc_hardcodes_static_where_clauses(self):
        """All WHERE predicates must be drawn from a fixed whitelist of
        literal strings — no user input is ever concatenated into the SQL
        text."""
        session = FakeSession()
        session.add_rule(r"FROM fsma\.traceability_events", _FakeResult(rows=[]))

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        store.query_events_by_tlc(tenant_id="t", tlc="T")
        sql, _ = session.calls[-1]
        # Sanity: each predicate uses a bound parameter
        assert ":tid" in sql
        assert ":tlc" in sql

    def test_query_events_by_tlc_identical_sql_regardless_of_date_filters(self):
        """Both date filters absent vs. both present must generate the same
        SQL text — only bind-param values change.  This proves there's no
        dynamic predicate assembly left."""
        session = FakeSession()
        session.add_rule(r"FROM fsma\.traceability_events", _FakeResult(rows=[]))

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        store.query_events_by_tlc(tenant_id="t", tlc="T")
        sql_none, _ = session.calls[-1]

        store.query_events_by_tlc(
            tenant_id="t", tlc="T",
            start_date="2026-01-01", end_date="2026-04-01",
        )
        sql_both, _ = session.calls[-1]

        assert sql_none == sql_both, (
            "SQL text must be identical regardless of filter values — "
            "dynamic predicates are the injection vector this fix removes"
        )

    def test_batch_idempotency_check_uses_expanding_bindparam(self):
        """The batch SELECT must not build placeholder names via f-string;
        it should use SQLAlchemy's ``bindparam(expanding=True)`` which
        generates ``IN (...)`` safely at prepare-time."""
        session = FakeSession()
        # The prepared SQL should contain `IN :keys`, not `IN (:k0, :k1, ...)`
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        # Single-tenant batch invariant (#1265): both events must carry
        # the same tenant_id, else the writer raises by design.
        shared_tid = uuid4()
        evt_a = _make_event(tenant_id=shared_tid, idemp_key="a")
        evt_b = _make_event(tenant_id=shared_tid, idemp_key="b")
        store.persist_events_batch([evt_a, evt_b])

        idemp_calls = [
            c for c in session.calls
            if "SELECT idempotency_key" in c[0]
        ]
        assert idemp_calls, "batch idempotency SELECT should have been issued"
        sql, params = idemp_calls[0]
        # No per-index placeholders like ":k0"
        assert ":k0" not in sql and ":k1" not in sql, (
            "f-string-built placeholders must be replaced with expanding bindparam"
        )
        assert ":keys" in sql
        # The bind param holds a list (expanding=True)
        assert isinstance(params.get("keys"), list)
        assert len(params["keys"]) == 2


# ---------------------------------------------------------------------------
# #1252 — Idempotent duplicate returns cleanly (no UNIQUE-violation abort)
# ---------------------------------------------------------------------------


class TestIdempotentReturn_Issue1252:
    def test_existing_idempotency_key_short_circuits(self):
        """If the caller's idempotency key already exists, persist_event
        returns ``idempotent=True`` and does NOT attempt an INSERT."""
        session = FakeSession()
        session.add_rule(
            r"SELECT event_id, sha256_hash, chain_hash",
            _FakeResult(rows=[(str(uuid4()), "a" * 64, "b" * 64)]),
        )

        store = CanonicalEventStore(session=session, dual_write=False, skip_chain_write=True)
        evt = _make_event(idemp_key="duplicate-key")
        result = store.persist_event(evt)

        assert result.idempotent is True
        # No INSERT statements were issued for the event
        inserts = [c for c in session.calls if c[0].lstrip().upper().startswith("INSERT") or "INSERT INTO" in c[0].upper()]
        assert not any("INTO fsma.traceability_events" in c[0] for c in inserts)


# ---------------------------------------------------------------------------
# #1263 — complete_ingestion_run UPDATE must scope by tenant_id
# ---------------------------------------------------------------------------


class _RowcountResult(_FakeResult):
    """``_FakeResult`` extension that exposes a ``rowcount`` attribute.

    The fix in ``complete_ingestion_run`` reads ``result.rowcount`` to
    detect "no row matched" and raise ValueError. The bare ``_FakeResult``
    above doesn't carry one because the existing tests don't need it.
    """

    def __init__(self, rowcount: int = 1):
        super().__init__()
        self.rowcount = rowcount


class TestCompleteIngestionRunTenantScope_Issue1263:
    """Regression tests for #1263.

    Prior shape::

        UPDATE fsma.ingestion_runs
        SET ...
        WHERE id = :id

    A caller passing a run_id from another tenant silently mutated that
    tenant's row. RLS is not a backstop because callers of this method do
    not always pre-set ``app.tenant_id`` (the writer's defensive
    ``set_tenant_context`` only fires inside ``persist_event``).
    """

    def _new_store(self, session: FakeSession) -> CanonicalEventStore:
        return CanonicalEventStore(
            session=session,
            dual_write=False,
            skip_chain_write=True,
        )

    def test_update_includes_tenant_id_in_where_clause(self):
        """The UPDATE WHERE clause must filter on tenant_id, not just id."""
        session = FakeSession()
        # Wrap in a result that reports a non-zero rowcount so the
        # method does not raise on its post-update check.
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _RowcountResult(rowcount=1))

        store = self._new_store(session)
        store.complete_ingestion_run(
            run_id="11111111-1111-1111-1111-111111111111",
            tenant_id="22222222-2222-2222-2222-222222222222",
            accepted=10,
            rejected=0,
        )

        update_calls = [c for c in session.calls if "UPDATE fsma.ingestion_runs" in c[0]]
        assert update_calls, "complete_ingestion_run must issue an UPDATE"
        sql, params = update_calls[0]

        assert "tenant_id = :tenant_id" in sql, (
            "#1263: UPDATE WHERE clause must filter by tenant_id so cross-tenant "
            "run_ids cannot mutate another tenant's row. SQL was:\n" + sql
        )
        assert "id = :id" in sql, "id filter must remain alongside the tenant filter"
        assert params["tenant_id"] == "22222222-2222-2222-2222-222222222222"

    def test_update_sets_rls_tenant_context_for_defence_in_depth(self):
        """Defence in depth: also bind the RLS GUC.

        If a future refactor accidentally drops the explicit WHERE
        filter, the RLS policy on fsma.ingestion_runs will still reject
        cross-tenant rows — but only if the GUC is set.
        """
        session = FakeSession()
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _RowcountResult(rowcount=1))

        store = self._new_store(session)
        store.complete_ingestion_run(
            run_id="run-id",
            tenant_id="tenant-id",
            accepted=1,
            rejected=0,
        )

        rls_calls = [c for c in session.calls if "SET LOCAL app.tenant_id" in c[0]]
        assert rls_calls, (
            "complete_ingestion_run must also set RLS context as a "
            "defence-in-depth guard against future refactors"
        )
        # The RLS bind must be the same tenant as the UPDATE bind.
        assert any(p.get("tid") == "tenant-id" for _, p in rls_calls)

    def test_no_row_matched_raises(self):
        """When the UPDATE matches 0 rows, the method must fail loud.

        A spurious silent success here masks bugs (caller using the wrong
        run_id, run was deleted, tenant mismatch). Raise so the caller
        finds out at write time, not when reading stale dashboards.
        """
        session = FakeSession()
        session.add_rule(r"UPDATE fsma\.ingestion_runs", _RowcountResult(rowcount=0))

        store = self._new_store(session)
        with pytest.raises(ValueError, match=r"#1263"):
            store.complete_ingestion_run(
                run_id="nonexistent-or-cross-tenant",
                tenant_id="tenant-id",
                accepted=1,
                rejected=0,
            )

    def test_signature_requires_tenant_id(self):
        """``tenant_id`` must be a required positional argument.

        Locks the API change in: callers can no longer omit tenant_id and
        rely on the prior single-id WHERE.
        """
        import inspect

        sig = inspect.signature(CanonicalEventStore.complete_ingestion_run)
        params = sig.parameters
        assert "tenant_id" in params, (
            "#1263: complete_ingestion_run must accept a `tenant_id` parameter"
        )
        # Required: no default value.
        assert params["tenant_id"].default is inspect.Parameter.empty, (
            "#1263: tenant_id must be required (no default) so callers cannot "
            "accidentally omit it and fall back to an id-only WHERE"
        )
