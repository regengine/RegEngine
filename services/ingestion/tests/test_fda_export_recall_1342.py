"""Coverage for app/fda_export/recall.py — export_recall_filtered_handler.

Locks:
- Validation (no DB needed):
    * 400 when no identifier filter (product/location/tlc/event_type).
    * 400 when only start_date or only end_date supplied.
    * 400 when end_date < start_date.
    * Equal dates are accepted.
- DB path:
    * build_recall_where_clause called with all filter kwargs.
    * Empty rows → 404 with filters_used in detail.
    * Rows → events → csv/hash → verify_chain → completeness →
      log_recall_export → response builder (CSV or package).
    * log_recall_export receives full identity kwargs (user_id,
      user_email, request_id, user_agent, source_ip) + filter kwargs.
    * include_pii threaded to generate_csv_and_hash + build_csv_response
      / build_package_response.
- Response routing:
    * format='package' → build_package_response with
      fda_recall_package_<ts>.zip filename.
    * format='csv' (or other) → build_csv_response with
      fda_recall_export_<ts>.csv filename.
- Error handling:
    * HTTPException raised downstream passes through unchanged.
    * AuditLogWriteError → 503 with chain-of-custody message.
    * (ImportError | ValueError | RuntimeError | OSError) → 500.
    * finally closes db_session; SessionLocal-raises → finally no-op.

Issue: #1342
"""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException

from app.fda_export import recall as r
from app.fda_export.queries import AuditLogWriteError


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakePersistence:
    def __init__(self, db_session):
        self.db_session = db_session
        self.verify_return = SimpleNamespace(valid=True)
        self.verify_raises: Exception | None = None

    def verify_chain(self, *, tenant_id):
        if self.verify_raises is not None:
            raise self.verify_raises
        return self.verify_return


def _install_stubs(
    monkeypatch,
    *,
    rows=None,
    events=None,
    session: _FakeSession | None = None,
    persistence: _FakePersistence | None = None,
    verify_return=None,
    verify_raises: Exception | None = None,
    session_factory_raises: Exception | None = None,
    log_raises: Exception | None = None,
    csv_response_marker="CSV-RESP",
    package_response_marker="PKG-RESP",
):
    """Install the dependency web. Returns (session, persistence, captured)."""
    sess = session if session is not None else _FakeSession()
    persist = persistence if persistence is not None else _FakePersistence(sess)
    if verify_return is not None:
        persist.verify_return = verify_return
    if verify_raises is not None:
        persist.verify_raises = verify_raises

    captured: dict = {
        "where_kwargs": None,
        "fetch_args": None,
        "rows_to_events_arg": None,
        "csv_and_hash_args": None,
        "completeness_arg": None,
        "log_kwargs": None,
        "csv_response_kwargs": None,
        "package_response_kwargs": None,
    }

    # shared.database.SessionLocal
    def _session_factory():
        if session_factory_raises is not None:
            raise session_factory_raises
        return sess

    db_mod = ModuleType("shared.database")
    db_mod.SessionLocal = _session_factory
    monkeypatch.setitem(sys.modules, "shared.database", db_mod)

    # shared.cte_persistence.CTEPersistence
    def _persistence_cls(db_session):
        persist.db_session = db_session
        return persist

    cp_mod = ModuleType("shared.cte_persistence")
    cp_mod.CTEPersistence = _persistence_cls
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", cp_mod)

    # Queries helpers
    def _build_where(**kwargs):
        captured["where_kwargs"] = kwargs
        return "WHERE 1=1", {"tenant_id": kwargs["tenant_id"]}

    def _fetch(db_session, where_clause, params):
        captured["fetch_args"] = {
            "where": where_clause,
            "params": params,
        }
        return list(rows) if rows is not None else []

    def _rows_to_events(rs):
        captured["rows_to_events_arg"] = list(rs)
        return list(events) if events is not None else []

    def _log(**kwargs):
        captured["log_kwargs"] = kwargs
        if log_raises is not None:
            raise log_raises

    monkeypatch.setattr(r, "build_recall_where_clause", _build_where)
    monkeypatch.setattr(r, "fetch_recall_events", _fetch)
    monkeypatch.setattr(r, "rows_to_event_dicts", _rows_to_events)
    monkeypatch.setattr(r, "log_recall_export", _log)

    # Formatters
    def _csv_and_hash(evts, *, include_pii=False):
        captured["csv_and_hash_args"] = {
            "events": list(evts),
            "include_pii": include_pii,
        }
        return "csv-content", "csv-hash-abc"

    def _make_ts():
        return "20260419_120000"

    def _build_csv(**kwargs):
        captured["csv_response_kwargs"] = kwargs
        return csv_response_marker

    def _build_pkg(**kwargs):
        captured["package_response_kwargs"] = kwargs
        return package_response_marker

    monkeypatch.setattr(r, "generate_csv_and_hash", _csv_and_hash)
    monkeypatch.setattr(r, "make_timestamp", _make_ts)
    monkeypatch.setattr(r, "build_csv_response", _build_csv)
    monkeypatch.setattr(r, "build_package_response", _build_pkg)

    # _build_completeness_summary
    def _completeness(evts):
        captured["completeness_arg"] = list(evts)
        return {"required_kde_coverage_ratio": 0.95,
                "events_with_missing_required_fields": 0}

    monkeypatch.setattr(r, "_build_completeness_summary", _completeness)

    return sess, persist, captured


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch):
    class _Silent:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
        def debug(self, *a, **k): pass
    monkeypatch.setattr(r, "logger", _Silent())


