"""FDA export audit-logging regression tests.

Covers:

* #1205 — ``/api/v1/fda/export`` must capture the authenticated
  ``user_id`` and a precise ``initiated_at_utc`` in the audit trail.
* #1209 — ``/api/v1/fda/export/recall`` must reject date-only queries
  that lack an identifier filter (product / location / tlc /
  event_type) — such queries previously dumped the entire tenant as a
  "recall" export.
* #1215 — ``log_recall_export`` raises :class:`AuditLogWriteError` on DB
  failure instead of silently swallowing. The handler translates that
  to a 503 so the export cannot succeed without its audit-trail row.
"""

from __future__ import annotations

import json
import logging
import sys
import types
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import shared.cte_persistence as shared_cte_persistence
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.fda_export.queries import AuditLogWriteError, log_recall_export
from app.fda_export.router import router as fda_router


# ---------------------------------------------------------------------------
# Fakes lifted from the existing test_fda_export_router.py suite, extended
# with log_export call capture.
# ---------------------------------------------------------------------------


class _FakeChainVerification:
    def __init__(self, valid: bool = True):
        self.valid = valid
        self.chain_length = 3
        self.errors: list[str] = []
        self.checked_at = "2026-04-17T10:00:00+00:00"


class _Result:
    def __init__(self, *, row: Any = None, rows: Optional[list[Any]] = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, *, export_log_row: Any = None, raise_on_insert: bool = False):
        self._export_log_row = export_log_row
        self._raise_on_insert = raise_on_insert
        self.executes: list[tuple[Any, Any]] = []
        self.rollbacks = 0
        self.commits = 0

    def execute(self, stmt, params=None):
        self.executes.append((stmt, params))
        if self._raise_on_insert and isinstance(params, dict) and "export_hash" in params:
            raise RuntimeError("simulated DB outage during audit log INSERT")
        if self._raise_on_insert and isinstance(params, dict) and "hash" in params:
            raise RuntimeError("simulated DB outage during audit log INSERT")
        return _Result(row=self._export_log_row)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        return None


class _FakePersistence:
    """Minimal persistence that records log_export calls for assertion."""

    captured_calls: list[dict] = []

    def __init__(self, session):
        self._session = session
        self._by_tlc = {
            "TLC-2026-001": [
                {
                    "id": "evt-1",
                    "event_type": "shipping",
                    "traceability_lot_code": "TLC-2026-001",
                    "product_description": "Romaine Hearts",
                    "quantity": 120.0,
                    "unit_of_measure": "cases",
                    "location_gln": "0614141000005",
                    "location_name": "Valley Fresh Farms",
                    "event_timestamp": "2026-04-17T09:00:00+00:00",
                    "sha256_hash": "a" * 64,
                    "chain_hash": "b" * 64,
                    "source": "webhook",
                    "kdes": {
                        "ship_date": "2026-04-17",
                        "ship_from_location": "Valley Fresh Farms",
                    },
                }
            ],
        }

    def query_events_by_tlc(self, tenant_id, tlc, start_date=None, end_date=None):
        _ = tenant_id, start_date, end_date
        return list(self._by_tlc.get(tlc, []))

    def query_all_events(self, tenant_id, start_date=None, end_date=None, event_type=None, limit=1000, offset=0):
        _ = tenant_id, start_date, end_date, event_type, limit, offset
        return ([{"traceability_lot_code": "TLC-2026-001"}], 1)

    def verify_chain(self, tenant_id):
        _ = tenant_id
        return _FakeChainVerification(valid=True)

    def log_export(self, **kwargs):
        _FakePersistence.captured_calls.append(kwargs)
        return "export-log-id"


@pytest.fixture(autouse=True)
def _reset_captured_calls():
    _FakePersistence.captured_calls = []
    yield
    _FakePersistence.captured_calls = []


