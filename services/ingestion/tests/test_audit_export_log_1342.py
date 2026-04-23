"""Coverage for app/audit_export_log.py — export audit trail + activity feed.

Locks:
- Pydantic response models (ExportRecord/VerificationRecord/ActivityEntry)
- _query_exports: happy path with date filters, DB exception returns None,
  missing columns handled, non-datetime created_at stringified
- _query_verifications: happy path, exception returns None, JSON-string
  errors unpacked, list errors passthrough
- _get_verification_fallback: in-memory store merge, ordering
- _query_ingestions: happy path + exception returns []
- POST /exports/{tid}: DB None → empty 200, happy path, default body
- POST /verifications/{tid}: DB None → fallback, default body
- GET /activity/{tid}: merges exports/verifications/ingestions, sorts
  by timestamp desc, paginates

Issue: #1342
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import audit_export_log as ael
from app.audit_export_log import (
    ActivityEntry,
    ActivityFeedResponse,
    ExportAuditResponse,
    ExportQueryRequest,
    ExportRecord,
    VerificationHistoryResponse,
    VerificationQueryRequest,
    VerificationRecord,
    _get_verification_fallback,
    _query_exports,
    _query_ingestions,
    _query_verifications,
    router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_stores():
    """Reset in-memory stores between tests."""
    with ael._verification_store_lock:
        ael._verification_store.clear()
    yield
    with ael._verification_store_lock:
        ael._verification_store.clear()


def _app():
    """Build a FastAPI with the router mounted and auth bypassed."""
    app = FastAPI()
    app.include_router(router)
    from app.webhook_compat import _verify_api_key
    bypass = lambda: None
    app.dependency_overrides[_verify_api_key] = bypass
    app.dependency_overrides[ael._verify_api_key] = bypass
    return app


class _FakeSession:
    def __init__(self, *, rows=None, raises=False):
        self._rows = rows or []
        self._raises = raises
        self.closed = False

    def execute(self, stmt, params=None):
        if self._raises:
            raise RuntimeError("DB down")
        return SimpleNamespace(fetchall=lambda: self._rows)

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_export_record_minimal(self):
        r = ExportRecord(id="x", tenant_id="t")
        assert r.record_count == 0
        assert r.sha256_hash is None

    def test_export_record_all_fields(self):
        r = ExportRecord(
            id="e-1", tenant_id="t", export_type="fda",
            record_count=5, sha256_hash="abc", created_at="2026-01-01",
            traceability_lot_code="TLC", format="json",
        )
        assert r.export_type == "fda"
        assert r.record_count == 5

    def test_export_audit_response_defaults(self):
        r = ExportAuditResponse(tenant_id="t")
        assert r.exports == []
        assert r.total == 0

    def test_export_query_request_limit_clamped(self):
        with pytest.raises(Exception):
            ExportQueryRequest(limit=0)
        with pytest.raises(Exception):
            ExportQueryRequest(limit=501)
        assert ExportQueryRequest(limit=500).limit == 500

    def test_verification_record_defaults(self):
        v = VerificationRecord(id="v", tenant_id="t")
        assert v.chain_length == 0
        assert v.errors == []

    def test_verification_response_defaults(self):
        r = VerificationHistoryResponse(tenant_id="t")
        assert r.verifications == []
        assert r.total == 0

    def test_verification_query_request_bounds(self):
        with pytest.raises(Exception):
            VerificationQueryRequest(limit=0)
        assert VerificationQueryRequest().limit == 50

    def test_activity_entry_required_fields(self):
        e = ActivityEntry(
            id="x", tenant_id="t", activity_type="export",
            summary="s", timestamp="2026-01-01",
        )
        assert e.details is None

    def test_activity_feed_response_defaults(self):
        r = ActivityFeedResponse(tenant_id="t")
        assert r.activities == []
        assert r.total == 0
        assert r.page == 1
        assert r.page_size == 50

    def test_default_factory_independence(self):
        a = ExportAuditResponse(tenant_id="a")
        b = ExportAuditResponse(tenant_id="b")
        a.exports.append(ExportRecord(id="x", tenant_id="a"))
        assert b.exports == []


# ---------------------------------------------------------------------------
# _query_exports
# ---------------------------------------------------------------------------


class TestQueryExports:
    def test_happy_path(self, monkeypatch):
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        row = ("e1", "t", "fda", 5, "hash", dt, "TLC-1", "json")
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_exports("t", None, None, 50)
        assert result[0]["id"] == "e1"
        assert result[0]["created_at"].startswith("2026-01-15")
        assert result[0]["record_count"] == 5
        assert sess.closed is True

    def test_record_count_none_normalized(self, monkeypatch):
        row = ("e1", "t", "fda", None, "h", None, "TLC", "json")
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_exports("t", None, None, 50)
        assert result[0]["record_count"] == 0
        assert result[0]["created_at"] is None

    def test_created_at_non_datetime_stringified(self, monkeypatch):
        row = ("e1", "t", "fda", 1, "h", "2026-01-15T00:00:00", "TLC", "json")
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_exports("t", None, None, 50)
        assert result[0]["created_at"] == "2026-01-15T00:00:00"

    def test_date_filters_included_in_params(self, monkeypatch):
        captured = {}
        class _Sess:
            def execute(self, stmt, params):
                captured.update(params)
                return SimpleNamespace(fetchall=lambda: [])
            def close(self):
                pass
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: _Sess())
        _query_exports("t", "2026-01-01", "2026-01-31", 25)
        assert captured["start"] == "2026-01-01"
        assert captured["end"] == "2026-01-31"
        assert captured["lim"] == 25

    def test_db_exception_returns_none(self, monkeypatch):
        import shared.database as shared_db
        monkeypatch.setattr(
            shared_db, "SessionLocal",
            lambda: _FakeSession(raises=True),
        )
        assert _query_exports("t", None, None, 50) is None

    def test_sessionlocal_factory_raises(self, monkeypatch):
        import shared.database as shared_db
        def _boom():
            raise RuntimeError("no db")
        monkeypatch.setattr(shared_db, "SessionLocal", _boom)
        assert _query_exports("t", None, None, 50) is None


# ---------------------------------------------------------------------------
# _query_verifications
# ---------------------------------------------------------------------------


class TestQueryVerifications:
    def test_happy_path_with_list_errors(self, monkeypatch):
        dt = datetime(2026, 1, 15, tzinfo=timezone.utc)
        row = ("v1", "t", True, 100, ["err1", "err2"], dt)
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_verifications("t", 10)
        assert result[0]["chain_valid"] is True
        assert result[0]["errors"] == ["err1", "err2"]

    def test_json_string_errors_unpacked(self, monkeypatch):
        row = ("v1", "t", False, 5, '["e1", "e2"]', None)
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_verifications("t", 10)
        assert result[0]["errors"] == ["e1", "e2"]
        assert result[0]["completed_at"] is None

    def test_none_errors_returns_empty_list(self, monkeypatch):
        row = ("v1", "t", True, 0, None, None)
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_verifications("t", 10)
        assert result[0]["errors"] == []

    def test_db_exception_returns_none(self, monkeypatch):
        import shared.database as shared_db
        monkeypatch.setattr(
            shared_db, "SessionLocal",
            lambda: _FakeSession(raises=True),
        )
        assert _query_verifications("t", 10) is None

    def test_completed_at_string_stringified(self, monkeypatch):
        row = ("v1", "t", True, 0, [], "2026-01-15")
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_verifications("t", 10)
        assert result[0]["completed_at"] == "2026-01-15"


# ---------------------------------------------------------------------------
# _get_verification_fallback
# ---------------------------------------------------------------------------


class TestVerificationFallback:
    def test_local_store_only(self):
        ael._verification_store["v1"] = {
            "id": "v1", "tenant_id": "t", "chain_valid": True,
            "chain_length": 10, "errors": [],
            "completed_at": "2026-01-01",
        }
        result = _get_verification_fallback("t", 10)
        assert len(result) == 1
        assert result[0]["id"] == "v1"

    def test_wrong_tenant_excluded(self):
        ael._verification_store["v1"] = {
            "id": "v1", "tenant_id": "other",
            "completed_at": "2026-01-01",
        }
        result = _get_verification_fallback("t", 10)
        assert result == []

    def test_chain_verification_job_merge(self, monkeypatch):
        import threading
        import sys
        fake_job_module = SimpleNamespace(
            _verification_jobs={
                "j1": {
                    "tenant_id": "t", "status": "completed",
                    "chain_valid": False, "chain_length": 5,
                    "errors": ["x"], "completed_at": "2026-01-02",
                },
                "j2": {
                    "tenant_id": "t", "status": "running",  # excluded
                    "completed_at": "2026-01-03",
                },
                "j3": {
                    "tenant_id": "other", "status": "completed",  # excluded
                    "completed_at": "2026-01-04",
                },
            },
            _verification_lock=threading.Lock(),
        )
        monkeypatch.setitem(sys.modules, "app.chain_verification_job", fake_job_module)
        result = _get_verification_fallback("t", 10)
        assert len(result) == 1
        assert result[0]["id"] == "j1"
        assert result[0]["chain_valid"] is False

    def test_chain_verification_job_import_error_handled(self, monkeypatch):
        import sys
        # Cause ImportError by setting module to None (Python sees as unavailable)
        monkeypatch.setitem(sys.modules, "app.chain_verification_job", None)
        ael._verification_store["v1"] = {"id": "v1", "tenant_id": "t", "completed_at": "2026-01-01"}
        result = _get_verification_fallback("t", 10)
        assert result[0]["id"] == "v1"

    def test_sorted_desc_by_completed_at(self):
        ael._verification_store["v1"] = {"id": "v1", "tenant_id": "t", "completed_at": "2026-01-01"}
        ael._verification_store["v2"] = {"id": "v2", "tenant_id": "t", "completed_at": "2026-01-03"}
        ael._verification_store["v3"] = {"id": "v3", "tenant_id": "t", "completed_at": "2026-01-02"}
        result = _get_verification_fallback("t", 10)
        assert [r["id"] for r in result] == ["v2", "v3", "v1"]

    def test_limit_applied(self):
        for i in range(5):
            ael._verification_store[f"v{i}"] = {
                "id": f"v{i}", "tenant_id": "t", "completed_at": f"2026-01-0{i+1}",
            }
        result = _get_verification_fallback("t", 3)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# _query_ingestions
# ---------------------------------------------------------------------------


class TestQueryIngestions:
    def test_happy_path(self, monkeypatch):
        dt = datetime(2026, 1, 15, tzinfo=timezone.utc)
        row = ("i1", "t", "shipping", "TLC-42", dt)
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_ingestions("t", 10)
        assert result[0]["id"] == "i1"
        assert result[0]["activity_type"] == "ingestion"
        assert "shipping" in result[0]["summary"]
        assert "TLC-42" in result[0]["summary"]
        assert result[0]["details"]["event_type"] == "shipping"

    def test_timestamp_non_datetime(self, monkeypatch):
        row = ("i1", "t", "shipping", "TLC", "2026-01-01")
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_ingestions("t", 10)
        assert result[0]["timestamp"] == "2026-01-01"

    def test_timestamp_none(self, monkeypatch):
        row = ("i1", "t", "shipping", "TLC", None)
        sess = _FakeSession(rows=[row])
        import shared.database as shared_db
        monkeypatch.setattr(shared_db, "SessionLocal", lambda: sess)
        result = _query_ingestions("t", 10)
        assert result[0]["timestamp"] == ""

    def test_exception_returns_empty(self, monkeypatch):
        import shared.database as shared_db
        monkeypatch.setattr(
            shared_db, "SessionLocal",
            lambda: _FakeSession(raises=True),
        )
        assert _query_ingestions("t", 10) == []


# ---------------------------------------------------------------------------
# POST /exports/{tid}
# ---------------------------------------------------------------------------


class TestExportsEndpoint:
    def test_db_unavailable_returns_empty(self, monkeypatch):
        monkeypatch.setattr(ael, "_query_exports", lambda *a, **k: None)
        app = _app()
        client = TestClient(app)
        resp = client.post("/api/v1/audit/exports/t1", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        assert body["exports"] == []
        assert body["total"] == 0

    def test_happy_path_returns_records(self, monkeypatch):
        monkeypatch.setattr(
            ael, "_query_exports",
            lambda *a, **k: [
                {"id": "e1", "tenant_id": "t1", "export_type": "fda",
                 "record_count": 3, "sha256_hash": None, "created_at": None,
                 "traceability_lot_code": None, "format": None},
            ],
        )
        app = _app()
        client = TestClient(app)
        resp = client.post(
            "/api/v1/audit/exports/t1",
            json={"start_date": "2026-01-01", "limit": 10},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["exports"][0]["id"] == "e1"

    def test_no_body_uses_defaults(self, monkeypatch):
        captured = {}
        def _q(tid, s, e, lim):
            captured["s"] = s
            captured["e"] = e
            captured["lim"] = lim
            return []
        monkeypatch.setattr(ael, "_query_exports", _q)
        app = _app()
        client = TestClient(app)
        resp = client.post("/api/v1/audit/exports/t1")
        assert resp.status_code == 200
        assert captured["s"] is None
        assert captured["e"] is None
        assert captured["lim"] == 50


# ---------------------------------------------------------------------------
# POST /verifications/{tid}
# ---------------------------------------------------------------------------


class TestVerificationsEndpoint:
    def test_db_happy_path(self, monkeypatch):
        monkeypatch.setattr(
            ael, "_query_verifications",
            lambda tid, lim: [
                {"id": "v1", "tenant_id": tid, "chain_valid": True,
                 "chain_length": 10, "errors": [], "completed_at": None},
            ],
        )
        app = _app()
        client = TestClient(app)
        resp = client.post("/api/v1/audit/verifications/t1", json={"limit": 10})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_db_none_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setattr(ael, "_query_verifications", lambda tid, lim: None)
        ael._verification_store["v1"] = {
            "id": "v1", "tenant_id": "t1", "chain_valid": True,
            "chain_length": 5, "errors": [], "completed_at": "2026-01-01",
        }
        app = _app()
        client = TestClient(app)
        resp = client.post("/api/v1/audit/verifications/t1", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["verifications"][0]["id"] == "v1"

    def test_no_body_defaults(self, monkeypatch):
        captured = {}
        def _q(tid, lim):
            captured["lim"] = lim
            return []
        monkeypatch.setattr(ael, "_query_verifications", _q)
        app = _app()
        client = TestClient(app)
        resp = client.post("/api/v1/audit/verifications/t1")
        assert resp.status_code == 200
        assert captured["lim"] == 50


# ---------------------------------------------------------------------------
# GET /activity/{tid}
# ---------------------------------------------------------------------------


class TestActivityFeedEndpoint:
    def test_combined_feed_sorts_desc(self, monkeypatch):
        monkeypatch.setattr(
            ael, "_query_exports",
            lambda *a, **k: [
                {"id": "e1", "tenant_id": "t1", "export_type": "fda",
                 "record_count": 3, "sha256_hash": "h",
                 "created_at": "2026-01-10", "traceability_lot_code": "T",
                 "format": "json"},
            ],
        )
        monkeypatch.setattr(
            ael, "_query_verifications",
            lambda *a, **k: [
                {"id": "v1", "tenant_id": "t1", "chain_valid": True,
                 "chain_length": 5, "errors": [],
                 "completed_at": "2026-01-20"},
            ],
        )
        monkeypatch.setattr(
            ael, "_query_ingestions",
            lambda *a, **k: [
                {"id": "i1", "tenant_id": "t1", "activity_type": "ingestion",
                 "summary": "CTE", "timestamp": "2026-01-15",
                 "details": {"event_type": "shipping"}},
            ],
        )
        app = _app()
        client = TestClient(app)
        resp = client.get("/api/v1/audit/activity/t1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        # Verification latest, then ingestion, then export
        types = [a["activity_type"] for a in body["activities"]]
        assert types == ["verification", "ingestion", "export"]

    def test_pagination(self, monkeypatch):
        def _exp(*a, **k):
            return [
                {"id": f"e{i}", "tenant_id": "t1", "export_type": "x",
                 "record_count": 1, "sha256_hash": None,
                 "created_at": f"2026-01-{i:02d}", "traceability_lot_code": None,
                 "format": None}
                for i in range(1, 11)
            ]
        monkeypatch.setattr(ael, "_query_exports", _exp)
        monkeypatch.setattr(ael, "_query_verifications", lambda *a, **k: [])
        monkeypatch.setattr(ael, "_query_ingestions", lambda *a, **k: [])
        app = _app()
        client = TestClient(app)
        resp = client.get("/api/v1/audit/activity/t1?page=2&page_size=3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 2
        assert body["page_size"] == 3
        assert len(body["activities"]) == 3
        assert body["total"] == 10

    def test_chain_invalid_marks_failed(self, monkeypatch):
        monkeypatch.setattr(ael, "_query_exports", lambda *a, **k: [])
        monkeypatch.setattr(
            ael, "_query_verifications",
            lambda *a, **k: [
                {"id": "v1", "tenant_id": "t1", "chain_valid": False,
                 "chain_length": 3, "errors": ["e1"],
                 "completed_at": "2026-01-01"},
            ],
        )
        monkeypatch.setattr(ael, "_query_ingestions", lambda *a, **k: [])
        app = _app()
        client = TestClient(app)
        resp = client.get("/api/v1/audit/activity/t1")
        assert resp.status_code == 200
        summary = resp.json()["activities"][0]["summary"]
        assert "failed" in summary

    def test_verifications_db_none_falls_back(self, monkeypatch):
        """_query_verifications returns None → fallback used."""
        monkeypatch.setattr(ael, "_query_exports", lambda *a, **k: [])
        monkeypatch.setattr(ael, "_query_verifications", lambda *a, **k: None)
        monkeypatch.setattr(ael, "_query_ingestions", lambda *a, **k: [])
        ael._verification_store["v1"] = {
            "id": "v1", "tenant_id": "t", "chain_valid": True,
            "chain_length": 0, "errors": [], "completed_at": "2026-01-01",
        }
        app = _app()
        client = TestClient(app)
        resp = client.get("/api/v1/audit/activity/t")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["activities"][0]["id"] == "v1"

    def test_exports_raw_falsy_skipped(self, monkeypatch):
        """If _query_exports returns None (DB error), exports section skipped."""
        monkeypatch.setattr(ael, "_query_exports", lambda *a, **k: None)
        monkeypatch.setattr(ael, "_query_verifications", lambda *a, **k: [])
        monkeypatch.setattr(ael, "_query_ingestions", lambda *a, **k: [])
        app = _app()
        client = TestClient(app)
        resp = client.get("/api/v1/audit/activity/t")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix(self):
        assert router.prefix == "/api/v1/audit"

    def test_tag(self):
        assert "Audit Trail" in router.tags

    def test_routes_registered(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/audit/exports/{tenant_id}" in paths
        assert "/api/v1/audit/verifications/{tenant_id}" in paths
        assert "/api/v1/audit/activity/{tenant_id}" in paths