def _call(**overrides):
    """Invoke the handler with sane defaults; ``overrides`` replace kwargs."""
    kwargs = dict(
        tenant_id="t-1",
        product=None,
        location=None,
        tlc="TLC-A",
        event_type=None,
        start_date=None,
        end_date=None,
        format="csv",
    )
    kwargs.update(overrides)
    return asyncio.run(r.export_recall_filtered_handler(**kwargs))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestIdentifierValidation:

    def test_no_identifier_raises_400(self, monkeypatch):
        _install_stubs(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            _call(tlc=None, product=None, location=None, event_type=None)
        assert exc_info.value.status_code == 400
        assert "at least one identifier filter" in exc_info.value.detail

    @pytest.mark.parametrize("field", ["product", "location", "tlc", "event_type"])
    def test_any_single_identifier_is_enough(self, monkeypatch, field):
        _install_stubs(monkeypatch, rows=[{"id": 1}], events=[{"id": "e1"}])
        kwargs = {"tlc": None, "product": None, "location": None, "event_type": None}
        kwargs[field] = "X"
        resp = _call(**kwargs)
        assert resp == "CSV-RESP"

    def test_empty_strings_count_as_no_identifier(self, monkeypatch):
        """Empty strings are falsy — treated like None by the `any()` check."""
        _install_stubs(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            _call(product="", location="", tlc="", event_type="")
        assert exc_info.value.status_code == 400


class TestDateValidation:

    def test_only_start_date_raises_400(self, monkeypatch):
        _install_stubs(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            _call(start_date="2026-01-01", end_date=None)
        assert exc_info.value.status_code == 400
        assert "Both start_date and end_date" in exc_info.value.detail

    def test_only_end_date_raises_400(self, monkeypatch):
        _install_stubs(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            _call(start_date=None, end_date="2026-01-31")
        assert exc_info.value.status_code == 400

    def test_end_before_start_raises_400(self, monkeypatch):
        _install_stubs(monkeypatch)
        with pytest.raises(HTTPException) as exc_info:
            _call(start_date="2026-02-01", end_date="2026-01-31")
        assert exc_info.value.status_code == 400
        assert "on or after start_date" in exc_info.value.detail

    def test_equal_dates_accepted(self, monkeypatch):
        _install_stubs(monkeypatch, rows=[{"id": 1}], events=[{"id": "e1"}])
        resp = _call(start_date="2026-01-01", end_date="2026-01-01")
        assert resp == "CSV-RESP"


# ---------------------------------------------------------------------------
# No rows → 404
# ---------------------------------------------------------------------------


class TestEmptyQuery:

    def test_no_rows_returns_404_with_all_filters(self, monkeypatch):
        sess, _, cap = _install_stubs(monkeypatch, rows=[])
        with pytest.raises(HTTPException) as exc_info:
            _call(
                product="apple", location="farm-1", tlc="TLC-A",
                event_type="harvesting",
                start_date="2026-01-01", end_date="2026-01-31",
            )
        assert exc_info.value.status_code == 404
        detail = exc_info.value.detail
        assert "product='apple'" in detail
        assert "location='farm-1'" in detail
        assert "tlc='TLC-A'" in detail
        assert "event_type='harvesting'" in detail
        assert "from=2026-01-01" in detail
        assert "to=2026-01-31" in detail
        # Session still closed in finally
        assert sess.closed is True

    def test_no_rows_filter_list_only_includes_set_fields(self, monkeypatch):
        _install_stubs(monkeypatch, rows=[])
        with pytest.raises(HTTPException) as exc_info:
            _call(tlc="TLC-B", product=None, location=None, event_type=None)
        detail = exc_info.value.detail
        assert "tlc='TLC-B'" in detail
        assert "product=" not in detail
        assert "location=" not in detail


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestCSVExport:

    def test_csv_happy_path_full_wiring(self, monkeypatch):
        rows = [{"id": 1}, {"id": 2}]
        events = [{"id": "e1"}, {"id": "e2"}]
        sess, persist, cap = _install_stubs(
            monkeypatch, rows=rows, events=events,
            verify_return=SimpleNamespace(valid=True),
        )
        resp = _call(
            tenant_id="T-1",
            product="apple",
            tlc="TLC-A",
            start_date="2026-01-01",
            end_date="2026-01-31",
            format="csv",
            user_id="u-1",
            user_email="ops@x.com",
            request_id="req-7",
            user_agent="curl",
            source_ip="1.2.3.4",
            include_pii=True,
        )
        assert resp == "CSV-RESP"
        # where clause built with all filter kwargs
        assert cap["where_kwargs"] == {
            "tenant_id": "T-1",
            "product": "apple",
            "location": None,
            "tlc": "TLC-A",
            "event_type": None,
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        }
        # rows forwarded to rows_to_event_dicts
        assert cap["rows_to_events_arg"] == rows
        # CSV hash generation saw events + include_pii
        assert cap["csv_and_hash_args"]["events"] == events
        assert cap["csv_and_hash_args"]["include_pii"] is True
        # completeness summary sees the same events
        assert cap["completeness_arg"] == events
        # Audit log captured identity + filter kwargs
        log = cap["log_kwargs"]
        assert log["tenant_id"] == "T-1"
        assert log["user_id"] == "u-1"
        assert log["user_email"] == "ops@x.com"
        assert log["request_id"] == "req-7"
        assert log["user_agent"] == "curl"
        assert log["source_ip"] == "1.2.3.4"
        assert log["product"] == "apple"
        assert log["tlc"] == "TLC-A"
        assert log["start_date"] == "2026-01-01"
        assert log["end_date"] == "2026-01-31"
        assert log["format"] == "csv"
        assert log["export_hash"] == "csv-hash-abc"
        assert log["events"] == events
        # CSV response kwargs
        csv_k = cap["csv_response_kwargs"]
        assert csv_k["csv_content"] == "csv-content"
        assert csv_k["filename"] == "fda_recall_export_20260419_120000.csv"
        assert csv_k["export_hash"] == "csv-hash-abc"
        assert csv_k["record_count"] == 2
        assert csv_k["chain_valid"] is True
        assert csv_k["extra_headers"]["X-Export-Type"] == "recall"
        assert csv_k["extra_headers"]["X-KDE-Coverage"] == "0.95"
        assert csv_k["include_pii"] is True
        # Session closed
        assert sess.closed is True

    def test_include_pii_defaults_to_false(self, monkeypatch):
        _, _, cap = _install_stubs(
            monkeypatch, rows=[{"id": 1}], events=[{"id": "e1"}]
        )
        _call()
        assert cap["csv_and_hash_args"]["include_pii"] is False
        assert cap["csv_response_kwargs"]["include_pii"] is False

    def test_chain_invalid_reported_in_response(self, monkeypatch):
        _, _, cap = _install_stubs(
            monkeypatch, rows=[{"id": 1}], events=[{"id": "e1"}],
            verify_return=SimpleNamespace(valid=False),
        )
        _call()
        assert cap["csv_response_kwargs"]["chain_valid"] is False

    def test_non_package_format_still_goes_csv_path(self, monkeypatch):
        """Any non-'package' format string routes through build_csv_response."""
        _, _, cap = _install_stubs(
            monkeypatch, rows=[{"id": 1}], events=[{"id": "e1"}]
        )
        _call(format="csv")
        assert cap["csv_response_kwargs"] is not None
        assert cap["package_response_kwargs"] is None


class TestPackageExport:

    def test_package_happy_path(self, monkeypatch):
        events = [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]
        _, _, cap = _install_stubs(
            monkeypatch, rows=[{"id": 1}], events=events,
        )
        resp = _call(format="package", include_pii=False)
        assert resp == "PKG-RESP"
        pkg_k = cap["package_response_kwargs"]
        assert pkg_k["events"] == events
        assert pkg_k["csv_content"] == "csv-content"
        assert pkg_k["export_hash"] == "csv-hash-abc"
        assert pkg_k["filename"] == "fda_recall_package_20260419_120000.zip"
        assert pkg_k["extra_headers"]["X-Export-Type"] == "recall_package"
        assert pkg_k["extra_headers"]["X-KDE-Coverage"] == "0.95"
        assert pkg_k["include_pii"] is False
        # Did NOT go through the CSV response path
        assert cap["csv_response_kwargs"] is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    def test_audit_log_write_error_becomes_503(self, monkeypatch):
        sess, _, _ = _install_stubs(
            monkeypatch, rows=[{"id": 1}], events=[{"id": "e1"}],
            log_raises=AuditLogWriteError("audit-db down"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _call()
        assert exc_info.value.status_code == 503
        assert "audit-log write failed" in exc_info.value.detail
        assert "chain-of-custody" in exc_info.value.detail
        # Session still closed in finally
        assert sess.closed is True

    def test_http_exception_from_verify_chain_passes_through(self, monkeypatch):
        """HTTPException from verify_chain bubbles out without being wrapped."""
        sess, _, _ = _install_stubs(
            monkeypatch, rows=[{"id": 1}], events=[{"id": "e1"}],
            verify_raises=HTTPException(status_code=418, detail="teapot"),
        )
        with pytest.raises(HTTPException) as exc_info:
            _call()
        assert exc_info.value.status_code == 418
        assert exc_info.value.detail == "teapot"
        assert sess.closed is True

    @pytest.mark.parametrize("exc", [
        ImportError("missing mod"),
        ValueError("bad value"),
        RuntimeError("boom"),
        OSError("disk"),
    ])
    def test_caught_exceptions_become_500(self, monkeypatch, exc):
        sess, _, _ = _install_stubs(
            monkeypatch, rows=[{"id": 1}], events=[{"id": "e1"}],
            verify_raises=exc,
        )
        with pytest.raises(HTTPException) as exc_info:
            _call()
        assert exc_info.value.status_code == 500
        assert "Recall export failed" in exc_info.value.detail
        assert sess.closed is True

    def test_uncaught_exception_propagates(self, monkeypatch):
        """KeyError is NOT in the catch tuple → it bubbles out."""
        sess, _, _ = _install_stubs(
            monkeypatch, rows=[{"id": 1}], events=[{"id": "e1"}],
            verify_raises=KeyError("k"),
        )
        with pytest.raises(KeyError):
            _call()
        # finally still closes session
        assert sess.closed is True

    def test_session_factory_failure_finally_noop(self, monkeypatch):
        """SessionLocal() raising OSError → db_session stays None, 500."""
        _install_stubs(monkeypatch, session_factory_raises=OSError("dead"))
        with pytest.raises(HTTPException) as exc_info:
            _call()
        assert exc_info.value.status_code == 500
