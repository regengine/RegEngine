"""Coverage for app/routes_status.py — status / audit / docs / verify routes.

Locks:
- GET /v1/ingest/status/{job_id}: 404 on missing, non-completed status
  (no result fetch), completed+result present, completed+no result
- GET /v1/ingest/documents/{document_id}/analysis: 404 on missing,
  result_raw present, result_raw absent → defaults
- GET /v1/audit/jobs/{job_id}: 503 when no db_manager, 404 when job
  missing, happy path; finally closes db_manager
- GET /v1/audit/logs/{job_id}: 503 when no db_manager, happy path
  passes limit through; finally closes db_manager
- GET /v1/ingest/documents: 503 when no db_manager, filters passed
  to search_documents, count returned; finally closes
- GET /v1/verify/{document_id}: 503 when no db_manager, 404 when
  missing, happy path returns all 4 hashes + ISO verified_at

Issue: #1342
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import routes_status as rs
from app.routes_status import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _stub_api_key():
    """Stand-in APIKey dependency override — no real auth."""
    from shared.auth import APIKey
    return APIKey(
        key_id="k1",
        key_hash="h",
        name="test",
        created_at=datetime.now(timezone.utc),
    )


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    from shared.auth import require_api_key
    app.dependency_overrides[require_api_key] = _stub_api_key
    return app


@pytest.fixture
def client():
    return TestClient(_app())


class _FakeRedis:
    """Minimal Redis stub — pre-seed a dict of {key: bytes-or-None}."""
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, key):
        return self.data.get(key)


@pytest.fixture
def patch_redis(monkeypatch):
    """Returns a callable that installs a fake redis for the test."""
    def _install(data):
        fake = _FakeRedis(data)
        import redis
        monkeypatch.setattr(redis, "from_url", lambda _url: fake)
        return fake
    return _install


# ---------------------------------------------------------------------------
# GET /v1/ingest/status/{job_id}
# ---------------------------------------------------------------------------


class TestGetIngestionStatus:
    def test_404_when_job_missing(self, client, patch_redis):
        patch_redis({})  # nothing in redis
        r = client.get("/v1/ingest/status/nope")
        assert r.status_code == 404
        assert r.json()["detail"] == "Job not found"

    def test_running_status_no_result_fetch(self, client, patch_redis):
        # status is not 'completed' → do not populate 'result'
        patch_redis({"ingest:status:j1": b"running"})
        r = client.get("/v1/ingest/status/j1")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "running"
        assert body["result"] is None

    def test_completed_with_result(self, client, patch_redis):
        patch_redis({
            "ingest:status:j1": b"completed",
            "ingest:result:j1": json.dumps({"sections": 12}).encode(),
        })
        r = client.get("/v1/ingest/status/j1")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "completed"
        assert body["result"] == {"sections": 12}

    def test_completed_without_result_still_ok(self, client, patch_redis):
        """Completed but result key missing → no result field populated."""
        patch_redis({"ingest:status:j1": b"completed"})
        r = client.get("/v1/ingest/status/j1")
        assert r.status_code == 200
        assert r.json()["result"] is None


# ---------------------------------------------------------------------------
# GET /v1/ingest/documents/{document_id}/analysis
# ---------------------------------------------------------------------------


class TestGetDocumentAnalysis:
    def test_404_when_document_missing(self, client, patch_redis):
        patch_redis({})
        r = client.get("/v1/ingest/documents/d1/analysis")
        assert r.status_code == 404
        assert r.json()["detail"] == "Document not found"

    def test_analysis_with_result_fills_obligations_count(self, client, patch_redis):
        patch_redis({
            "ingest:status:d1": b"completed",
            "ingest:result:d1": json.dumps({"sections": 42}).encode(),
        })
        r = client.get("/v1/ingest/documents/d1/analysis")
        assert r.status_code == 200
        body = r.json()
        assert body["document_id"] == "d1"
        assert body["status"] == "completed"
        assert body["obligations_count"] == 42
        assert body["risk_score"] == 0
        assert body["missing_dates_count"] == 0
        assert body["critical_risks"] == []

    def test_analysis_without_result_defaults_to_zero(self, client, patch_redis):
        """When no result blob exists, obligations_count defaults to 0."""
        patch_redis({"ingest:status:d1": b"processing"})
        r = client.get("/v1/ingest/documents/d1/analysis")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "processing"
        assert body["obligations_count"] == 0


# ---------------------------------------------------------------------------
# GET /v1/audit/jobs/{job_id}
# ---------------------------------------------------------------------------


class TestGetJobStatus:
    def test_503_when_no_db_manager(self, client, monkeypatch):
        monkeypatch.setattr(rs, "get_db_manager", lambda: None)
        r = client.get("/v1/audit/jobs/j1")
        assert r.status_code == 503
        assert "not available" in r.json()["detail"]

    def test_404_when_job_missing(self, client, monkeypatch):
        db = MagicMock()
        db.get_job.return_value = None
        monkeypatch.setattr(rs, "get_db_manager", lambda: db)

        r = client.get("/v1/audit/jobs/j1")
        assert r.status_code == 404
        assert r.json()["detail"] == "Job not found"
        # finally: db.close() still called on 404
        assert db.close.called

    def test_happy_path_returns_job_dict(self, client, monkeypatch):
        db = MagicMock()
        db.get_job.return_value = {"job_id": "j1", "status": "completed"}
        monkeypatch.setattr(rs, "get_db_manager", lambda: db)

        r = client.get("/v1/audit/jobs/j1")
        assert r.status_code == 200
        # JobStatusResponse is an empty pydantic model — arbitrary fields
        # are accepted but not echoed back by the response_model filter.
        # What we care about is that the handler ran without error and
        # that the db was closed.
        assert db.close.called


# ---------------------------------------------------------------------------
# GET /v1/audit/logs/{job_id}
# ---------------------------------------------------------------------------


class TestGetJobLogs:
    def test_503_when_no_db_manager(self, client, monkeypatch):
        monkeypatch.setattr(rs, "get_db_manager", lambda: None)
        r = client.get("/v1/audit/logs/j1")
        assert r.status_code == 503

    def test_happy_path_returns_entries_and_closes(self, client, monkeypatch):
        db = MagicMock()
        db.get_audit_log.return_value = [
            {"ts": "2026-01-01T00:00:00Z", "event": "ingest_start"},
            {"ts": "2026-01-01T00:01:00Z", "event": "ingest_done"},
        ]
        monkeypatch.setattr(rs, "get_db_manager", lambda: db)

        r = client.get("/v1/audit/logs/j1?limit=50")
        assert r.status_code == 200
        body = r.json()
        assert body["job_id"] == "j1"
        assert len(body["entries"]) == 2
        # db_manager.get_audit_log called with the limit we passed
        db.get_audit_log.assert_called_once_with("j1", limit=50)
        assert db.close.called

    def test_default_limit_is_100(self, client, monkeypatch):
        db = MagicMock()
        db.get_audit_log.return_value = []
        monkeypatch.setattr(rs, "get_db_manager", lambda: db)

        client.get("/v1/audit/logs/j1")
        db.get_audit_log.assert_called_once_with("j1", limit=100)


# ---------------------------------------------------------------------------
# GET /v1/ingest/documents
# ---------------------------------------------------------------------------


class TestListDocuments:
    def test_503_when_no_db_manager(self, client, monkeypatch):
        monkeypatch.setattr(rs, "get_db_manager", lambda: None)
        r = client.get("/v1/ingest/documents")
        assert r.status_code == 503

    def test_happy_path_with_filters(self, client, monkeypatch):
        db = MagicMock()
        db.search_documents.return_value = [
            {"id": "d1", "vertical": "food"}, {"id": "d2", "vertical": "food"},
        ]
        monkeypatch.setattr(rs, "get_db_manager", lambda: db)

        r = client.get(
            "/v1/ingest/documents?vertical=food&source_type=fda&limit=10&offset=5",
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        assert len(body["documents"]) == 2
        db.search_documents.assert_called_once_with("food", "fda", 10, 5)
        assert db.close.called

    def test_default_paging(self, client, monkeypatch):
        db = MagicMock()
        db.search_documents.return_value = []
        monkeypatch.setattr(rs, "get_db_manager", lambda: db)

        client.get("/v1/ingest/documents")
        db.search_documents.assert_called_once_with(None, None, 100, 0)


# ---------------------------------------------------------------------------
# GET /v1/verify/{document_id}
# ---------------------------------------------------------------------------


class TestVerifyDocument:
    def test_503_when_no_db_manager(self, client, monkeypatch):
        monkeypatch.setattr(rs, "get_db_manager", lambda: None)
        r = client.get("/v1/verify/d1")
        assert r.status_code == 503

    def test_404_when_document_missing(self, client, monkeypatch):
        db = MagicMock()
        db.get_document.return_value = None
        monkeypatch.setattr(rs, "get_db_manager", lambda: db)

        r = client.get("/v1/verify/d1")
        assert r.status_code == 404
        assert r.json()["detail"] == "Document not found"
        # finally: db.close() still called on 404
        assert db.close.called

    def test_happy_path_returns_all_hashes(self, client, monkeypatch):
        db = MagicMock()
        db.get_document.return_value = {
            "content_sha256": "c256",
            "content_sha512": "c512",
            "text_sha256": "t256",
            "text_sha512": "t512",
        }
        monkeypatch.setattr(rs, "get_db_manager", lambda: db)

        r = client.get("/v1/verify/d1")
        assert r.status_code == 200
        body = r.json()
        assert body["document_id"] == "d1"
        assert body["status"] == "verified"
        assert body["hashes"] == {
            "content_sha256": "c256",
            "content_sha512": "c512",
            "text_sha256": "t256",
            "text_sha512": "t512",
        }
        # verified_at is a valid ISO-8601 timestamp
        assert "T" in body["verified_at"]
        assert db.close.called


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_routes_registered(self):
        paths = {r.path for r in router.routes}
        expected = {
            "/v1/ingest/status/{job_id}",
            "/v1/ingest/documents/{document_id}/analysis",
            "/v1/audit/jobs/{job_id}",
            "/v1/audit/logs/{job_id}",
            "/v1/ingest/documents",
            "/v1/verify/{document_id}",
        }
        assert expected.issubset(paths)
