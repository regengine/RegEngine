"""Coverage for app/fda_export/verification.py — verify_export_handler.

Locks:
- 404 when fda_export_log row is missing for (tenant_id, export_id).
- Single-TLC export path: query_events_by_tlc called with stored tlc;
  returned events feed into _generate_csv(); regenerated_hash computed
  from UTF-8-encoded CSV SHA-256; hashes_match reflects equality.
- Full-export path (fda_spreadsheet / fda_package): query_all_events
  called once, then query_events_by_tlc per event; duplicate event ids
  dedup'd by str(event.get("id")).
- 409 for unreproducible export types (e.g., "fda_recall").
- HTTPException pass-through (not wrapped as 500).
- (ImportError | ValueError | RuntimeError | OSError) → 500 with
  generic "Verification failed" detail.
- db_session.close() always invoked in finally when SessionLocal
  succeeded; no-op when SessionLocal itself raised.
- generated_at.isoformat() used when row has datetime; None passed
  through when None.
- start_date / end_date coerced to str() when present, else None.

Issue: #1342
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import HTTPException

from app.fda_export import verification as v


# ---------------------------------------------------------------------------
# Fakes / fixtures
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(self, *, row=None, execute_raises=None):
        self.row = row
        self.execute_raises = execute_raises
        self.execute_calls: list[dict] = []
        self.closed = False

    def execute(self, stmt, params):
        self.execute_calls.append(params)
        if self.execute_raises is not None:
            raise self.execute_raises
        return _FakeResult(self.row)

    def close(self):
        self.closed = True


class _FakePersistence:
    def __init__(self, db_session):
        self.db_session = db_session
        self.tlc_calls: list[dict] = []
        self.all_events_calls: list[dict] = []
        self.tlc_return = []
        self.all_events_return = ([], None)
        self.tlc_side_effect = None  # callable(tlc) -> list

    def query_events_by_tlc(self, *, tenant_id, tlc, start_date, end_date):
        self.tlc_calls.append(
            {
                "tenant_id": tenant_id,
                "tlc": tlc,
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        if self.tlc_side_effect is not None:
            return self.tlc_side_effect(tlc)
        return list(self.tlc_return)

    def query_all_events(self, *, tenant_id, start_date, end_date, event_type, limit):
        self.all_events_calls.append(
            {
                "tenant_id": tenant_id,
                "start_date": start_date,
                "end_date": end_date,
                "event_type": event_type,
                "limit": limit,
            }
        )
        return self.all_events_return


def _install_deps(
    monkeypatch,
    *,
    session: _FakeSession | None = None,
    persistence: _FakePersistence | None = None,
    session_factory_exc: Exception | None = None,
):
    """Install fake shared.database.SessionLocal and shared.cte_persistence.CTEPersistence.

    Returns (session, persistence) for easy assertions.
    """
    sess = session if session is not None else _FakeSession(row=None)
    persist = persistence if persistence is not None else _FakePersistence(sess)

    def _session_factory():
        if session_factory_exc is not None:
            raise session_factory_exc
        return sess

    db_mod = ModuleType("shared.database")
    db_mod.SessionLocal = _session_factory
    monkeypatch.setitem(sys.modules, "shared.database", db_mod)

    def _persistence_cls(db_session):
        # Reuse the provided fake so tests can pre-configure its return values.
        persist.db_session = db_session
        return persist

    cp_mod = ModuleType("shared.cte_persistence")
    cp_mod.CTEPersistence = _persistence_cls
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", cp_mod)

    return sess, persist


def _sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 404 + unreproducible paths
# ---------------------------------------------------------------------------


class TestRowLookup:

    def test_missing_row_raises_404(self, monkeypatch):
        sess, _ = _install_deps(monkeypatch, session=_FakeSession(row=None))
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(v.verify_export_handler("exp-99", "tenant-1"))
        assert exc_info.value.status_code == 404
        assert "exp-99" in exc_info.value.detail
        # Session still closed on 404
        assert sess.closed is True

    def test_execute_passed_export_id_and_tenant_id(self, monkeypatch):
        sess, _ = _install_deps(monkeypatch, session=_FakeSession(row=None))
        with pytest.raises(HTTPException):
            asyncio.run(v.verify_export_handler("exp-1", "t-1"))
        assert sess.execute_calls == [{"eid": "exp-1", "tid": "t-1"}]

    def test_unreproducible_export_type_raises_409(self, monkeypatch):
        """export_type outside {fda_spreadsheet, fda_package} without TLC → 409."""
        row = (
            "fda_recall",  # export_type
            None,  # query_tlc
            None,  # query_start_date
            None,  # query_end_date
            0,  # record_count
            "hash-0",  # export_hash
            None,  # generated_at
        )
        sess, _ = _install_deps(monkeypatch, session=_FakeSession(row=row))
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(v.verify_export_handler("exp-recall", "t"))
        assert exc_info.value.status_code == 409
        assert "fda_recall" in exc_info.value.detail
        assert "not fully reproducible" in exc_info.value.detail
        assert sess.closed is True


# ---------------------------------------------------------------------------
# Single-TLC export verification
# ---------------------------------------------------------------------------


class TestSingleTLCVerification:

    def _make_row(self, *, tlc="TLC-A", start="2026-01-01", end="2026-01-31",
                  count=3, original_hash="orig", generated_at=None):
        return (
            "fda_csv",
            tlc,
            start,
            end,
            count,
            original_hash,
            generated_at,
        )

    def test_hashes_match_path(self, monkeypatch):
        csv_out = "event1\nevent2\nevent3\n"
        original_hash = _sha256_hex(csv_out)
        row = self._make_row(original_hash=original_hash)
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.tlc_return = [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}]
        _install_deps(monkeypatch, session=sess, persistence=persist)

        monkeypatch.setattr(v, "_generate_csv", lambda events: csv_out)
        out = asyncio.run(v.verify_export_handler("exp-1", "tenant-1"))

        assert out["export_id"] == "exp-1"
        assert out["original_hash"] == original_hash
        assert out["regenerated_hash"] == original_hash
        assert out["hashes_match"] is True
        assert out["data_integrity"] == "VERIFIED"
        assert out["current_record_count"] == 3
        # Single TLC path: query_events_by_tlc invoked once with stored tlc
        assert persist.tlc_calls == [
            {"tenant_id": "tenant-1", "tlc": "TLC-A",
             "start_date": "2026-01-01", "end_date": "2026-01-31"}
        ]
        assert persist.all_events_calls == []
        assert sess.closed is True

    def test_hashes_mismatch_path(self, monkeypatch):
        row = self._make_row(original_hash="stored-hash-abc", count=1)
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.tlc_return = [{"id": "e1"}]
        _install_deps(monkeypatch, session=sess, persistence=persist)

        csv_out = "different content"
        monkeypatch.setattr(v, "_generate_csv", lambda events: csv_out)
        out = asyncio.run(v.verify_export_handler("exp-1", "tenant-1"))

        assert out["original_hash"] == "stored-hash-abc"
        assert out["regenerated_hash"] == _sha256_hex(csv_out)
        assert out["hashes_match"] is False
        assert out["data_integrity"] == "MISMATCH_DETECTED"
        assert out["original_record_count"] == 1
        assert out["current_record_count"] == 1

    def test_start_end_date_none_passed_through(self, monkeypatch):
        row = self._make_row(start=None, end=None)
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.tlc_return = []
        _install_deps(monkeypatch, session=sess, persistence=persist)
        monkeypatch.setattr(v, "_generate_csv", lambda events: "")
        asyncio.run(v.verify_export_handler("x", "t"))
        call = persist.tlc_calls[0]
        assert call["start_date"] is None
        assert call["end_date"] is None

    def test_non_string_dates_coerced_to_str(self, monkeypatch):
        """date() objects stored in the audit row are stringified for the re-query."""
        from datetime import date
        row = self._make_row(start=date(2026, 2, 1), end=date(2026, 2, 28))
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.tlc_return = []
        _install_deps(monkeypatch, session=sess, persistence=persist)
        monkeypatch.setattr(v, "_generate_csv", lambda events: "")
        asyncio.run(v.verify_export_handler("x", "t"))
        call = persist.tlc_calls[0]
        assert call["start_date"] == "2026-02-01"
        assert call["end_date"] == "2026-02-28"

    def test_generated_at_isoformat_forwarded(self, monkeypatch):
        gen_at = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
        row = self._make_row(generated_at=gen_at, original_hash="h")
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.tlc_return = []
        _install_deps(monkeypatch, session=sess, persistence=persist)
        monkeypatch.setattr(v, "_generate_csv", lambda events: "")
        out = asyncio.run(v.verify_export_handler("x", "t"))
        assert out["original_generated_at"] == "2026-04-01T12:00:00+00:00"

    def test_generated_at_none_forwarded(self, monkeypatch):
        row = self._make_row(generated_at=None)
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.tlc_return = []
        _install_deps(monkeypatch, session=sess, persistence=persist)
        monkeypatch.setattr(v, "_generate_csv", lambda events: "")
        out = asyncio.run(v.verify_export_handler("x", "t"))
        assert out["original_generated_at"] is None

    def test_verified_at_is_isoformat_string(self, monkeypatch):
        row = self._make_row(original_hash="h")
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.tlc_return = []
        _install_deps(monkeypatch, session=sess, persistence=persist)
        monkeypatch.setattr(v, "_generate_csv", lambda events: "")
        out = asyncio.run(v.verify_export_handler("x", "t"))
        # ISO-8601 with timezone
        parsed = datetime.fromisoformat(out["verified_at"])
        assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# Full-export (fda_spreadsheet / fda_package) verification
# ---------------------------------------------------------------------------


class TestFullExportVerification:

    @pytest.mark.parametrize("export_type", ["fda_spreadsheet", "fda_package"])
    def test_full_export_expands_per_tlc_and_dedups(self, monkeypatch, export_type):
        row = (
            export_type,
            None,  # no TLC
            "2026-01-01",
            "2026-01-31",
            0,
            "hash",
            None,
        )
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        # First query returns 2 events with distinct TLCs
        persist.all_events_return = (
            [
                {"id": "e1", "traceability_lot_code": "TLC-X"},
                {"id": "e2", "traceability_lot_code": "TLC-Y"},
            ],
            None,
        )
        # Per-TLC expansion returns overlapping events (e1 appears in both)
        def _by_tlc(tlc):
            if tlc == "TLC-X":
                return [{"id": "e1"}, {"id": "e3"}]
            if tlc == "TLC-Y":
                return [{"id": "e1"}, {"id": "e4"}]  # e1 dup
            return []
        persist.tlc_side_effect = _by_tlc
        _install_deps(monkeypatch, session=sess, persistence=persist)

        captured_events: list = []

        def _gen_csv(events):
            captured_events.extend(events)
            return "csv"

        monkeypatch.setattr(v, "_generate_csv", _gen_csv)
        out = asyncio.run(v.verify_export_handler("exp-full", "t"))

        # query_all_events called once with limit=10000
        assert len(persist.all_events_calls) == 1
        assert persist.all_events_calls[0]["limit"] == 10000
        assert persist.all_events_calls[0]["event_type"] is None

        # query_events_by_tlc called once per event_page entry
        tlc_queried = [c["tlc"] for c in persist.tlc_calls]
        assert tlc_queried == ["TLC-X", "TLC-Y"]

        # Dedup by str(id): e1 should only appear once
        event_ids = [str(e.get("id")) for e in captured_events]
        assert event_ids.count("e1") == 1
        assert set(event_ids) == {"e1", "e3", "e4"}
        assert out["current_record_count"] == 3

    def test_full_export_empty_page(self, monkeypatch):
        row = ("fda_spreadsheet", None, None, None, 0, "h", None)
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.all_events_return = ([], None)
        _install_deps(monkeypatch, session=sess, persistence=persist)
        monkeypatch.setattr(v, "_generate_csv", lambda events: "")
        out = asyncio.run(v.verify_export_handler("x", "t"))
        # No per-TLC calls when query_all_events returns []
        assert persist.tlc_calls == []
        assert out["current_record_count"] == 0

    def test_full_export_events_with_none_id_dedup_by_str(self, monkeypatch):
        """Dedup key is str(event.get('id')) — None → 'None', still dedupes."""
        row = ("fda_package", None, None, None, 0, "h", None)
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.all_events_return = (
            [{"id": None, "traceability_lot_code": "TLC-Z"}],
            None,
        )
        persist.tlc_side_effect = lambda tlc: [{"id": None}, {"id": None}]
        _install_deps(monkeypatch, session=sess, persistence=persist)
        captured: list = []
        monkeypatch.setattr(
            v, "_generate_csv", lambda events: (captured.extend(events), "x")[1]
        )
        out = asyncio.run(v.verify_export_handler("x", "t"))
        assert len(captured) == 1  # both None-ids collapse to one
        assert out["current_record_count"] == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:

    def test_http_exception_passes_through(self, monkeypatch):
        """409/404 raised inside the try-block is re-raised as-is."""
        row = ("fda_recall", None, None, None, 0, "h", None)
        sess = _FakeSession(row=row)
        _install_deps(monkeypatch, session=sess)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(v.verify_export_handler("x", "t"))
        # It's a 409 from the unreproducible branch — not wrapped as 500
        assert exc_info.value.status_code == 409
        assert sess.closed is True

    @pytest.mark.parametrize("exc", [
        ImportError("missing mod"),
        ValueError("bad value"),
        RuntimeError("boom"),
        OSError("disk"),
    ])
    def test_generic_caught_exceptions_become_500(self, monkeypatch, exc):
        sess = _FakeSession(execute_raises=exc)
        _install_deps(monkeypatch, session=sess)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(v.verify_export_handler("x", "t"))
        assert exc_info.value.status_code == 500
        assert "Verification failed" in exc_info.value.detail
        # Session still closed in finally
        assert sess.closed is True

    def test_uncaught_exception_does_not_become_500(self, monkeypatch):
        """KeyError is NOT in the handler's catch tuple → propagates."""
        sess = _FakeSession(execute_raises=KeyError("unhandled"))
        _install_deps(monkeypatch, session=sess)
        with pytest.raises(KeyError):
            asyncio.run(v.verify_export_handler("x", "t"))
        # finally still closes the session
        assert sess.closed is True

    def test_sessionlocal_factory_exception_finally_noop(self, monkeypatch):
        """SessionLocal() raising OSError → db_session stays None, finally no-ops.

        The OSError is caught by the except tuple and becomes 500.
        """
        _install_deps(
            monkeypatch,
            session_factory_exc=OSError("cannot connect"),
        )
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(v.verify_export_handler("x", "t"))
        assert exc_info.value.status_code == 500

    def test_generate_csv_raises_value_error(self, monkeypatch):
        """Downstream CSV generation raising ValueError is mapped to 500."""
        row = ("fda_csv", "TLC-A", "2026-01-01", "2026-01-31", 1, "h", None)
        sess = _FakeSession(row=row)
        persist = _FakePersistence(sess)
        persist.tlc_return = [{"id": "e1"}]
        _install_deps(monkeypatch, session=sess, persistence=persist)

        def _raise(events):
            raise ValueError("bad csv")

        monkeypatch.setattr(v, "_generate_csv", _raise)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(v.verify_export_handler("x", "t"))
        assert exc_info.value.status_code == 500
        assert sess.closed is True