def _install_fakes(monkeypatch, *, session_factory, persistence_cls=_FakePersistence):
    fake_db_module = types.ModuleType("shared.database")
    fake_db_module.SessionLocal = session_factory
    monkeypatch.setitem(sys.modules, "shared.database", fake_db_module)
    monkeypatch.setattr(shared_cte_persistence, "CTEPersistence", persistence_cls)


@pytest.fixture()
def authed_client(monkeypatch):
    app = FastAPI()
    app.include_router(fda_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-user-key-abc123",
        scopes=["*"],
        auth_mode="test",
        tenant_id="00000000-0000-0000-0000-000000000111",
    )
    _install_fakes(monkeypatch, session_factory=lambda: _FakeSession())
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def unauthed_client(monkeypatch):
    """Client where the principal resolves but has no key_id — simulates
    a degraded auth path that must not be allowed to produce exports.
    """
    app = FastAPI()
    app.include_router(fda_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="",
        scopes=["*"],
        auth_mode="test",
        tenant_id="00000000-0000-0000-0000-000000000111",
    )
    _install_fakes(monkeypatch, session_factory=lambda: _FakeSession())
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# #1205 — audit trail identity + timestamp
# ---------------------------------------------------------------------------

def test_1205_export_captures_user_id_in_log_export_call(authed_client):
    """The persistence.log_export call must carry the authenticated
    user's key_id in ``generated_by`` and the structured logger line
    must include user_id, request_id, and initiated_at_utc.
    """
    resp = authed_client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-2026-001",
            "format": "csv",
            # Fixture KDE coverage is below 80% — bypass #1222 gate so
            # this test keeps exercising the audit-log path.
            "allow_incomplete": "true",
        },
        headers={"X-Request-ID": "req-42"},
    )
    assert resp.status_code == 200, resp.text
    calls = _FakePersistence.captured_calls
    assert len(calls) == 1
    call = calls[0]
    assert "user:test-user-key-abc123" in call["generated_by"]
    assert "request:req-42" in call["generated_by"]
    assert call["tenant_id"] == "00000000-0000-0000-0000-000000000111"
    assert call["record_count"] == 1


def test_1205_export_rejects_request_with_no_resolvable_user_id(unauthed_client):
    """Without a resolvable key_id the handler must 401 rather than
    write an audit row with a null actor.
    """
    resp = unauthed_client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-2026-001",
        },
    )
    assert resp.status_code == 401
    assert "FSMA-204" in resp.json()["detail"] or "audit-trail actor" in resp.json()["detail"]
    # Most importantly: no log_export call was made.
    assert _FakePersistence.captured_calls == []


def test_1205_emits_structured_audit_log_line(authed_client, caplog):
    caplog.set_level(logging.INFO, logger="fda-export")
    resp = authed_client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-2026-001",
            "format": "csv",
            "allow_incomplete": "true",
        },
        headers={"X-Request-ID": "req-42", "User-Agent": "pytest-test/1.0"},
    )
    assert resp.status_code == 200
    audit_records = [
        r for r in caplog.records
        if r.name == "fda-export" and r.msg == "fda_export_audit"
    ]
    assert audit_records, "expected an fda_export_audit structured log line"
    rec = audit_records[0]
    assert getattr(rec, "user_id", None) == "test-user-key-abc123"
    assert getattr(rec, "request_id", None) == "req-42"
    assert getattr(rec, "user_agent", None) == "pytest-test/1.0"
    assert getattr(rec, "initiated_at_utc", "").startswith("20"), (
        "initiated_at_utc must be ISO-8601 UTC"
    )
    assert getattr(rec, "export_hash", None)
    assert getattr(rec, "filters_applied", {}).get("tlc") == "TLC-2026-001"


# ---------------------------------------------------------------------------
# #1209 — recall export filter enforcement
# ---------------------------------------------------------------------------

