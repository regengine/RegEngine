"""Regression tests for #2817 — FDA exports silently omitted the final day.

Context
-------
The three read-path queries in ``shared/cte_persistence/queries.py``
(``query_events_by_tlc``, ``query_events_by_tlcs``, ``query_all_events``)
filtered with::

    event_timestamp <= :end_date          -- :end_date = "2026-06-15"

Postgres casts a bare ``YYYY-MM-DD`` string to that day at **midnight**, so
``2026-06-15T14:00:00Z <= 2026-06-15T00:00:00`` is FALSE and every event ON
the end date was dropped. An FDA §1.1350(c) records request for
``2026-06-01 .. 2026-06-15`` returned a document that looked complete but
was missing the whole last day.

The fix mirrors ``services/ingestion/app/fda_export/queries.py::_end_bound_utc``
(issue #1224): convert the end date to a strict next-day UTC bound and use a
strict ``<``.

These tests pin it at three levels:

  1. ``_end_bound_utc`` semantics, including the non-ISO passthrough
     fallback, matched against the #1224 original.
  2. The SQL each of the three call sites actually emits: ``<`` (not ``<=``)
     bound to the next-day timestamp.
  3. Real SQL semantics — the emitted predicate + params are executed
     against a real SQLite table holding an event at
     ``2026-06-15T14:00:00Z``, asserting it IS returned for
     ``end_date=2026-06-15``. The pre-fix predicate is run over the same
     rows to show it returned nothing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest
from sqlalchemy import create_engine, text

from services.shared.cte_persistence.queries import QueryPathMixin, _end_bound_utc

TENANT_ID = "8f14e45f-ceea-467a-9f43-1b0a5eaa1d0e"

# The event that used to disappear.
LAST_DAY_EVENT_TS = "2026-06-15T14:00:00Z"
END_DATE = "2026-06-15"
START_DATE = "2026-06-01"


# ---------------------------------------------------------------------------
# Fake session: records the SQL/params each query emits
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows: List[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> List[Any]:
        return list(self._rows)

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None


class _RecordingSession:
    """Captures every ``execute`` call; returns canned rows in order."""

    def __init__(self, results: Optional[List[List[Any]]] = None) -> None:
        self.calls: List[Tuple[str, Dict[str, Any]]] = []
        self._results = list(results or [])

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), dict(params or {})))
        rows = self._results.pop(0) if self._results else []
        return _Result(rows)

    def rollback(self) -> None:  # pragma: no cover - not exercised here
        pass


class _Queries(QueryPathMixin):
    """Bare mixin host — avoids pulling in the DB/RLS machinery."""

    def __init__(self, session: _RecordingSession) -> None:
        self.session = session
        self.tenant_contexts: List[str] = []

    def set_tenant_context(self, tenant_id: str) -> None:
        # Real impl issues ``SET LOCAL app.tenant_id`` — irrelevant here and
        # unsupported by the fake session.
        self.tenant_contexts.append(tenant_id)


def _events_call(session: _RecordingSession) -> Tuple[str, Dict[str, Any]]:
    """The call whose SQL touches ``fsma.cte_events`` with the date filter."""
    for sql, params in session.calls:
        if "fsma.cte_events" in sql and "end_date" in params:
            return sql, params
    raise AssertionError(f"no cte_events query with an end_date bind: {session.calls}")


# ---------------------------------------------------------------------------
# 1. _end_bound_utc semantics (must match fda_export/queries.py, #1224)
# ---------------------------------------------------------------------------


def test_end_bound_is_strict_next_day_utc_midnight() -> None:
    assert _end_bound_utc("2026-06-15") == "2026-06-16T00:00:00+00:00"


@pytest.mark.parametrize(
    "end_date,expected",
    [
        ("2026-01-31", "2026-02-01T00:00:00+00:00"),  # month rollover
        ("2026-12-31", "2027-01-01T00:00:00+00:00"),  # year rollover
        ("2028-02-28", "2028-02-29T00:00:00+00:00"),  # leap year
        ("2028-02-29", "2028-03-01T00:00:00+00:00"),  # leap day
    ],
)
def test_end_bound_rollovers(end_date: str, expected: str) -> None:
    assert _end_bound_utc(end_date) == expected


@pytest.mark.parametrize("raw", ["not-a-date", "2026-13-45", "", "06/15/2026", None, 20260615])
def test_end_bound_passes_non_iso_values_through_unchanged(raw) -> None:
    """Matches the #1224 fallback exactly: upstream validation stays the
    authoritative source of 4xx responses, so a non-ISO value is handed to
    the DB verbatim rather than being silently reinterpreted here."""
    assert _end_bound_utc(raw) is raw


def test_end_bound_matches_the_fda_export_original() -> None:
    """The helper is duplicated (shared must not import a service package);
    assert the two implementations agree so they cannot drift."""
    fda = pytest.importorskip("services.ingestion.app.fda_export.queries")
    for value in ["2026-06-15", "2026-01-31", "2026-12-31", "not-a-date", ""]:
        assert _end_bound_utc(value) == fda._end_bound_utc(value)


# ---------------------------------------------------------------------------
# 2. Every call site emits a strict `<` against the next-day bound
# ---------------------------------------------------------------------------


def test_query_all_events_uses_strict_less_than() -> None:
    session = _RecordingSession(results=[[(0,)], []])
    _Queries(session).query_all_events(TENANT_ID, start_date=START_DATE, end_date=END_DATE)

    sql, params = _events_call(session)
    assert "event_timestamp < :end_date" in sql
    assert "event_timestamp <= :end_date" not in sql
    assert params["end_date"] == "2026-06-16T00:00:00+00:00"


def test_query_events_by_tlc_uses_strict_less_than() -> None:
    # call 1: transformation-link expansion (empty → seed only); call 2: events
    session = _RecordingSession(results=[[], []])
    _Queries(session).query_events_by_tlc(TENANT_ID, "LOT-1", start_date=START_DATE, end_date=END_DATE)

    sql, params = _events_call(session)
    assert "event_timestamp < :end_date" in sql
    assert "event_timestamp <= :end_date" not in sql
    assert params["end_date"] == "2026-06-16T00:00:00+00:00"


def test_query_events_by_tlcs_uses_strict_less_than() -> None:
    session = _RecordingSession(results=[[], []])
    _Queries(session).query_events_by_tlcs(TENANT_ID, ["LOT-1"], start_date=START_DATE, end_date=END_DATE)

    sql, params = _events_call(session)
    assert "event_timestamp < :end_date" in sql
    assert "event_timestamp <= :end_date" not in sql
    assert params["end_date"] == "2026-06-16T00:00:00+00:00"


def test_start_date_bound_stays_inclusive_in_utc() -> None:
    """The inclusive start stays ``>=`` and is independent of session time."""
    session = _RecordingSession(results=[[(0,)], []])
    _Queries(session).query_all_events(TENANT_ID, start_date=START_DATE, end_date=END_DATE)
    sql, params = _events_call(session)
    assert "event_timestamp >= :start_date" in sql
    assert params["start_date"] == "2026-06-01T00:00:00+00:00"


def test_no_end_date_emits_no_upper_bound() -> None:
    session = _RecordingSession(results=[[(0,)], []])
    _Queries(session).query_all_events(TENANT_ID, start_date=START_DATE)
    sql, params = session.calls[0]
    assert "end_date" not in sql
    assert "end_date" not in params


# ---------------------------------------------------------------------------
# 3. Real SQL: an event ON the end date IS included
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqlite_events():
    """A real table of ISO-8601 timestamps spanning the export window.

    ISO-8601 strings compare lexicographically in the same order they
    compare chronologically, so SQLite reproduces the Postgres boundary
    behaviour faithfully for this test.
    """
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE cte_events (tenant_id TEXT, event_timestamp TEXT, tag TEXT)"))
        for ts, tag in [
            ("2026-06-01T00:00:00Z", "first_day_midnight"),
            ("2026-06-10T09:30:00Z", "mid_window"),
            ("2026-06-15T00:00:00Z", "last_day_midnight"),
            (LAST_DAY_EVENT_TS, "last_day_afternoon"),
            ("2026-06-15T23:59:59Z", "last_day_last_second"),
            ("2026-06-16T00:00:00Z", "next_day_midnight"),
            ("2026-06-17T08:00:00Z", "after_window"),
        ]:
            conn.execute(
                text("INSERT INTO cte_events VALUES (:tid, :ts, :tag)"),
                {"tid": TENANT_ID, "ts": ts, "tag": tag},
            )
        conn.commit()
        yield conn


def _select_tags(conn, predicate: str, params: Dict[str, Any]) -> List[str]:
    rows = conn.execute(
        text(f"SELECT tag FROM cte_events WHERE tenant_id = :tid AND {predicate} ORDER BY event_timestamp"),
        params,
    ).fetchall()
    return [r[0] for r in rows]


def test_event_on_end_date_is_included(sqlite_events) -> None:
    """THE #2817 regression test: an event at 2026-06-15T14:00:00Z IS
    returned when end_date=2026-06-15."""
    session = _RecordingSession(results=[[(0,)], []])
    _Queries(session).query_all_events(TENANT_ID, start_date=START_DATE, end_date=END_DATE)
    _sql, params = _events_call(session)

    # Execute the EXACT predicate + binds the fixed query produced.
    tags = _select_tags(
        sqlite_events,
        "event_timestamp >= :start_date AND event_timestamp < :end_date",
        {"tid": TENANT_ID, "start_date": START_DATE, "end_date": params["end_date"]},
    )

    assert "last_day_afternoon" in tags, f"2026-06-15T14:00:00Z was dropped again: {tags}"
    assert tags == [
        "first_day_midnight",
        "mid_window",
        "last_day_midnight",
        "last_day_afternoon",
        "last_day_last_second",
    ]
    # The strict bound must still exclude the day AFTER the window.
    assert "next_day_midnight" not in tags
    assert "after_window" not in tags


def test_pre_fix_predicate_would_have_dropped_the_final_day(sqlite_events) -> None:
    """Demonstrates the bug this test guards against: the old
    ``<= 'YYYY-MM-DD'`` predicate returns nothing from 2026-06-15."""
    tags = _select_tags(
        sqlite_events,
        "event_timestamp >= :start_date AND event_timestamp <= :end_date",
        {"tid": TENANT_ID, "start_date": START_DATE, "end_date": END_DATE},
    )
    assert "last_day_afternoon" not in tags
    assert not [t for t in tags if t.startswith("last_day")]
