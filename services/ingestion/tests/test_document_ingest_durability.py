"""Document ingestion must not report success without database persistence."""

from __future__ import annotations

import socket
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import psycopg
import pytest
from app import routes_ingest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from regengine_ingestion.models import JobStatus

TENANT_ID = "10000000-0000-0000-0000-000000000001"
SOURCE_URL = "https://example.com/document.txt"
CONTENT = b"Synthetic regulatory document."


class _Database:
    def __init__(self, failure=None, *, fail_status_update=False):
        self.failure = failure
        self.fail_status_update = fail_status_update
        self.documents = []
        self.jobs = []
        self.statuses = []
        self.tenant_id = None
        self.closed = False
        self.fail_close = False

    def _check(self, operation):
        if self.failure == operation:
            raise psycopg.OperationalError("synthetic private database diagnostic")

    def connect(self):
        self._check("connect")

    def set_tenant_context(self, tenant_id):
        self._check("tenant")
        self.tenant_id = tenant_id

    def insert_job(self, job):
        self._check("job")
        self.jobs.append(replace(job))

    def get_document_by_hash(self, content_hash, *, tenant_id):
        assert tenant_id == self.tenant_id
        self._check("lookup")
        return None

    def insert_document(self, document):
        if self.failure == "document_runtime":
            raise RuntimeError("synthetic private database diagnostic")
        self._check("document")
        self.documents.append(document)

    def insert_audit_entry(self, entry):
        pass

    def update_job(self, job):
        if self.fail_status_update:
            raise RuntimeError("synthetic secondary status failure")
        self.statuses.append(job.status)

    def close(self):
        self.closed = True
        if self.fail_close:
            raise RuntimeError("synthetic private cleanup diagnostic")


@pytest.fixture
def harness(monkeypatch):
    database = _Database()
    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: database)
    monkeypatch.setattr(routes_ingest, "consume_tenant_rate_limit", lambda **kwargs: (True, 999))
    # All DNS and I/O is synthetic, including upload.internal's legacy source URL.
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    writes = Mock(return_value="s3://synthetic/raw")
    normalized_writes = Mock(return_value="s3://synthetic/normalized")

    def emit_after_persistence(*args, **kwargs):
        assert database.documents, "Document must be persisted before publication"

    sends = Mock(side_effect=emit_after_persistence)
    fetch = AsyncMock(return_value=(CONTENT, "text/plain"))
    monkeypatch.setattr(routes_ingest, "put_bytes", writes)
    monkeypatch.setattr(routes_ingest, "put_json", normalized_writes)
    monkeypatch.setattr(routes_ingest, "send", sends)
    monkeypatch.setattr(routes_ingest, "_fetch", fetch)
    app = FastAPI()
    app.include_router(routes_ingest.router)
    key = SimpleNamespace(tenant_id=TENANT_ID, allowed_jurisdictions=["US"])
    app.dependency_overrides[routes_ingest.require_api_key] = lambda: key
    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, db=database, writes=writes, normalized_writes=normalized_writes, sends=sends, fetch=fetch
        )


def _request(harness, route):
    if route == "file":
        return harness.client.post("/v1/ingest/file", files={"file": ("document.txt", CONTENT, "text/plain")})
    if route == "direct":
        return harness.client.post(
            "/v1/ingest", json={"text": CONTENT.decode(), "source_url": SOURCE_URL, "source_system": "test"}
        )
    return harness.client.post("/v1/ingest/url", json={"url": SOURCE_URL, "source_system": "test"})


@pytest.mark.parametrize("route", ["file", "direct", "url"])
def test_database_unavailable_rejects_before_processing(harness, monkeypatch, route):
    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)

    response = _request(harness, route)

    assert response.status_code == 503
    assert "event_id" not in response.json()
    harness.writes.assert_not_called()
    harness.normalized_writes.assert_not_called()
    harness.sends.assert_not_called()
    harness.fetch.assert_not_called()


