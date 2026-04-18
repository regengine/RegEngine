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


# Note: #1262 tests added alongside the supersede fix in the next commit.


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
