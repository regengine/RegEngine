"""Data-free query shape, empty-result, and audit failure checks."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fda_export import queries as q  # noqa: E402


class _EmptyResult:
    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _EmptySession:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return _EmptyResult()


class _FailingSession(_EmptySession):
    def __init__(self) -> None:
        super().__init__()
        self.rolled_back = False

    def execute(self, statement, params=None):
        raise RuntimeError("audit write unavailable")

    def rollback(self):
        self.rolled_back = True


def test_iso_date_returns_next_day_midnight_utc() -> None:
    today = date.today()
    bound = datetime.fromisoformat(q._end_bound_utc(today.isoformat()))
    assert bound == datetime.combine(today + timedelta(days=1), datetime.min.time(), timezone.utc)


def test_non_iso_falls_back_to_raw_string() -> None:
    assert q._end_bound_utc("") == ""


def test_empty_result_set_returns_empty_list() -> None:
    session = _EmptySession()
    assert q.fetch_export_log_history(session, "", 0) == []
    assert session.calls[0][1] == {"tid": "", "lim": 0}


def test_empty_rows_returns_zero_total() -> None:
    assert q.format_export_log_rows([], "") == {"tenant_id": "", "exports": [], "total": 0}


def test_tenant_only_base_conditions() -> None:
    clause, params = q.build_recall_where_clause("", None, None, None, None, None, None)
    assert params == {"tid": ""}
    assert "tenant_id = :tid" in clause
    assert "validation_status != 'rejected'" in clause


def test_empty_strings_treated_as_unset() -> None:
    base = q.build_recall_where_clause("", None, None, None, None, None, None)
    assert q.build_recall_where_clause("", "", "", "", "", "", "") == base


def test_canonical_where_excludes_inactive_records() -> None:
    clause, params = q.build_recall_where_clause_canonical("", None, None, None, None, None, None)
    assert params == {"tid": ""}
    assert "e.status = 'active'" in clause


def test_fetch_recall_events_empty_result() -> None:
    session = _EmptySession()
    assert q.fetch_recall_events(session, "e.tenant_id = :tid", {"tid": ""}) == []
    assert session.calls[0][1]["tid"] == ""
    assert "LIMIT :lim" in session.calls[0][0]


def test_rows_to_event_dicts_empty_rows() -> None:
    assert q.rows_to_event_dicts([]) == []
    assert q.v2_rows_to_event_dicts([]) == []


def test_audit_log_write_error_is_runtime_error() -> None:
    assert issubclass(q.AuditLogWriteError, RuntimeError)


def test_recall_audit_db_failure_rolls_back() -> None:
    session = _FailingSession()
    with pytest.raises(q.AuditLogWriteError):
        q.log_recall_export(session, "", [], "", "csv", None, None, None)
    assert session.rolled_back


def test_v2_tenant_only_base() -> None:
    clause, params = q.build_v2_where_clause("", None, None, None, None)
    assert params == {"tid": ""}
    assert "e.status = 'active'" in clause


def test_fetch_v2_events_empty_result() -> None:
    session = _EmptySession()
    assert q.fetch_v2_events(session, "e.tenant_id = :tid", {"tid": ""}) == []
    sql, params = session.calls[0]
    assert params == {"tid": ""}
    assert "evaluation_verdict" in sql
    assert "LIMIT 10001" in sql


def test_trace_with_no_linked_lots_has_no_nodes_or_edges() -> None:
    from shared.cte_persistence.queries import TlcExpansion

    class EmptyPersistence:
        def _expand_tlcs_detailed(self, **kwargs):
            return TlcExpansion(tlcs=[], depth_exhausted=False, direction=kwargs["direction"], max_depth=kwargs["depth"])

    session = _EmptySession()
    graph = q.fetch_trace_graph_data(session, EmptyPersistence(), "", "", 0)
    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["total_events"] == 0
    assert graph["direction"] == "both"
    assert graph["depth_exhausted"] is False
    assert len(session.calls) == 1
    assert "fsma.transformation_links" in session.calls[0][0]


def test_trace_roles_follow_walk_direction_and_report_depth_limit() -> None:
    """S2 (gap analysis 2026-10-28): node roles come from the walk that
    reached the lot, so a lot two hops downstream is ``downstream`` (it used
    to read ``upstream`` because only seed-adjacent edges were checked), and
    reaching the depth limit is surfaced on the response."""
    from shared.cte_persistence.queries import TlcExpansion

    class Persistence:
        def __init__(self):
            self.calls = []

        def _expand_tlcs_detailed(self, **kwargs):
            self.calls.append(kwargs)
            return TlcExpansion(
                tlcs=["SEED", "OUT1", "OUT2", "IN1"],
                depth_exhausted=True,
                direction=kwargs["direction"],
                max_depth=kwargs["depth"],
                reached_via={
                    "SEED": {"depth": 0, "downstream": False, "upstream": False},
                    "OUT1": {"depth": 1, "downstream": True, "upstream": False},
                    "OUT2": {"depth": 2, "downstream": True, "upstream": False},
                    "IN1": {"depth": 1, "downstream": False, "upstream": True},
                },
            )

    persistence = Persistence()
    session = _EmptySession()
    graph = q.fetch_trace_graph_data(session, persistence, "tenant-1", "SEED", 2, direction="forward")
    assert persistence.calls == [{"tenant_id": "tenant-1", "seed_tlc": "SEED", "depth": 2, "direction": "forward"}]
    roles = {n["tlc"]: n["role"] for n in graph["nodes"]}
    assert roles == {"SEED": "seed", "OUT1": "downstream", "OUT2": "downstream", "IN1": "upstream"}
    assert {n["tlc"]: n["depth"] for n in graph["nodes"]}["OUT2"] == 2
    assert graph["direction"] == "forward"
    assert graph["depth_exhausted"] is True
    assert graph["node_count"] == 4