@pytest.mark.parametrize("route", ["file", "direct", "url"])
@pytest.mark.parametrize("failure", ["connect", "tenant", "job"])
def test_database_initialization_failure_rejects_before_processing(harness, route, failure):
    harness.db.failure = failure

    response = _request(harness, route)

    assert response.status_code in (500, 503)
    assert "private database diagnostic" not in response.text
    assert harness.db.jobs == []
    assert harness.db.documents == []
    assert JobStatus.COMPLETED not in harness.db.statuses
    assert harness.db.closed
    harness.writes.assert_not_called()
    harness.sends.assert_not_called()
    harness.fetch.assert_not_called()


@pytest.mark.parametrize("route", ["file", "direct", "url"])
@pytest.mark.parametrize("failure", ["lookup", "document", "document_runtime"])
@pytest.mark.parametrize("fail_status_update", [False, True])
def test_database_write_failure_never_emits_or_completes(harness, route, failure, fail_status_update):
    harness.db.failure = failure
    harness.db.fail_status_update = fail_status_update

    response = _request(harness, route)

    assert response.status_code in (500, 503)
    assert "event_id" not in response.json()
    assert "private database diagnostic" not in response.text
    assert "secondary status failure" not in response.text
    assert harness.db.documents == []
    assert JobStatus.COMPLETED not in harness.db.statuses
    assert harness.db.closed
    harness.sends.assert_not_called()
    if not fail_status_update:
        assert harness.db.statuses == [JobStatus.FAILED]


@pytest.mark.parametrize("route", ["file", "direct", "url"])
def test_success_requires_document_persistence_and_completed_job(harness, route):
    response = _request(harness, route)

    assert response.status_code == 200
    assert response.json()["tenant_id"] == TENANT_ID
    assert [job.status for job in harness.db.jobs] == [JobStatus.RUNNING]
    assert len(harness.db.documents) == 1
    assert harness.db.documents[0].tenant_id == TENANT_ID
    assert harness.db.statuses == [JobStatus.COMPLETED]
    assert harness.db.closed
    harness.sends.assert_called_once()


@pytest.mark.parametrize("route", ["file", "direct", "url"])
@pytest.mark.parametrize("failure,expected_status", [("document", 503), (None, 200)])
def test_database_cleanup_failure_preserves_primary_response(harness, caplog, route, failure, expected_status):
    harness.db.failure = failure
    harness.db.fail_close = True

    response = _request(harness, route)

    assert response.status_code == expected_status
    assert harness.db.closed
    assert "private cleanup diagnostic" not in response.text
    assert "private cleanup diagnostic" not in caplog.text
    assert "document_db_close_failed" in caplog.text
    if failure:
        assert response.json() == {"detail": "Document persistence unavailable"}
        assert harness.db.statuses == [JobStatus.FAILED]
        assert harness.db.documents == []
        harness.sends.assert_not_called()
    else:
        assert "event_id" in response.json()
        assert harness.db.statuses == [JobStatus.COMPLETED]
        assert len(harness.db.documents) == 1
        harness.sends.assert_called_once()


@pytest.mark.parametrize("failure", ["unavailable", "document"])
def test_shared_processor_requires_database_persistence_before_emission(harness, failure):
    harness.db.tenant_id = TENANT_ID
    harness.db.failure = failure
    database = None if failure == "unavailable" else harness.db

    with pytest.raises(HTTPException) as caught:
        routes_ingest._process_and_emit(
            raw_bytes=CONTENT,
            url_str=SOURCE_URL,
            source_system="test",
            tenant_id=TENANT_ID,
            content_type="text/plain",
            db_manager=database,
        )

    assert caught.value.status_code == 503
    harness.sends.assert_not_called()
    if database is None:
        harness.writes.assert_not_called()


@pytest.mark.parametrize("content,expected", [(b"", 400), (b"oversized", 413)])
def test_file_input_errors_survive_database_outage(harness, monkeypatch, content, expected):
    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)
    monkeypatch.setattr(routes_ingest, "MAX_PAYLOAD_BYTES", 4)

    response = harness.client.post("/v1/ingest/file", files={"file": ("document.txt", content, "text/plain")})

    assert response.status_code == expected
    harness.writes.assert_not_called()
    harness.sends.assert_not_called()
