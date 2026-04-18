"""
Hardening tests for shared.cte_persistence.CTEPersistence (round 2).

Extends ``test_cte_persistence_hardening.py`` with the residual items
from the April 17 shared-kernel audit:

- #1321 — ``query_events_by_tlc`` did not call ``set_tenant_context``
  before issuing its SELECT, relying solely on the caller having set
  RLS context and on the explicit ``tenant_id = :tid`` predicate.  A
  caller that forgets the context (or a future refactor that drops
  the explicit predicate) can leak cross-tenant rows.

All assertions use the same ``FakeSession`` harness as
``test_cte_persistence_hardening.py`` so no live Postgres is needed.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

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
