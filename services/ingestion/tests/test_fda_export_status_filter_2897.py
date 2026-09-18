"""Regression tests for #2897 — FDA export readers must apply a lifecycle-status filter.

``services/shared/cte_persistence/writes.py`` states the invariant verbatim:
an event with ``validation_status='rejected'`` "must NOT be written to the
hash chain or included in FDA export / graph sync queries".  The canonical
store adds a second non-exportable state: ``status='superseded'`` — the
pre-correction version of an amended event, which
``canonical_persistence/writer.py`` deliberately leaves in place.

Before this fix all three FDA-export WHERE-clause builders filtered on
tenant / product / location / TLC / event type / date and nothing else, so
both classes of non-exportable row were emitted into regulator-facing
CSV and ZIP packages:

* ``build_recall_where_clause``            → ``/export/recall`` (legacy store)
* ``build_recall_where_clause_canonical``  → ``/export/recall`` (canonical store)
* ``build_v2_where_clause``                → ``/export/v2``

The sibling readers used by ``/export/all``
(``services/shared/cte_persistence/queries.py`` lines 255 and 507) and the
trace-graph reader in this very module already carried the predicate, so the
two export families disagreed on the same invariant.

These tests pin the predicate in each builder AND assert it survives into the
SQL the fetchers actually execute, so the gap cannot be reintroduced by
either half of a builder/fetcher pair.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from services.ingestion.app.fda_export.queries import (  # noqa: E402
    build_recall_where_clause,
    build_recall_where_clause_canonical,
    build_v2_where_clause,
    fetch_recall_events,
    fetch_recall_events_canonical,
    fetch_v2_events,
)

# The legacy ``fsma.cte_events`` lifecycle column (V002 line 84,
# CHECK domain {'valid','rejected','warning'}). ``warning`` events are
# exportable — only ``rejected`` is chain-less and KDE-less.
LEGACY_PREDICATE = "e.validation_status != 'rejected'"

# The canonical ``fsma.traceability_events`` lifecycle column (V043 lines
# 129-130, CHECK domain {'active','superseded','rejected','draft'}). Only
# ``active`` is the current, exportable head of an amendment chain.
CANONICAL_PREDICATE = "e.status = 'active'"


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """Captures the SQL text each fetcher hands to the driver."""

    def __init__(self):
        self.executes: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        self.executes.append((str(statement), params))
        return _Result([])


# ---------------------------------------------------------------------------
# build_recall_where_clause — legacy /export/recall reader
# ---------------------------------------------------------------------------


class TestRecallLegacyStatusFilter:
    def test_base_clause_excludes_rejected(self):
        where, _params = build_recall_where_clause("t", None, None, None, None, None, None)
        assert LEGACY_PREDICATE in where

    def test_predicate_survives_every_filter_combination(self):
        where, _params = build_recall_where_clause("t", "Prod", "Loc", "TLC", "shipping", "2026-04-01", "2026-04-10")
        assert LEGACY_PREDICATE in where

    def test_predicate_is_literal_not_parameterized(self):
        """No bind param a caller could override to re-admit rejected rows."""
        _where, params = build_recall_where_clause("t", None, None, None, None, None, None)
        assert "rejected" not in {str(v) for v in params.values()}

    def test_predicate_reaches_executed_sql(self):
        where, params = build_recall_where_clause("t", None, None, None, None, None, None)
        session = _FakeSession()
        fetch_recall_events(session, where, params)
        sql = session.executes[0][0]
        assert LEGACY_PREDICATE in sql


# ---------------------------------------------------------------------------
# build_recall_where_clause_canonical — canonical /export/recall reader
# ---------------------------------------------------------------------------


class TestRecallCanonicalStatusFilter:
    def test_base_clause_restricts_to_active(self):
        where, _params = build_recall_where_clause_canonical("t", None, None, None, None, None, None)
        assert CANONICAL_PREDICATE in where

    def test_predicate_survives_every_filter_combination(self):
        where, _params = build_recall_where_clause_canonical(
            "t", "Prod", "Loc", "TLC", "shipping", "2026-04-01", "2026-04-10"
        )
        assert CANONICAL_PREDICATE in where

    def test_predicate_reaches_executed_sql(self):
        where, params = build_recall_where_clause_canonical("t", None, None, None, None, None, None)
        session = _FakeSession()
        fetch_recall_events_canonical(session, where, params)
        sql = session.executes[0][0]
        assert CANONICAL_PREDICATE in sql


# ---------------------------------------------------------------------------
# build_v2_where_clause — /export/v2 canonical reader
# ---------------------------------------------------------------------------


class TestV2StatusFilter:
    def test_base_clause_restricts_to_active(self):
        where, _params = build_v2_where_clause("t", None, None, None, None)
        assert CANONICAL_PREDICATE in where

    def test_predicate_survives_every_filter_combination(self):
        where, _params = build_v2_where_clause("t", "TLC-ABC", "shipping", "2026-04-01", "2026-04-10")
        assert CANONICAL_PREDICATE in where

    def test_predicate_reaches_executed_sql(self):
        where, params = build_v2_where_clause("t", None, None, None, None)
        session = _FakeSession()
        fetch_v2_events(session, where, params)
        sql = session.executes[0][0]
        assert CANONICAL_PREDICATE in sql

    def test_amended_lot_excludes_superseded_and_draft(self):
        """``status = 'active'`` is the only predicate that drops all three
        non-exportable canonical states, so an amended lot appears exactly
        once (as its active correction) rather than twice."""
        where, _params = build_v2_where_clause("t", "TLC-ABC", None, None, None)
        assert CANONICAL_PREDICATE in where
        # A ``!= 'rejected'`` style predicate would leave superseded/draft in.
        assert "!= 'rejected'" not in where


# ---------------------------------------------------------------------------
# Lockstep: no export reader may ship without a lifecycle-status predicate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("builder", "args", "predicate"),
    [
        (build_recall_where_clause, ("t", None, None, None, None, None, None), LEGACY_PREDICATE),
        (
            build_recall_where_clause_canonical,
            ("t", None, None, None, None, None, None),
            CANONICAL_PREDICATE,
        ),
        (build_v2_where_clause, ("t", None, None, None, None), CANONICAL_PREDICATE),
    ],
    ids=["recall_legacy", "recall_canonical", "v2"],
)
def test_every_export_clause_builder_pins_a_status_predicate(builder, args, predicate):
    where, _params = builder(*args)
    assert predicate in where, f"{builder.__name__} emits non-exportable events into an FDA package"
