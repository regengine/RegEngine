"""Unit tests for ``app.fda_export.queries`` — issue #1342.

Covers the SQL-building, row-shaping, and audit-log helpers in
``queries.py`` as an isolated unit — no real database, no FastAPI — so
each branch (end-bound parsing, conditional WHERE fragments, ``%``
wildcard handling, ``AuditLogWriteError`` raise/rollback paths,
timezone-aware ``initiated_at_utc`` stamping, rule-result JSON parsing,
trace-graph edge expansion) is locked against regression even if the
outer router evolves.

These tests pin production-critical behavior explicitly called out in
the docstrings:

* #1205 / #1215 — audit-log write failure must raise
  :class:`AuditLogWriteError`, not be swallowed.
* #1224 — strict next-day UTC upper bound in ``_end_bound_utc`` so
  recalls don't drop events due to server-timezone drift.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.fda_export import queries as q  # noqa: E402
from app.fda_export.queries import (  # noqa: E402
    AuditLogWriteError,
    _end_bound_utc,
    build_recall_where_clause,
    build_v2_where_clause,
    fetch_export_log_history,
    fetch_recall_events,
    fetch_trace_graph_data,
    fetch_v2_events,
    format_export_log_rows,
    log_recall_export,
    log_v2_export,
    rows_to_event_dicts,
    v2_rows_to_event_dicts,
)


# ---------------------------------------------------------------------------
# Fake DB-session primitives
# ---------------------------------------------------------------------------


class _Result:
    """Stand-in for a SQLAlchemy Result."""

    def __init__(self, rows=None, row=None):
        self._rows = rows or []
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _FakeSession:
    """Captures ``execute`` calls and lets tests script the return value.

    ``execute`` returns the next value from ``results`` on each call, so
    tests that issue multiple queries (e.g., trace-graph) can script the
    count + edges responses in order.
    """

    def __init__(self, *, results=None, raise_on_insert=False,
                 raise_on_rollback=False):
        self.executes: list[tuple[Any, Any]] = []
        self.commits = 0
        self.rollbacks = 0
        self._results = list(results or [])
        self._raise_on_insert = raise_on_insert
        self._raise_on_rollback = raise_on_rollback

    def execute(self, stmt, params=None):
        self.executes.append((stmt, params))
        if self._raise_on_insert:
            raise RuntimeError("simulated DB outage")
        if self._results:
            return self._results.pop(0)
        return _Result()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1
        if self._raise_on_rollback:
            raise RuntimeError("rollback also failed")


# ---------------------------------------------------------------------------
# _end_bound_utc
# ---------------------------------------------------------------------------


class TestEndBoundUtc:
    def test_iso_date_returns_next_day_midnight_utc(self):
        result = _end_bound_utc("2026-04-17")
        # Must be the *next* day at 00:00 UTC so strict ``<`` catches
        # every event on 2026-04-17 regardless of TZ (issue #1224).
        assert result == "2026-04-18T00:00:00+00:00"

    def test_result_is_strictly_after_end_date_start(self):
        result = _end_bound_utc("2026-04-17")
        parsed = datetime.fromisoformat(result)
        end_date_start = datetime(2026, 4, 17, 0, 0, 0, tzinfo=timezone.utc)
        delta = parsed - end_date_start
        assert delta == timedelta(days=1)

    def test_leap_day_handled(self):
        result = _end_bound_utc("2024-02-29")
        assert result == "2024-03-01T00:00:00+00:00"

    def test_year_boundary_rolls_into_next_year(self):
        result = _end_bound_utc("2026-12-31")
        assert result == "2027-01-01T00:00:00+00:00"

    def test_non_iso_falls_back_to_raw_string(self):
        # Upstream validation remains the 4xx source — we must not
        # silently mangle bad input.
        assert _end_bound_utc("not-a-date") == "not-a-date"

    def test_none_falls_back_to_raw(self):
        assert _end_bound_utc(None) is None  # type: ignore[arg-type]

    def test_datetime_with_time_portion_also_falls_back(self):
        # ``YYYY-MM-DDTHH:MM`` parses via ``date.fromisoformat`` only on
        # Python 3.11+ — guard the branch either way.
        val = _end_bound_utc("2026-04-17T12:00:00")
        # Whatever the Python version decides, we either rolled a day or
        # fell back. Both are acceptable; the key point is we never
        # raise.
        assert isinstance(val, str)


# ---------------------------------------------------------------------------
# fetch_export_log_history
# ---------------------------------------------------------------------------


class TestFetchExportLogHistory:
    def test_returns_rows_from_session_execute(self):
        row = ("id-1", "recall", "TLC-X", "2026-04-01", "2026-04-10",
               42, "hash", "user@example.com",
               datetime(2026, 4, 17, tzinfo=timezone.utc))
        session = _FakeSession(results=[_Result(rows=[row])])

        rows = fetch_export_log_history(session, "tenant-42", 25)

        assert rows == [row]
        assert len(session.executes) == 1
        _stmt, params = session.executes[0]
        assert params == {"tid": "tenant-42", "lim": 25}

    def test_empty_result_set_returns_empty_list(self):
        session = _FakeSession(results=[_Result(rows=[])])
        assert fetch_export_log_history(session, "tenant-42", 5) == []


# ---------------------------------------------------------------------------
# format_export_log_rows
# ---------------------------------------------------------------------------


class TestFormatExportLogRows:
    def test_happy_path_with_populated_fields(self):
        generated_at = datetime(2026, 4, 17, 12, 30, 0, tzinfo=timezone.utc)
        row = (
            "export-id-1",
            "recall",
            "TLC-ABC",
            date(2026, 4, 1),
            date(2026, 4, 10),
            42,
            "sha256hash",
            "user@example.com",
            generated_at,
        )
        result = format_export_log_rows([row], "tenant-42")

        assert result["tenant_id"] == "tenant-42"
        assert result["total"] == 1
        assert len(result["exports"]) == 1

        export = result["exports"][0]
        assert export["id"] == "export-id-1"
        assert export["export_type"] == "recall"
        assert export["query_tlc"] == "TLC-ABC"
        assert export["query_start_date"] == "2026-04-01"
        assert export["query_end_date"] == "2026-04-10"
        assert export["record_count"] == 42
        assert export["export_hash"] == "sha256hash"
        assert export["generated_by"] == "user@example.com"
        assert export["generated_at"] == generated_at.isoformat()

    def test_none_date_fields_become_none(self):
        row = ("id", "recall", None, None, None, 0, "h", "u", None)
        result = format_export_log_rows([row], "t")

        export = result["exports"][0]
        assert export["query_start_date"] is None
        assert export["query_end_date"] is None
        assert export["generated_at"] is None

    def test_empty_rows_returns_zero_total(self):
        result = format_export_log_rows([], "t")
        assert result == {"tenant_id": "t", "exports": [], "total": 0}

    def test_multiple_rows_preserve_order(self):
        rows = [
            ("id-1", "recall", "TLC-A", None, None, 1, "h1", "u", None),
            ("id-2", "recall", "TLC-B", None, None, 2, "h2", "u", None),
        ]
        result = format_export_log_rows(rows, "t")
        assert [e["id"] for e in result["exports"]] == ["id-1", "id-2"]

    def test_uuid_like_ids_stringified(self):
        class _FakeUUID:
            def __str__(self):
                return "550e8400-e29b-41d4-a716-446655440000"

        row = (_FakeUUID(), "recall", "T", None, None, 0, "h", "u", None)
        result = format_export_log_rows([row], "t")
        assert result["exports"][0]["id"] == "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# build_recall_where_clause
# ---------------------------------------------------------------------------


class TestBuildRecallWhereClause:
    def test_tenant_only_base_conditions(self):
        where, params = build_recall_where_clause(
            "tenant-42", None, None, None, None, None, None
        )
        assert where == "e.tenant_id = :tid"
        assert params == {"tid": "tenant-42"}

    def test_product_filter_adds_like(self):
        where, params = build_recall_where_clause(
            "t", "Strawberries", None, None, None, None, None
        )
        assert "LOWER(e.product_description) LIKE LOWER(:product)" in where
        assert params["product"] == "%Strawberries%"

    def test_location_filter_matches_name_or_gln(self):
        where, params = build_recall_where_clause(
            "t", None, "Warehouse-A", None, None, None, None
        )
        assert "LOWER(e.location_name) LIKE LOWER(:loc)" in where
        assert "e.location_gln LIKE :loc_exact" in where
        assert params["loc"] == "%Warehouse-A%"
        assert params["loc_exact"] == "%Warehouse-A%"

    def test_tlc_without_percent_gets_wrapped(self):
        where, params = build_recall_where_clause(
            "t", None, None, "TLC-XYZ", None, None, None
        )
        assert "e.traceability_lot_code LIKE :tlc" in where
        assert params["tlc"] == "%TLC-XYZ%"

    def test_tlc_with_percent_passes_through(self):
        # User-supplied wildcard is respected (advanced recall use).
        where, params = build_recall_where_clause(
            "t", None, None, "TLC-%", None, None, None
        )
        assert params["tlc"] == "TLC-%"

    def test_event_type_equality(self):
        where, params = build_recall_where_clause(
            "t", None, None, None, "shipping", None, None
        )
        assert "e.event_type = :etype" in where
        assert params["etype"] == "shipping"

    def test_start_date_adds_ge_condition(self):
        where, params = build_recall_where_clause(
            "t", None, None, None, None, "2026-04-01", None
        )
        assert "e.event_timestamp >= :start" in where
        assert params["start"] == "2026-04-01"

    def test_end_date_adds_strict_lt_at_next_day_utc(self):
        # #1224 — must be strict ``<`` with next-day UTC bound.
        where, params = build_recall_where_clause(
            "t", None, None, None, None, None, "2026-04-10"
        )
        assert "e.event_timestamp < :end" in where
        assert params["end"] == "2026-04-11T00:00:00+00:00"

    def test_all_filters_combine_with_and(self):
        where, params = build_recall_where_clause(
            "tenant-1", "Prod", "Loc", "TLC", "shipping",
            "2026-04-01", "2026-04-10"
        )
        clauses = where.split(" AND ")
        # 1 base + 6 extras = 7 clauses total (location adds one clause
        # with an OR inside it).
        assert len(clauses) == 7
        assert params["tid"] == "tenant-1"
        assert params["product"] == "%Prod%"
        assert params["loc"] == "%Loc%"
        assert params["loc_exact"] == "%Loc%"
        assert params["tlc"] == "%TLC%"
        assert params["etype"] == "shipping"
        assert params["start"] == "2026-04-01"
        assert params["end"] == "2026-04-11T00:00:00+00:00"

    def test_empty_strings_treated_as_unset(self):
        # Empty strings are falsy, so no extra clauses.
        where, params = build_recall_where_clause(
            "t", "", "", "", "", "", ""
        )
        assert where == "e.tenant_id = :tid"
        assert params == {"tid": "t"}


# ---------------------------------------------------------------------------
# fetch_recall_events
# ---------------------------------------------------------------------------


class TestFetchRecallEvents:
    def test_executes_with_params_and_returns_rows(self):
        row = ("id-1",) + ("x",) * 13
        session = _FakeSession(results=[_Result(rows=[row])])
        out = fetch_recall_events(session, "e.tenant_id = :tid", {"tid": "t"})
        assert out == [row]
        _stmt, params = session.executes[0]
        assert params == {"tid": "t"}

    def test_empty_result_returns_empty_list(self):
        session = _FakeSession(results=[_Result(rows=[])])
        assert fetch_recall_events(session, "1=1", {}) == []


# ---------------------------------------------------------------------------
# rows_to_event_dicts
# ---------------------------------------------------------------------------


class TestRowsToEventDicts:
    def _make_row(self, *, ts=None, ingested=None, kdes=None, chain_hash="chain-x"):
        return (
            "event-id",
            "shipping",
            "TLC-1",
            "Frozen Strawberries",
            100.5,
            "lbs",
            ts,
            "0614141999996",
            "Warehouse A",
            "edi_856",
            "sha-256",
            chain_hash,
            kdes,
            ingested,
        )

    def test_populated_timestamp_is_iso_serialized(self):
        ts = datetime(2026, 4, 17, 10, 30, 0, tzinfo=timezone.utc)
        ingested = datetime(2026, 4, 17, 10, 35, 0, tzinfo=timezone.utc)
        row = self._make_row(ts=ts, ingested=ingested, kdes={"a": "b"})

        events = rows_to_event_dicts([row])

        assert len(events) == 1
        ev = events[0]
        assert ev["id"] == "event-id"
        assert ev["event_type"] == "shipping"
        assert ev["traceability_lot_code"] == "TLC-1"
        assert ev["product_description"] == "Frozen Strawberries"
        assert ev["quantity"] == 100.5
        assert ev["unit_of_measure"] == "lbs"
        assert ev["event_timestamp"] == ts.isoformat()
        assert ev["location_gln"] == "0614141999996"
        assert ev["location_name"] == "Warehouse A"
        assert ev["source"] == "edi_856"
        assert ev["sha256_hash"] == "sha-256"
        assert ev["chain_hash"] == "chain-x"
        assert ev["kdes"] == {"a": "b"}
        assert ev["ingested_at"] == ingested.isoformat()

    def test_none_kdes_default_to_empty_dict(self):
        row = self._make_row(kdes=None)
        events = rows_to_event_dicts([row])
        assert events[0]["kdes"] == {}

    def test_string_timestamp_passes_through(self):
        row = self._make_row(ts="2026-04-17T10:00:00Z")
        events = rows_to_event_dicts([row])
        assert events[0]["event_timestamp"] == "2026-04-17T10:00:00Z"

    def test_none_timestamp_becomes_empty_string(self):
        row = self._make_row(ts=None)
        events = rows_to_event_dicts([row])
        assert events[0]["event_timestamp"] == ""

    def test_none_chain_hash_becomes_empty_string(self):
        row = self._make_row(chain_hash=None)
        events = rows_to_event_dicts([row])
        assert events[0]["chain_hash"] == ""

    def test_none_ingested_becomes_empty_string(self):
        row = self._make_row(ingested=None)
        events = rows_to_event_dicts([row])
        assert events[0]["ingested_at"] == ""

    def test_string_ingested_passes_through(self):
        row = self._make_row(ingested="2026-04-17T10:00:00Z")
        events = rows_to_event_dicts([row])
        # Falls through to ``str()`` branch — still preserves the
        # string.
        assert events[0]["ingested_at"] == "2026-04-17T10:00:00Z"

    def test_uuid_like_id_is_stringified(self):
        class _FakeUUID:
            def __str__(self):
                return "uuid-x"

        row = (_FakeUUID(),) + ("x",) * 11 + ({}, None)
        events = rows_to_event_dicts([row])
        assert events[0]["id"] == "uuid-x"

    def test_empty_rows(self):
        assert rows_to_event_dicts([]) == []


# ---------------------------------------------------------------------------
# AuditLogWriteError
# ---------------------------------------------------------------------------


class TestAuditLogWriteError:
    def test_is_runtime_error_subclass(self):
        # Must subclass RuntimeError so the router's ``except
        # (ImportError, ValueError, RuntimeError, OSError)`` tuple
        # catches non-audit RuntimeErrors without also swallowing
        # ``AuditLogWriteError`` — the latter needs its dedicated
        # 503 mapping.
        assert issubclass(AuditLogWriteError, RuntimeError)

    def test_str_representation_preserves_message(self):
        err = AuditLogWriteError("boom")
        assert str(err) == "boom"


# ---------------------------------------------------------------------------
# log_recall_export
# ---------------------------------------------------------------------------


class TestLogRecallExport:
    def test_happy_path_inserts_commits_and_logs(self, caplog):
        session = _FakeSession()
        with caplog.at_level("INFO", logger="fda-export"):
            log_recall_export(
                db_session=session,
                tenant_id="tenant-42",
                events=[{"id": "e1"}, {"id": "e2"}],
                export_hash="0" * 64,
                format="csv",
                tlc="TLC-X",
                start_date="2026-04-01",
                end_date="2026-04-10",
                user_id="user@example.com",
                user_email="user@example.com",
                request_id="req-1",
                user_agent="UA/1.0",
                source_ip="1.2.3.4",
                product="Prod",
                location="Loc",
                event_type="shipping",
            )

        assert len(session.executes) == 1
        assert session.commits == 1
        assert session.rollbacks == 0

        _stmt, params = session.executes[0]
        assert params["tid"] == "tenant-42"
        assert params["cnt"] == 2
        assert params["etype"] == "recall"
        assert params["generated_by"] == "user@example.com"
        assert params["tlc"] == "TLC-X"
        assert params["sd"] == "2026-04-01"
        assert params["ed"] == "2026-04-10"

        audit_records = [r for r in caplog.records
                         if r.message == "fda_recall_export_audit"]
        assert len(audit_records) == 1
        audit = audit_records[0]
        assert audit.tenant_id == "tenant-42"
        assert audit.user_id == "user@example.com"
        assert audit.user_email == "user@example.com"
        assert audit.request_id == "req-1"
        assert audit.user_agent == "UA/1.0"
        assert audit.source_ip == "1.2.3.4"
        assert audit.export_type == "recall"
        assert audit.record_count == 2
        assert audit.filters_applied["product"] == "Prod"
        assert audit.filters_applied["location"] == "Loc"
        assert audit.filters_applied["tlc"] == "TLC-X"
        assert audit.filters_applied["event_type"] == "shipping"
        # initiated_at_utc must be ISO-8601 with TZ offset
        datetime.fromisoformat(audit.initiated_at_utc)

    def test_package_format_uses_recall_package_etype(self):
        session = _FakeSession()
        log_recall_export(
            db_session=session,
            tenant_id="t",
            events=[],
            export_hash="h",
            format="package",
            tlc=None,
            start_date=None,
            end_date=None,
        )
        params = session.executes[0][1]
        assert params["etype"] == "recall_package"
        assert params["generated_by"] == "api_recall_package"

    def test_csv_format_without_user_defaults_to_api_recall(self):
        session = _FakeSession()
        log_recall_export(
            db_session=session,
            tenant_id="t",
            events=[],
            export_hash="h",
            format="csv",
            tlc=None,
            start_date=None,
            end_date=None,
        )
        params = session.executes[0][1]
        assert params["etype"] == "recall"
        assert params["generated_by"] == "api_recall"

    def test_user_id_overrides_default_generated_by(self):
        session = _FakeSession()
        log_recall_export(
            db_session=session,
            tenant_id="t",
            events=[],
            export_hash="h",
            format="csv",
            tlc=None,
            start_date=None,
            end_date=None,
            user_id="explicit-user",
        )
        params = session.executes[0][1]
        assert params["generated_by"] == "explicit-user"

    def test_db_failure_raises_audit_log_write_error(self):
        session = _FakeSession(raise_on_insert=True)

        with pytest.raises(AuditLogWriteError) as exc_info:
            log_recall_export(
                db_session=session,
                tenant_id="t",
                events=[],
                export_hash="h",
                format="csv",
                tlc=None,
                start_date=None,
                end_date=None,
            )

        # Original error must be chained so operators can see root cause.
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        # Rollback was attempted to clear session state.
        assert session.rollbacks == 1
        assert session.commits == 0

    def test_db_failure_with_rollback_also_failing_still_raises(self):
        session = _FakeSession(raise_on_insert=True, raise_on_rollback=True)

        # The except block swallows rollback failures so the caller still
        # sees the *original* AuditLogWriteError.
        with pytest.raises(AuditLogWriteError):
            log_recall_export(
                db_session=session,
                tenant_id="t",
                events=[],
                export_hash="hash-abcdef0123",
                format="csv",
                tlc=None,
                start_date=None,
                end_date=None,
            )
        assert session.rollbacks == 1  # attempted once
        assert session.commits == 0

    def test_db_failure_logs_error_with_truncated_hash(self, caplog):
        session = _FakeSession(raise_on_insert=True)

        with caplog.at_level("ERROR", logger="fda-export"):
            with pytest.raises(AuditLogWriteError):
                log_recall_export(
                    db_session=session,
                    tenant_id="t",
                    events=[{"x": 1}],
                    export_hash="a" * 64,
                    format="csv",
                    tlc=None,
                    start_date=None,
                    end_date=None,
                    user_id="u",
                    request_id="r",
                )

        err_records = [r for r in caplog.records
                       if r.message == "fda_recall_export_audit_log_failed"]
        assert len(err_records) == 1
        err = err_records[0]
        assert err.levelname == "ERROR"
        # Truncate hash to 16 chars to avoid dumping the full digest in
        # plaintext logs.
        assert err.export_hash == "a" * 16
        assert err.record_count == 1

    def test_db_failure_with_empty_hash_logs_none(self, caplog):
        session = _FakeSession(raise_on_insert=True)
        with caplog.at_level("ERROR", logger="fda-export"):
            with pytest.raises(AuditLogWriteError):
                log_recall_export(
                    db_session=session,
                    tenant_id="t",
                    events=[],
                    export_hash="",
                    format="csv",
                    tlc=None,
                    start_date=None,
                    end_date=None,
                )
        err = [r for r in caplog.records
               if r.message == "fda_recall_export_audit_log_failed"][0]
        assert err.export_hash is None


# ---------------------------------------------------------------------------
# build_v2_where_clause
# ---------------------------------------------------------------------------


class TestBuildV2WhereClause:
    def test_tenant_only_base(self):
        where, params = build_v2_where_clause("t", None, None, None, None)
        assert where == "e.tenant_id = :tid"
        assert params == {"tid": "t"}

    def test_tlc_exact_when_no_percent(self):
        # v2 uses equality for exact TLC (unlike recall which wraps
        # with ``%``) — exact match is cheaper and lets callers target
        # a single lot precisely.
        where, params = build_v2_where_clause("t", "TLC-X", None, None, None)
        assert "e.traceability_lot_code = :tlc" in where
        assert params["tlc"] == "TLC-X"

    def test_tlc_with_percent_uses_like(self):
        where, params = build_v2_where_clause("t", "TLC-%", None, None, None)
        assert "e.traceability_lot_code LIKE :tlc" in where
        assert params["tlc"] == "TLC-%"

    def test_event_type_filter(self):
        where, params = build_v2_where_clause("t", None, "receiving", None, None)
        assert "e.event_type = :etype" in where
        assert params["etype"] == "receiving"

    def test_start_date_filter(self):
        where, params = build_v2_where_clause(
            "t", None, None, "2026-04-01", None
        )
        assert "e.event_timestamp >= :start" in where
        assert params["start"] == "2026-04-01"

    def test_end_date_uses_next_day_utc_bound(self):
        where, params = build_v2_where_clause(
            "t", None, None, None, "2026-04-10"
        )
        assert "e.event_timestamp < :end" in where
        assert params["end"] == "2026-04-11T00:00:00+00:00"

    def test_all_filters_combined(self):
        where, params = build_v2_where_clause(
            "t", "TLC-ABC", "shipping", "2026-04-01", "2026-04-10"
        )
        clauses = where.split(" AND ")
        assert len(clauses) == 5
        assert params == {
            "tid": "t",
            "tlc": "TLC-ABC",
            "etype": "shipping",
            "start": "2026-04-01",
            "end": "2026-04-11T00:00:00+00:00",
        }


# ---------------------------------------------------------------------------
# fetch_v2_events
# ---------------------------------------------------------------------------


class TestFetchV2Events:
    def test_executes_and_returns_rows(self):
        row = ("id",) + ("x",) * 15
        session = _FakeSession(results=[_Result(rows=[row])])
        assert fetch_v2_events(session, "e.tenant_id = :tid", {"tid": "t"}) == [row]
        assert session.executes[0][1] == {"tid": "t"}

    def test_empty_result(self):
        session = _FakeSession(results=[_Result(rows=[])])
        assert fetch_v2_events(session, "1=1", {}) == []


# ---------------------------------------------------------------------------
# v2_rows_to_event_dicts
# ---------------------------------------------------------------------------


class TestV2RowsToEventDicts:
    def _make_row(self, *, ts=None, ingested=None, kdes=None,
                  provenance=None, rule_results=None,
                  chain_hash="chain-x"):
        return (
            "event-id",
            "shipping",
            "TLC-1",
            "Frozen Strawberries",
            100.5,
            "lbs",
            ts,
            "0614141999996",
            "Warehouse A",
            "edi_856",
            "sha-256",
            chain_hash,
            kdes,
            provenance,
            rule_results,
            ingested,
        )

    def test_happy_path_with_all_fields(self):
        ts = datetime(2026, 4, 17, 10, 0, 0, tzinfo=timezone.utc)
        ingested = datetime(2026, 4, 17, 10, 5, 0, tzinfo=timezone.utc)
        rule_results = [
            {"rule_name": "r1", "passed": True, "why_failed": None},
        ]
        row = self._make_row(
            ts=ts, ingested=ingested,
            kdes={"a": "b"},
            provenance={"src": "edi"},
            rule_results=rule_results,
        )

        events = v2_rows_to_event_dicts([row])
        assert len(events) == 1
        ev = events[0]
        assert ev["id"] == "event-id"
        assert ev["event_timestamp"] == ts.isoformat()
        assert ev["kdes"] == {"a": "b"}
        assert ev["provenance"] == {"src": "edi"}
        assert ev["rule_results"] == rule_results
        assert ev["ingested_at"] == ingested.isoformat()

    def test_none_kdes_default_to_empty_dict(self):
        row = self._make_row(kdes=None)
        events = v2_rows_to_event_dicts([row])
        assert events[0]["kdes"] == {}

    def test_none_provenance_default_to_empty_dict(self):
        row = self._make_row(provenance=None)
        events = v2_rows_to_event_dicts([row])
        assert events[0]["provenance"] == {}

    def test_none_rule_results_default_to_empty_list(self):
        row = self._make_row(rule_results=None)
        events = v2_rows_to_event_dicts([row])
        assert events[0]["rule_results"] == []

    def test_rule_results_as_json_string_is_parsed(self):
        # PostgreSQL can return jsonb as str in some drivers.
        row = self._make_row(
            rule_results='[{"rule_name": "r1", "passed": false}]'
        )
        events = v2_rows_to_event_dicts([row])
        assert events[0]["rule_results"] == [
            {"rule_name": "r1", "passed": False}
        ]

    def test_malformed_json_rule_results_becomes_empty_list(self):
        row = self._make_row(rule_results="{not-json")
        events = v2_rows_to_event_dicts([row])
        assert events[0]["rule_results"] == []

    def test_string_timestamp_preserved(self):
        row = self._make_row(ts="2026-04-17T00:00:00Z")
        events = v2_rows_to_event_dicts([row])
        assert events[0]["event_timestamp"] == "2026-04-17T00:00:00Z"

    def test_none_timestamp_becomes_empty_string(self):
        row = self._make_row(ts=None)
        events = v2_rows_to_event_dicts([row])
        assert events[0]["event_timestamp"] == ""

    def test_none_chain_hash_becomes_empty_string(self):
        row = self._make_row(chain_hash=None)
        events = v2_rows_to_event_dicts([row])
        assert events[0]["chain_hash"] == ""

    def test_none_ingested_becomes_empty_string(self):
        row = self._make_row(ingested=None)
        events = v2_rows_to_event_dicts([row])
        assert events[0]["ingested_at"] == ""

    def test_string_ingested_preserved_via_str(self):
        row = self._make_row(ingested="2026-04-17T10:00:00Z")
        events = v2_rows_to_event_dicts([row])
        assert events[0]["ingested_at"] == "2026-04-17T10:00:00Z"

    def test_empty_rows(self):
        assert v2_rows_to_event_dicts([]) == []


# ---------------------------------------------------------------------------
# log_v2_export
# ---------------------------------------------------------------------------


class TestLogV2Export:
    def test_happy_path_spreadsheet_format(self, caplog):
        session = _FakeSession()
        with caplog.at_level("INFO", logger="fda-export"):
            log_v2_export(
                db_session=session,
                tenant_id="tenant-42",
                events=[{}, {}, {}],
                export_hash="h" * 64,
                format="csv",
                tlc="TLC-X",
                start_date="2026-04-01",
                end_date="2026-04-10",
                user_id="u",
                user_email="u@e.com",
                request_id="r",
                user_agent="UA",
                source_ip="1.2.3.4",
            )
        assert session.commits == 1
        params = session.executes[0][1]
        assert params["etype"] == "v2_spreadsheet"
        assert params["generated_by"] == "u"
        assert params["cnt"] == 3

        audit = [r for r in caplog.records
                 if r.message == "fda_v2_export_audit"][0]
        assert audit.export_type == "v2_spreadsheet"
        assert audit.filters_applied == {
            "tlc": "TLC-X",
            "start_date": "2026-04-01",
            "end_date": "2026-04-10",
        }
        datetime.fromisoformat(audit.initiated_at_utc)

    def test_package_format_uses_v2_package(self):
        session = _FakeSession()
        log_v2_export(
            db_session=session,
            tenant_id="t",
            events=[],
            export_hash="h",
            format="package",
            tlc=None,
            start_date=None,
            end_date=None,
        )
        params = session.executes[0][1]
        assert params["etype"] == "v2_package"
        assert params["generated_by"] == "api_v2_package"

    def test_default_generated_by_without_user(self):
        session = _FakeSession()
        log_v2_export(
            db_session=session,
            tenant_id="t",
            events=[],
            export_hash="h",
            format="csv",
            tlc=None,
            start_date=None,
            end_date=None,
        )
        assert session.executes[0][1]["generated_by"] == "api_v2"

    def test_db_failure_raises_audit_log_write_error(self):
        session = _FakeSession(raise_on_insert=True)
        with pytest.raises(AuditLogWriteError) as exc_info:
            log_v2_export(
                db_session=session,
                tenant_id="t",
                events=[],
                export_hash="h",
                format="csv",
                tlc=None,
                start_date=None,
                end_date=None,
            )
        assert isinstance(exc_info.value.__cause__, RuntimeError)
        assert session.rollbacks == 1
        assert session.commits == 0

    def test_db_failure_with_rollback_also_failing(self):
        session = _FakeSession(raise_on_insert=True, raise_on_rollback=True)
        with pytest.raises(AuditLogWriteError):
            log_v2_export(
                db_session=session,
                tenant_id="t",
                events=[],
                export_hash="hash123456789abc",
                format="csv",
                tlc=None,
                start_date=None,
                end_date=None,
            )
        assert session.rollbacks == 1

    def test_db_failure_logs_error_with_truncated_hash(self, caplog):
        session = _FakeSession(raise_on_insert=True)
        with caplog.at_level("ERROR", logger="fda-export"):
            with pytest.raises(AuditLogWriteError):
                log_v2_export(
                    db_session=session,
                    tenant_id="t",
                    events=[{}],
                    export_hash="b" * 64,
                    format="csv",
                    tlc=None,
                    start_date=None,
                    end_date=None,
                    user_id="u",
                    request_id="r",
                )
        err = [r for r in caplog.records
               if r.message == "fda_v2_export_audit_log_failed"][0]
        assert err.export_hash == "b" * 16

    def test_db_failure_with_empty_hash_logs_none(self, caplog):
        session = _FakeSession(raise_on_insert=True)
        with caplog.at_level("ERROR", logger="fda-export"):
            with pytest.raises(AuditLogWriteError):
                log_v2_export(
                    db_session=session,
                    tenant_id="t",
                    events=[],
                    export_hash="",
                    format="csv",
                    tlc=None,
                    start_date=None,
                    end_date=None,
                )
        err = [r for r in caplog.records
               if r.message == "fda_v2_export_audit_log_failed"][0]
        assert err.export_hash is None


# ---------------------------------------------------------------------------
# fetch_trace_graph_data
# ---------------------------------------------------------------------------


class TestFetchTraceGraphData:
    def _persistence(self, linked):
        """Persistence stub with a scripted transformation-link expansion."""
        return SimpleNamespace(
            _expand_tlcs_via_transformation_links=lambda tenant_id, seed_tlc, depth: list(linked)
        )

    def test_happy_path_builds_nodes_edges_and_totals(self):
        # Scripted expansion: seed plus 2 linked TLCs.
        persistence = self._persistence(["TLC-A", "TLC-B", "TLC-C"])

        count_rows = [
            ("TLC-A", 3,
             datetime(2026, 4, 1, tzinfo=timezone.utc),
             datetime(2026, 4, 5, tzinfo=timezone.utc)),
            ("TLC-B", 1, None, None),
        ]
        link_rows = [
            ("TLC-A", "TLC-B", "transform", 0.95),
            ("TLC-B", "TLC-C", "transform", None),
        ]
        session = _FakeSession(results=[
            _Result(rows=count_rows),
            _Result(rows=link_rows),
        ])

        result = fetch_trace_graph_data(
            session, persistence, "tenant-42", "TLC-A", 3
        )

        assert result["seed_tlc"] == "TLC-A"
        assert result["tenant_id"] == "tenant-42"
        assert result["traversal_depth"] == 3
        assert result["node_count"] == 3
        assert result["edge_count"] == 2
        assert result["total_events"] == 4  # 3 + 1 + 0 (TLC-C missing)

        nodes_by_tlc = {n["tlc"]: n for n in result["nodes"]}
        # Seed stats populated from count_rows
        assert nodes_by_tlc["TLC-A"]["is_seed"] is True
        assert nodes_by_tlc["TLC-A"]["role"] == "seed"
        assert nodes_by_tlc["TLC-A"]["event_count"] == 3
        assert nodes_by_tlc["TLC-A"]["first_event"] == "2026-04-01T00:00:00+00:00"
        assert nodes_by_tlc["TLC-A"]["last_event"] == "2026-04-05T00:00:00+00:00"

        # Downstream role: seed -> TLC-B edge exists
        assert nodes_by_tlc["TLC-B"]["is_seed"] is False
        assert nodes_by_tlc["TLC-B"]["role"] == "downstream"
        # First/last events were None → isoformat() skipped
        assert nodes_by_tlc["TLC-B"]["first_event"] is None
        assert nodes_by_tlc["TLC-B"]["last_event"] is None

        # TLC-C has no stats in tlc_stats — default zero/None applied
        assert nodes_by_tlc["TLC-C"]["event_count"] == 0
        assert nodes_by_tlc["TLC-C"]["first_event"] is None
        assert nodes_by_tlc["TLC-C"]["last_event"] is None
        # No direct seed->TLC-C edge, so role defaults to upstream
        assert nodes_by_tlc["TLC-C"]["role"] == "upstream"

        # Edges were normalized: confidence_score=None preserved as None,
        # 0.95 becomes float.
        edges_by_pair = {(e["input_tlc"], e["output_tlc"]): e
                         for e in result["edges"]}
        assert edges_by_pair[("TLC-A", "TLC-B")]["confidence_score"] == 0.95
        assert edges_by_pair[("TLC-B", "TLC-C")]["confidence_score"] is None
        assert edges_by_pair[("TLC-A", "TLC-B")]["process_type"] == "transform"

    def test_empty_linked_tlcs_skips_count_query(self):
        # When no transformation links exist, the count query is
        # bypassed and ``tlc_stats`` is empty. The edges query still
        # runs against the empty list.
        persistence = self._persistence([])
        session = _FakeSession(results=[_Result(rows=[])])  # only edges query

        result = fetch_trace_graph_data(
            session, persistence, "tenant-42", "TLC-SEED", 2
        )
        assert len(session.executes) == 1  # only the edges SELECT
        assert result["node_count"] == 0
        assert result["edge_count"] == 0
        assert result["total_events"] == 0
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_seed_only_no_other_tlcs_returns_seed_node(self):
        persistence = self._persistence(["TLC-SOLO"])
        count_rows = [("TLC-SOLO", 5,
                       datetime(2026, 4, 1, tzinfo=timezone.utc),
                       datetime(2026, 4, 2, tzinfo=timezone.utc))]
        session = _FakeSession(results=[
            _Result(rows=count_rows),
            _Result(rows=[]),
        ])

        result = fetch_trace_graph_data(
            session, persistence, "tenant", "TLC-SOLO", 1
        )
        assert result["node_count"] == 1
        assert result["nodes"][0]["is_seed"] is True
        assert result["nodes"][0]["role"] == "seed"
        assert result["nodes"][0]["event_count"] == 5
        assert result["total_events"] == 5

    def test_count_query_uses_dynamic_placeholders(self):
        # Verify the dynamic-placeholder construction matches tlc count.
        persistence = self._persistence(["A", "B", "C", "D"])
        session = _FakeSession(results=[
            _Result(rows=[]),  # count rows
            _Result(rows=[]),  # edge rows
        ])
        fetch_trace_graph_data(session, persistence, "t", "A", 2)

        _stmt, params = session.executes[0]
        # 4 placeholder params tlc_0..tlc_3 plus :tid
        assert params["tid"] == "t"
        assert params["tlc_0"] == "A"
        assert params["tlc_1"] == "B"
        assert params["tlc_2"] == "C"
        assert params["tlc_3"] == "D"

    def test_non_seed_without_direct_edge_is_upstream(self):
        # TLC-UP is linked but has no seed→UP edge, so it's classified
        # as upstream (i.e., the seed is downstream of it).
        persistence = self._persistence(["TLC-SEED", "TLC-UP"])
        session = _FakeSession(results=[
            _Result(rows=[]),  # no counts
            _Result(rows=[("TLC-UP", "TLC-SEED", "transform", 0.5)]),
        ])
        result = fetch_trace_graph_data(
            session, persistence, "t", "TLC-SEED", 2
        )
        nodes_by_tlc = {n["tlc"]: n for n in result["nodes"]}
        # Seed→UP doesn't exist, so TLC-UP is upstream.
        assert nodes_by_tlc["TLC-UP"]["role"] == "upstream"
        assert nodes_by_tlc["TLC-SEED"]["role"] == "seed"

    def test_edges_query_receives_tlc_list_as_array(self):
        persistence = self._persistence(["A", "B"])
        session = _FakeSession(results=[
            _Result(rows=[]),  # counts
            _Result(rows=[]),  # edges
        ])
        fetch_trace_graph_data(session, persistence, "tenant", "A", 1)

        # Second execute is the edges query.
        _stmt, params = session.executes[1]
        assert params["tid"] == "tenant"
        assert params["tlcs"] == ["A", "B"]

    def test_total_events_sums_across_nodes_with_default_zero(self):
        persistence = self._persistence(["A", "B", "C"])
        count_rows = [("A", 10, None, None), ("B", 7, None, None)]
        # C has no stats — defaults to 0 so total = 17
        session = _FakeSession(results=[
            _Result(rows=count_rows),
            _Result(rows=[]),
        ])
        result = fetch_trace_graph_data(session, persistence, "t", "A", 1)
        assert result["total_events"] == 17