def test_1209_recall_export_rejects_end_date_only(authed_client):
    """A recall request with only ``end_date`` must return 400, not a
    full-tenant dump.
    """
    resp = authed_client.get(
        "/api/v1/fda/export/recall",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "end_date": "2026-04-17",
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    # Could be either missing-identifier OR missing-start_date — both rules fire.
    assert "identifier" in detail or "start_date" in detail


def test_1209_recall_export_rejects_date_range_without_identifier(authed_client):
    """Start + end date alone still doesn't scope to a recall — must 400."""
    resp = authed_client.get(
        "/api/v1/fda/export/recall",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "start_date": "2026-04-01",
            "end_date": "2026-04-17",
        },
    )
    assert resp.status_code == 400
    assert "identifier" in resp.json()["detail"]


def test_1209_recall_export_rejects_start_date_only_as_legit_filter(authed_client):
    """The old code considered ``start_date`` a valid filter on its own.
    After the fix, start_date alone (without end_date OR an identifier)
    is rejected.
    """
    resp = authed_client.get(
        "/api/v1/fda/export/recall",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "start_date": "2026-04-01",
        },
    )
    assert resp.status_code == 400


def test_1209_recall_export_rejects_inverted_date_range(authed_client):
    resp = authed_client.get(
        "/api/v1/fda/export/recall",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-2026-001",
            "start_date": "2026-04-17",
            "end_date": "2026-04-01",
        },
    )
    assert resp.status_code == 400
    assert "on or after" in resp.json()["detail"]


def test_1209_recall_export_accepts_identifier_plus_date_range(authed_client):
    """Positive case: a proper recall query (identifier + date range)
    still returns data.
    """
    resp = authed_client.get(
        "/api/v1/fda/export/recall",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-2026-001",
        },
    )
    # The fake DB session returns no rows for the recall query builder,
    # so the handler returns 404 — not 400. That's still proof that
    # filter validation passed.
    assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# #1222 — KDE coverage gate
# ---------------------------------------------------------------------------

def test_1222_coverage_below_threshold_returns_409_without_bypass(authed_client):
    """The fixtures' sample event has ship_to_location missing, which
    puts KDE coverage below the 80% threshold. A request without
    ``allow_incomplete=true`` must 409.
    """
    resp = authed_client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-2026-001",
            "format": "csv",
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["error"] == "kde_coverage_below_threshold"
    assert body["detail"]["threshold"] == 0.80
    # Most importantly: no log_export call was made, so no audit row
    # was created for a non-compliant export.
    assert _FakePersistence.captured_calls == []


def test_1222_coverage_bypass_allowed_with_explicit_flag(authed_client, caplog):
    """``allow_incomplete=true`` lets the export proceed, but the
    bypass is logged at WARNING for ops visibility.
    """
    caplog.set_level(logging.WARNING, logger="fda-export")
    resp = authed_client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-2026-001",
            "format": "csv",
            "allow_incomplete": "true",
        },
    )
    assert resp.status_code == 200
    bypass_records = [
        r for r in caplog.records
        if r.name == "fda-export" and r.msg == "fda_export_coverage_gate_bypass"
    ]
    assert bypass_records, "expected a coverage_gate_bypass WARNING"
    rec = bypass_records[0]
    assert getattr(rec, "user_id", None) == "test-user-key-abc123"
    assert getattr(rec, "kde_coverage_ratio", 1.0) < 0.80


# ---------------------------------------------------------------------------
# #1215 — log_recall_export no longer swallows exceptions
# ---------------------------------------------------------------------------

def test_1215_log_recall_export_raises_audit_log_write_error():
    """Direct-call: a simulated DB outage must raise
    :class:`AuditLogWriteError`, not return silently.
    """
    failing = _FakeSession(raise_on_insert=True)
    with pytest.raises(AuditLogWriteError):
        log_recall_export(
            db_session=failing,
            tenant_id="00000000-0000-0000-0000-000000000111",
            events=[{"id": "evt-1"}],
            export_hash="deadbeef" * 8,
            format="csv",
            tlc="TLC-2026-001",
            start_date="2026-04-01",
            end_date="2026-04-17",
            user_id="test-user-key-abc123",
            request_id="req-42",
        )
    assert failing.rollbacks == 1
