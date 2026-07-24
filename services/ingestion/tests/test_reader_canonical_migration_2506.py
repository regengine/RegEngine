"""Equivalence coverage for the #2506 reader migration (second pass).

The #2506 verifier work re-anchored the hash-chain verifier on the
canonical store ``fsma.traceability_events``. This second pass migrates
the *read-coupled* scoring readers that previously counted the legacy
``fsma.cte_events`` table so they read the same source of truth as the
verifier.

Two reader groups are migrated here and proven equivalent:

* ``recall_report._query_scoring_data`` — event count, distinct-TLC
  count, distinct-CTE-type count.
* ``recall_simulations._query_tenant_recall_metrics`` — event count and
  distinct-TLC count.

Equivalence argument (no live DB needed):

During the dual-write migration period the canonical writer keys every
``cte_events`` row to ``traceability_events.event_id`` (legacy
``cte_events.id = str(event.event_id)``), so for any dual-write tenant
the two tables hold row-for-row-identical events. The migrated readers
issue ``COUNT(*)`` / ``COUNT(DISTINCT ...)`` over columns
(``traceability_lot_code``, ``event_type``) that are byte-identical on
both tables and apply no status filter (matching the prior behavior of
counting every legacy row). Therefore, given the same underlying data,
the canonical query returns the *same scalar* the legacy query returned,
and the reader's output dict is unchanged.

These tests assert BOTH halves of that argument:
  1. The migrated SQL now targets ``fsma.traceability_events`` (the
     repoint actually happened) and no longer references
     ``fsma.cte_events`` for the migrated counts.
  2. Fed the count scalars a dual-write tenant would have in *either*
     table, the migrated reader produces the exact output it produced
     pre-migration from the legacy table (golden output unchanged).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import (
    recall_report as rr,  # noqa: E402
    recall_simulations as rs,  # noqa: E402
)

# ---------------------------------------------------------------------------
# Recording fake sessions
# ---------------------------------------------------------------------------


class _RecordingScalarSession:
    """Records every SQL string and serves scalars by SQL-substring route."""

    def __init__(self, route: dict[str, object]):
        self.route = route
        self.sqls: list[str] = []
        self.closed = False

    def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())  # normalize whitespace
        self.sqls.append(sql)
        for pat, value in self.route.items():
            if pat in sql:
                return SimpleNamespace(scalar=lambda v=value: v)
        return SimpleNamespace(scalar=lambda: None)

    def close(self):
        self.closed = True


class _OrderedScalarSession:
    """Pops the next scalar per execute() and records SQL (positional)."""

    def __init__(self, scalars: list):
        self._scalars = list(scalars)
        self.sqls: list[str] = []
        self.closed = False

    def execute(self, stmt, params=None):
        self.sqls.append(" ".join(str(stmt).split()))
        value = self._scalars.pop(0) if self._scalars else 0
        return SimpleNamespace(scalar=lambda v=value: v)

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# recall_report._query_scoring_data
# ---------------------------------------------------------------------------


class TestRecallReportRepointedToCanonical:
    def _run(self, monkeypatch, session):
        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)
        return rr._query_scoring_data("tenant-x")

    def test_migrated_counts_query_canonical_not_legacy(self, monkeypatch):
        session = _RecordingScalarSession(
            {
                "COUNT(*) FROM fsma.traceability_events": 12,
                "COUNT(DISTINCT traceability_lot_code) FROM fsma.traceability_events": 5,
                "COUNT(DISTINCT event_type) FROM fsma.traceability_events": 3,
                "COUNT(*) FROM fsma.fda_export_log": 1,
                "COUNT(*) FROM fsma.tenant_suppliers": 7,
                "COUNT(*) FROM fsma.hash_chain": 12,
                "MAX(sequence_num)": 12,
            }
        )
        data = self._run(monkeypatch, session)

        assert data is not None
        # The three migrated counts now hit the canonical store.
        canonical_count_sqls = [s for s in session.sqls if "fsma.traceability_events" in s and "COUNT" in s]
        assert len(canonical_count_sqls) == 3
        # And NONE of the migrated count queries touch the legacy table.
        legacy_count_sqls = [s for s in session.sqls if "fsma.cte_events" in s]
        assert legacy_count_sqls == []

    def test_golden_output_unchanged_under_dual_write_identity(self, monkeypatch):
        # For a dual-write tenant the legacy and canonical tables hold the
        # same rows, so the same scalars flow through either query. Feeding
        # the canonical-routed query the scalars a 50-event tenant would
        # have must reproduce the pre-migration output dict exactly.
        session = _RecordingScalarSession(
            {
                "COUNT(*) FROM fsma.traceability_events": 50,
                "COUNT(DISTINCT traceability_lot_code) FROM fsma.traceability_events": 8,
                "COUNT(DISTINCT event_type) FROM fsma.traceability_events": 4,
                "COUNT(*) FROM fsma.fda_export_log": 3,
                "COUNT(*) FROM fsma.tenant_suppliers": 12,
                "COUNT(*) FROM fsma.hash_chain": 50,
                "MAX(sequence_num)": 55,
            }
        )
        data = self._run(monkeypatch, session)

        # Golden output: identical to what the legacy reader produced for
        # the same 50-event / 8-TLC / 4-type tenant (see
        # test_recall_report_1342.TestQueryScoringData.test_happy_path_with_gaps).
        assert data == {
            "cte_count": 50,
            "tlc_count": 8,
            "cte_types": 4,
            "has_export": True,
            "supplier_count": 12,
            "chain_length": 50,
            "chain_gap_count": 5,  # 55 - 50
        }
        assert session.closed is True


# ---------------------------------------------------------------------------
# recall_simulations._query_tenant_recall_metrics
# ---------------------------------------------------------------------------


class TestRecallSimulationsRepointedToCanonical:
    def _run(self, monkeypatch, session):
        import shared.database as db_mod

        monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)
        return rs._query_tenant_recall_metrics("tenant-x")

    def test_event_and_tlc_counts_query_canonical(self, monkeypatch):
        # Order: cte_count, supplier_count, tlc_count, has_export.
        session = _OrderedScalarSession([5, 2, 3, 1])
        self._run(monkeypatch, session)

        # The COUNT(*) and the distinct-TLC count now read canonical.
        assert "COUNT(*) FROM fsma.traceability_events" in session.sqls[0]
        tlc_sql = session.sqls[2]
        assert "COUNT(DISTINCT traceability_lot_code) FROM fsma.traceability_events" in tlc_sql
        assert "fsma.cte_events" not in session.sqls[0]
        assert "fsma.cte_events" not in tlc_sql

    def test_supplier_count_reads_tenant_suppliers(self, monkeypatch):
        # Suppliers are counted from fsma.tenant_suppliers (#2599) — the
        # event tables have no supplier_id column, so neither legacy nor
        # canonical may appear in this query.
        session = _OrderedScalarSession([5, 2, 3, 1])
        self._run(monkeypatch, session)
        supplier_sql = session.sqls[1]
        assert "fsma.tenant_suppliers" in supplier_sql
        assert "supplier_id" not in supplier_sql
        assert "fsma.cte_events" not in supplier_sql
        assert "fsma.traceability_events" not in supplier_sql

    def test_golden_output_unchanged_under_dual_write_identity(self, monkeypatch):
        # Same scalars a dual-write tenant has in either table → identical
        # output dict to the pre-migration legacy reader (see
        # test_recall_simulations_1342.test_returns_aggregated_metrics_when_ctes_exist).
        session = _OrderedScalarSession([5, 2, 3, 1])
        result = self._run(monkeypatch, session)
        assert result == {
            "cte_count": 5,
            "supplier_count": 2,
            "tlc_count": 3,
            "has_export": True,
        }
        assert session.closed is True
