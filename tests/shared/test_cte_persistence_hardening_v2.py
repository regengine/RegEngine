"""
Hardening tests for shared.cte_persistence.CTEPersistence (round 2).

Extends ``test_cte_persistence_hardening.py`` with the residual items
from the April 17 shared-kernel audit:

- #1321 — ``query_events_by_tlc`` did not call ``set_tenant_context``
  before issuing its SELECT, relying solely on the caller having set
  RLS context and on the explicit ``tenant_id = :tid`` predicate.
  Locked in: every call path to ``query_events_by_tlc`` issues
  ``SET LOCAL app.tenant_id`` before the SELECT.

- #1322 — ``_expand_tlcs_via_transformation_links`` hard-coded the
  recursion depth at 5 in the signature and swallowed every
  ``Exception`` with a ``DEBUG`` log.  Now:
    * ``max_depth`` is a kwarg on ``query_events_by_tlc`` and
      ``_expand_tlcs_via_transformation_links`` via the class-level
      ``DEFAULT_TRAVERSAL_DEPTH``.
    * Only ``ProgrammingError`` (table missing) and
      ``OperationalError`` (DB unavailable) are caught; other
      exceptions propagate so real bugs are loud.

- #1336 — ``test_cte_persistence_hardening.py`` never exercised:
    * Batch quantity clamp negative-path (extremely small sub-unit)
    * Orphan-chain degradation (chain INSERT must not run if the
      cte_events INSERT ON CONFLICT-DO-NOTHING'd)
    * Future-date rejection across the batch path
    * JSONB round-trip for a list-typed KDE value

All assertions use the same ``FakeSession`` harness as
``test_cte_persistence_hardening.py`` so no live Postgres is needed.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from sqlalchemy.exc import OperationalError, ProgrammingError

from shared.cte_persistence.core import CTEPersistence


# ---------------------------------------------------------------------------
# Minimal fake session — same shape as the original hardening tests
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
    def __init__(self):
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
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

    def rollback(self):
        self.calls.append(("__ROLLBACK__", {}))


# ---------------------------------------------------------------------------
# Shared-kernel #1321 — tenant context is set before the TLC query
# ---------------------------------------------------------------------------


class TestTenantContext_Issue1321:
    def test_query_events_by_tlc_sets_tenant_context_before_select(self):
        """The SET LOCAL app.tenant_id must be the FIRST DB call, so
        the subsequent SELECT is bounded by RLS even if the explicit
        predicate is removed by a future refactor."""
        session = FakeSession()
        session.add_rule(r"SELECT DISTINCT tlc FROM tlc_graph", _FakeResult(rows=[("TLC-1",)]))
        session.add_rule(r"FROM fsma\.cte_events", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        p.query_events_by_tlc(tenant_id="t-1", tlc="TLC-1")

        # The set_tenant_context SQL must appear in the call log and
        # precede any fsma.cte_events SELECT.
        set_calls = [
            i for i, (sql, _) in enumerate(session.calls)
            if "SET LOCAL app.tenant_id" in sql
        ]
        select_calls = [
            i for i, (sql, _) in enumerate(session.calls)
            if "FROM fsma.cte_events" in sql
        ]
        assert set_calls, "query_events_by_tlc must SET LOCAL app.tenant_id"
        assert select_calls, "query_events_by_tlc must SELECT from fsma.cte_events"
        assert set_calls[0] < select_calls[0], (
            "tenant context must be set BEFORE the cte_events SELECT"
        )

    def test_query_events_by_tlc_passes_tenant_to_session_setting(self):
        """The bound tenant_id parameter on the SET LOCAL must match
        the caller's tenant_id — not a hard-coded default."""
        session = FakeSession()
        session.add_rule(r"SELECT DISTINCT tlc FROM tlc_graph", _FakeResult(rows=[("TLC-1",)]))
        session.add_rule(r"FROM fsma\.cte_events", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        p.query_events_by_tlc(tenant_id="t-abc-123", tlc="TLC-1")

        set_calls = [
            (sql, params) for sql, params in session.calls
            if "SET LOCAL app.tenant_id" in sql
        ]
        assert set_calls
        _, params = set_calls[0]
        assert params["tid"] == "t-abc-123"

    def test_explicit_tenant_id_predicate_retained_as_defense_in_depth(self):
        """Even with RLS set, the explicit tenant_id = :tid WHERE must
        still be in the SELECT — so that a drift in RLS config does not
        silently open a cross-tenant read."""
        session = FakeSession()
        session.add_rule(r"SELECT DISTINCT tlc FROM tlc_graph", _FakeResult(rows=[("TLC-1",)]))
        session.add_rule(r"FROM fsma\.cte_events", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        p.query_events_by_tlc(tenant_id="t-1", tlc="TLC-1")

        select_sql = next(
            sql for sql, _ in session.calls if "FROM fsma.cte_events" in sql
        )
        assert "tenant_id = :tid" in select_sql


# ---------------------------------------------------------------------------
# Shared-kernel #1322 — max_depth parameterized, narrow exception handling
# ---------------------------------------------------------------------------


class TestTraversalDepth_Issue1322:
    def test_default_traversal_depth_is_class_attribute(self):
        """The default depth must be a class attribute so tests and
        ops can override without patching method signatures."""
        assert hasattr(CTEPersistence, "DEFAULT_TRAVERSAL_DEPTH")
        assert CTEPersistence.DEFAULT_TRAVERSAL_DEPTH == 5

    def test_query_events_by_tlc_accepts_max_depth_kwarg(self):
        """max_depth must be forwarded to the recursive CTE's
        :max_depth bind parameter so a caller can expand or limit a
        trace without editing the persistence layer."""
        session = FakeSession()
        session.add_rule(r"SELECT DISTINCT tlc FROM tlc_graph", _FakeResult(rows=[("TLC-1",)]))
        session.add_rule(r"FROM fsma\.cte_events", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        p.query_events_by_tlc(tenant_id="t-1", tlc="TLC-1", max_depth=12)

        # Find the recursive CTE call and assert the bound depth.
        cte_calls = [
            (sql, params) for sql, params in session.calls
            if "RECURSIVE tlc_graph" in sql
        ]
        assert cte_calls
        _, params = cte_calls[0]
        assert params["max_depth"] == 12

    def test_negative_depth_is_rejected(self):
        """Passing depth < 0 must raise ValueError rather than issue
        a nonsense WHERE depth < -1 that returns an empty graph."""
        session = FakeSession()
        p = CTEPersistence(session=session)
        with pytest.raises(ValueError, match="depth must be"):
            p._expand_tlcs_via_transformation_links(
                tenant_id="t-1", seed_tlc="TLC-1", depth=-1,
            )

    def test_programming_error_degrades_to_seed_tlc_only(self):
        """If the transformation_links table is missing the traversal
        must return [seed_tlc] instead of raising — graceful
        degradation for fresh-DB bootstrapping."""
        session = FakeSession()

        def _raise_programming(sql, params):
            raise ProgrammingError("stmt", {}, Exception("table missing"))

        session.add_rule(r"RECURSIVE tlc_graph", _raise_programming)

        p = CTEPersistence(session=session)
        result = p._expand_tlcs_via_transformation_links(
            tenant_id="t-1", seed_tlc="TLC-X",
        )
        assert result == ["TLC-X"]

    def test_operational_error_degrades_to_seed_tlc_only(self):
        """Transient DB connectivity errors also degrade to seed-only;
        we do not want one dead replica to DoS FDA export."""
        session = FakeSession()

        def _raise_operational(sql, params):
            raise OperationalError("stmt", {}, Exception("conn refused"))

        session.add_rule(r"RECURSIVE tlc_graph", _raise_operational)

        p = CTEPersistence(session=session)
        result = p._expand_tlcs_via_transformation_links(
            tenant_id="t-1", seed_tlc="TLC-X",
        )
        assert result == ["TLC-X"]

    def test_unexpected_exception_propagates(self):
        """Regression guard against the original bare ``except
        Exception`` clause that silently returned [seed_tlc] for any
        error.  A programmer bug (ValueError, AttributeError, etc.)
        must NOT be swallowed — it should fail loud in tests and in
        prod."""
        session = FakeSession()

        def _raise_runtime(sql, params):
            raise RuntimeError("programmer bug")

        session.add_rule(r"RECURSIVE tlc_graph", _raise_runtime)

        p = CTEPersistence(session=session)
        with pytest.raises(RuntimeError):
            p._expand_tlcs_via_transformation_links(
                tenant_id="t-1", seed_tlc="TLC-X",
            )


# ---------------------------------------------------------------------------
# Shared-kernel #1336 — gaps in prior hardening test coverage
# ---------------------------------------------------------------------------


def _base_batch_event(**overrides):
    evt = {
        "event_type": "harvesting",
        "traceability_lot_code": "TLC-1",
        "product_description": "Lettuce",
        "quantity": 10.0,
        "unit_of_measure": "kg",
        "event_timestamp": "2026-04-15T12:00:00Z",
        "kdes": {"farm_name": "Acme"},
    }
    evt.update(overrides)
    return evt


class TestBatchQuantityClamp_Issue1336:
    def test_batch_tiny_sub_unit_quantity_preserved(self):
        """Even values < 0.01 (e.g., kilogram-level loss accounting)
        must be preserved — no silent clamp to 1.0 for the batch
        path.  Locking in that sub-unit measurements keep their
        precision through hash and storage."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        evt = _base_batch_event(quantity=0.001)
        results = p.store_events_batch(tenant_id="t-1", events=[evt])

        assert results and results[0].success
        cte_inserts = [c for c in session.calls if "INSERT INTO fsma.cte_events" in c[0]]
        assert cte_inserts
        _, params = cte_inserts[0]
        qty_params = [v for k, v in params.items() if k.startswith("qty_")]
        assert qty_params, "quantity bind parameters must be present"
        assert all(v == 0.001 for v in qty_params)

    def test_batch_negative_quantity_rejected(self):
        """Negative quantities are nonsensical for food traceability —
        batch path must reject them same as the single-event path."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        evt = _base_batch_event(quantity=-1.0)
        with pytest.raises(ValueError, match="quantity must be > 0"):
            p.store_events_batch(tenant_id="t-1", events=[evt])


class TestOrphanChain_Issue1336:
    def test_chain_insert_guarded_by_where_exists(self):
        """If a batch event was idempotent (ON CONFLICT DO NOTHING
        skipped the INSERT), its chain row must ALSO be skipped — the
        WHERE EXISTS guard enforces this.  We assert that every
        hash_chain INSERT the batch path emits carries the guard,
        which is the #1307 fix extended to cover the batch-orphan
        intersection (#1336)."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        evt = _base_batch_event()
        p.store_events_batch(tenant_id="t-1", events=[evt])

        chain_inserts = [c for c in session.calls if "INSERT INTO fsma.hash_chain" in c[0]]
        for sql, _ in chain_inserts:
            normalized = " ".join(sql.split()).upper()
            assert "WHERE EXISTS" in normalized


class TestFutureDate_Issue1336:
    def test_batch_far_future_event_timestamp_rejected(self):
        """The batch path must reject timestamps more than the
        allowed drift window into the future — a poisoned input
        should not be able to claim "ingested at 2100-01-01" and
        distort trace queries or retention math."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        future = (datetime.now(timezone.utc) + timedelta(days=365 * 5)).isoformat()
        with pytest.raises(ValueError, match="future"):
            p.store_events_batch(
                tenant_id="t-1", events=[_base_batch_event(event_timestamp=future)]
            )


class TestBatchKdeJsonb_Issue1336:
    @staticmethod
    def _has_jsonb_cast(sql: str) -> bool:
        return "::jsonb" in sql or "AS jsonb" in sql

    def test_batch_list_kde_round_trips_as_jsonb(self):
        """A list-typed KDE value (e.g., input_lot_codes=["TLC-A",
        "TLC-B"]) must be stored as JSON text cast to jsonb, NOT as
        "['TLC-A', 'TLC-B']" (the Python repr).  The single-event
        path was covered by #1311; this locks in the batch path
        (#1336)."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        p = CTEPersistence(session=session)
        evt = _base_batch_event(
            event_type="transformation",
            kdes={"input_lot_codes": ["TLC-A", "TLC-B"], "process_type": "cut"},
        )
        p.store_events_batch(tenant_id="t-1", events=[evt])

        kde_inserts = [c for c in session.calls if "INSERT INTO fsma.cte_kdes" in c[0]]
        assert kde_inserts
        sql, params = kde_inserts[0]
        assert self._has_jsonb_cast(sql)

        # Find the bound kde_value params and assert they are JSON
        # text (not Python repr).  Python repr would start with "[" +
        # single quotes.
        kv_params = [v for k, v in params.items() if k.startswith("kv_")]
        assert kv_params
        for v in kv_params:
            assert isinstance(v, str)
            # JSON text uses double-quotes for strings; python repr
            # uses single-quotes.  A bare ``["TLC-A","TLC-B"]`` is
            # valid JSON; ``['TLC-A', 'TLC-B']`` is not.
            assert "'TLC-A'" not in v, (
                f"KDE value should be JSON text, got python repr: {v!r}"
            )
