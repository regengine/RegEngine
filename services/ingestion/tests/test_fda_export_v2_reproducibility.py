"""Reproducibility of v2 FDA exports (canonical model).

Two defects, one regulatory consequence:

1. ``log_v2_export`` / ``log_recall_export`` never persisted the
   ``include_pii`` flag (and ``log_v2_export`` never persisted the
   ``event_type`` filter) even though migration v114 added the
   ``include_pii`` / ``query_event_type`` columns for exactly this
   purpose. Every v2 export therefore verified as "predates capture".

2. ``verify_export_handler`` regenerated *every* TLC-scoped export with
   the v1 query plus the v1 CSV builder. V2 bytes carry four appended
   compliance columns, so a v2 TLC export could never reproduce its
   stored hash: untampered v2 exports verified as MISMATCH_DETECTED,
   a false tamper verdict against a regulator-facing artifact.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from datetime import datetime, timezone
from types import ModuleType

import pytest
from app.fda_export import verification as v
from app.fda_export.queries import log_recall_export, log_v2_export
from app.fda_export_service import _generate_csv_v2
from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return list(self._rows)


class _ScriptedSession:
    """Return scripted results in call order; capture every execute."""

    def __init__(self, results):
        self._results = list(results)
        self.executes: list[tuple[object, dict]] = []
        self.commits = 0
        self.closed = False

    def execute(self, stmt, params=None):
        self.executes.append((stmt, dict(params or {})))
        return self._results.pop(0)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class _NoV1Persistence:
    """CTEPersistence stand-in that forbids the legacy v1 read path.

    A v2 verification must never touch ``query_events_by_tlc``; if the
    handler under test takes the old branch this raises instead of
    returning plausible data.
    """

    def __init__(self, db_session):
        self.db_session = db_session

    def query_events_by_tlc(self, **kwargs):
        raise AssertionError("v2 verification must not use the v1 TLC query path")

    def query_all_events(self, **kwargs):
        raise AssertionError("v2 verification must not use the full-export helper")


def _install(monkeypatch, session):
    def _factory():
        return session

    db_mod = ModuleType("shared.database")
    db_mod.SessionLocal = _factory
    monkeypatch.setitem(sys.modules, "shared.database", db_mod)

    cp_mod = ModuleType("shared.cte_persistence")
    cp_mod.CTEPersistence = _NoV1Persistence
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", cp_mod)


def _v2_row(
    event_id="evt-1",
    event_type="shipping",
    tlc="TLC-V2",
    rule_results=None,
):
    ts = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
    return (
        event_id,  # event_id
        event_type,  # event_type
        tlc,  # traceability_lot_code
        "Cheddar",  # product_description
        10,  # quantity
        "kg",  # unit_of_measure
        ts,  # event_timestamp
        "1234567890123",  # location_gln
        "Warehouse A",  # location_name
        "csv-upload",  # source
        "a" * 64,  # sha256_hash
        "b" * 64,  # chain_hash
        {"ship_from_location": "Farm F"},  # kdes
        {"ingest": "test"},  # provenance
        rule_results if rule_results is not None else [],  # rule_results
        ts,  # ingested_at
        "pass",  # evaluation_verdict
        None,  # no_verdict_reason
    )


def _audit_row(
    export_type="v2_spreadsheet",
    tlc="TLC-V2",
    start="2026-04-01",
    end="2026-04-10",
    count=1,
    export_hash="h" * 64,
    include_pii=False,
    event_type=None,
):
    return (
        export_type,
        tlc,
        start,
        end,
        count,
        export_hash,
        datetime(2026, 4, 11, 0, 0, 0, tzinfo=timezone.utc),
        include_pii,
        event_type,
    )


# ---------------------------------------------------------------------------
# Audit-log persistence
# ---------------------------------------------------------------------------


class TestV2AuditLogPersistence:
    def test_v2_log_persists_pii_flag_and_event_type(self):
        session = _ScriptedSession([_Result()])
        log_v2_export(
            db_session=session,
            tenant_id="t-1",
            events=[{}, {}],
            export_hash="h" * 64,
            format="csv",
            tlc="TLC-V2",
            start_date="2026-04-01",
            end_date="2026-04-10",
            include_pii=True,
            event_type="shipping",
        )
        assert session.commits == 1
        params = session.executes[0][1]
        assert params["pii"] is True
        assert params["qetype"] == "shipping"

    def test_v2_log_defaults_to_redacted_no_event_type(self):
        session = _ScriptedSession([_Result()])
        log_v2_export(
            db_session=session,
            tenant_id="t-1",
            events=[],
            export_hash="h",
            format="package",
            tlc=None,
            start_date=None,
            end_date=None,
        )
        params = session.executes[0][1]
        assert params["pii"] is False
        assert params["qetype"] is None
        assert params["etype"] == "v2_package"

    def test_recall_log_persists_pii_flag(self):
        session = _ScriptedSession([_Result()])
        log_recall_export(
            db_session=session,
            tenant_id="t-1",
            events=[{}],
            export_hash="h" * 64,
            format="csv",
            tlc=None,
            start_date=None,
            end_date=None,
            include_pii=True,
        )
        params = session.executes[0][1]
        assert params["pii"] is True

    def test_recall_log_defaults_to_redacted(self):
        session = _ScriptedSession([_Result()])
        log_recall_export(
            db_session=session,
            tenant_id="t-1",
            events=[{}],
            export_hash="h",
            format="csv",
            tlc=None,
            start_date=None,
            end_date=None,
        )
        assert session.executes[0][1]["pii"] is False


# ---------------------------------------------------------------------------
# Verify handler: v2 reconstruction
# ---------------------------------------------------------------------------


class TestVerifyV2Exports:
    def test_v2_tlc_export_verifies_with_v2_csv(self, monkeypatch):
        from app.fda_export.queries import v2_rows_to_event_dicts

        rows = [_v2_row()]
        events = v2_rows_to_event_dicts(rows)
        original_hash = hashlib.sha256(
            _generate_csv_v2(events, include_pii=False).encode("utf-8")
        ).hexdigest()
        session = _ScriptedSession(
            [
                _Result(row=_audit_row(export_hash=original_hash)),
                _Result(rows=rows),
            ]
        )
        _install(monkeypatch, session)

        out = asyncio.run(v.verify_export_handler("exp-v2", "t-1"))

        assert out["hashes_match"] is True
        assert out["data_integrity"] == "VERIFIED"
        assert out["regenerated_hash"] == original_hash
        assert session.closed is True

    def test_v2_full_export_applies_stored_event_type_filter(self, monkeypatch):
        from app.fda_export.queries import v2_rows_to_event_dicts

        rows = [_v2_row(event_type="receiving")]
        events = v2_rows_to_event_dicts(rows)
        original_hash = hashlib.sha256(
            _generate_csv_v2(events, include_pii=False).encode("utf-8")
        ).hexdigest()
        session = _ScriptedSession(
            [
                _Result(
                    row=_audit_row(
                        export_type="v2_package",
                        tlc=None,
                        export_hash=original_hash,
                        event_type="receiving",
                    )
                ),
                _Result(rows=rows),
            ]
        )
        _install(monkeypatch, session)

        out = asyncio.run(v.verify_export_handler("exp-v2-full", "t-1"))

        assert out["hashes_match"] is True
        assert out["data_integrity"] == "VERIFIED"
        # The stored CTE-type filter must reach the regeneration query.
        v2_params = session.executes[1][1]
        assert v2_params["etype"] == "receiving"

    def test_v2_row_predating_pii_capture_fails_closed(self, monkeypatch):
        session = _ScriptedSession(
            [_Result(row=_audit_row(export_hash="h" * 64, include_pii=None))]
        )
        _install(monkeypatch, session)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(v.verify_export_handler("exp-v2-old", "t-1"))

        assert exc_info.value.status_code == 409
        assert session.closed is True
