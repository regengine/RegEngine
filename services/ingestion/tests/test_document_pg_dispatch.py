"""A successful PostgreSQL-backed document import must leave durable NLP work."""

from __future__ import annotations

import hashlib
import io
import json
import traceback
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app import document_dispatch, kafka_utils, routes_ingest, s3_utils
from app.models import NormalizedEvent
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from regengine_ingestion.models import JobStatus
from shared import database
from shared.tenant_context import get_rls_tenant_id

TENANT_ID = "11111111-1111-1111-1111-111111111111"
SOURCE_URL = "https://8.8.8.8/document.json"
CONTENT = b'{"text":"Actual normalized regulatory text.","tenant_id":"untrusted-tenant"}'


class _Documents:
    def __init__(self):
        self.rows = {}
        self.statuses = []

    def connect(self):
        pass

    def set_tenant_context(self, tenant_id):
        self.tenant_id = tenant_id

    def insert_job(self, job):
        pass

    def insert_audit_entry(self, entry):
        pass

    def update_job(self, job):
        self.statuses.append(job.status)

    def close(self):
        pass

    def get_document_by_hash(self, content_hash, *, tenant_id):
        return self.rows.get((tenant_id, content_hash))

    def insert_document(self, document):
        row = {
            "id": document.id,
            "tenant_id": document.tenant_id,
            "content_sha256": document.hash.content_sha256,
            "storage_key": document.storage_key,
            "source_url": document.source_metadata.source_url,
        }
        return self.rows.setdefault((document.tenant_id, document.hash.content_sha256), row)


class _QueueSession:
    """Capture SQL writes and expose only committed tasks to the assertion."""

    def __init__(self, committed, control):
        self.committed = committed
        self.pending = []
        self.control = control

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        params = params or {}
        assert get_rls_tenant_id() == params["tenant_id"]
        if sql.startswith("INSERT INTO fsma.task_queue"):
            if self.control.failure == "insert":
                raise RuntimeError("private queue diagnostic")
            existing = next(
                (
                    row
                    for row in self.committed + self.pending
                    if row["tenant_id"] == params["tenant_id"] and row["idempotency_key"] == params["idempotency_key"]
                ),
                None,
            )
            if existing:
                return SimpleNamespace(fetchone=lambda: None)
            row = dict(params, id=len(self.committed) + len(self.pending) + 1, status="pending")
            row["payload"] = json.loads(row["payload"])
            self.pending.append(row)
            return SimpleNamespace(fetchone=lambda: (row["id"],), scalar_one=lambda: row["id"])
        if sql.startswith("SELECT id FROM fsma.task_queue"):
            row = next(
                row
                for row in self.committed + self.pending
                if row["tenant_id"] == params["tenant_id"] and row["idempotency_key"] == params["idempotency_key"]
            )
            return SimpleNamespace(fetchone=lambda: (row["id"],))
        if sql.startswith("SELECT task_type, payload, tenant_id, status, idempotency_key"):
            if self.control.failure == "read":
                raise RuntimeError("private queue diagnostic")
            row = next(
                (
                    row
                    for row in self.committed + self.pending
                    if row["id"] == params["task_id"] and row["tenant_id"] == params["tenant_id"]
                ),
                None,
            )
            return SimpleNamespace(mappings=lambda: SimpleNamespace(one_or_none=lambda: row))
        raise AssertionError(f"Unexpected task SQL: {sql}")

    def commit(self):
        if self.control.failure == "commit":
            raise RuntimeError("private queue diagnostic")
        self.committed.extend(self.pending)
        self.pending.clear()
        self.control.commits += 1

    def rollback(self):
        self.pending.clear()
        self.control.rollbacks += 1
        if self.control.rollback_failure:
            raise RuntimeError("private rollback diagnostic")

    def close(self):
        self.pending.clear()
        self.control.closes += 1
        if self.control.failure == "close":
            raise RuntimeError("private queue diagnostic")


@pytest.fixture
def dispatch_store(monkeypatch):
    objects, committed, reads = {}, [], []
    control = SimpleNamespace(failure=None, commits=0, rollbacks=0, closes=0, rollback_failure=False)

    def session():
        if control.failure == "session":
            raise RuntimeError("private queue diagnostic")
        return _QueueSession(committed, control)

    def put_object(*, Bucket, Key, Body, **kwargs):
        objects[f"s3://{Bucket}/{Key}"] = Body

    def get_object(*, Bucket, Key):
        reads.append(f"s3://{Bucket}/{Key}")
        return {"Body": io.BytesIO(objects[f"s3://{Bucket}/{Key}"])}

    storage = SimpleNamespace(put_object=put_object, get_object=get_object)
    monkeypatch.setenv("EVENT_BACKBONE", "pg")
    monkeypatch.setattr(s3_utils, "_client", lambda: storage)
    monkeypatch.setattr(routes_ingest, "SessionLocal", session)
    monkeypatch.setattr(database, "SessionLocal", session)
    monkeypatch.setattr(document_dispatch, "SessionLocal", session)

    def forbid_kafka():
        pytest.fail("PostgreSQL document ingestion must not contact Kafka")

    monkeypatch.setattr(kafka_utils, "get_producer", forbid_kafka)
    return SimpleNamespace(db=_Documents(), objects=objects, committed=committed, control=control, reads=reads)


def _ingest(store):
    return routes_ingest._process_and_emit(
        raw_bytes=CONTENT,
        url_str=SOURCE_URL,
        source_system="synthetic",
        tenant_id=TENANT_ID,
        content_type="application/json",
        db_manager=store.db,
    )


@pytest.fixture
def dispatch_client(dispatch_store, monkeypatch):
    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: dispatch_store.db)
    monkeypatch.setattr(routes_ingest, "consume_tenant_rate_limit", lambda **kwargs: (True, 999))
    monkeypatch.setattr(routes_ingest, "_fetch", AsyncMock(return_value=(CONTENT, "application/json")))
    monkeypatch.setattr(routes_ingest, "_resolve_and_validate", lambda host: {"8.8.8.8"})
    app = FastAPI()
    app.include_router(routes_ingest.router)
    app.dependency_overrides[routes_ingest.require_api_key] = lambda: SimpleNamespace(
        tenant_id=TENANT_ID, allowed_jurisdictions=["US"]
    )
    with TestClient(app) as client:
        yield client


def _request(client, route):
    if route == "file":
        return client.post("/v1/ingest/file", files={"file": ("document.json", CONTENT, "application/json")})
    if route == "direct":
        return client.post("/v1/ingest", json={"text": CONTENT.decode(), "source_system": "synthetic"})
    return client.post("/v1/ingest/url", json={"url": SOURCE_URL, "source_system": "synthetic"})


@pytest.mark.parametrize("route", ["file", "direct", "url"])
@pytest.mark.parametrize("failure", ["session", "insert", "read", "commit"])
def test_queue_failure_prevents_http_success_and_job_completion(dispatch_client, dispatch_store, route, failure):
    dispatch_store.control.failure = failure

    response = _request(dispatch_client, route)

    assert response.status_code == 503
    assert response.json() == {"detail": "Document processing unavailable"}
    assert dispatch_store.committed == []
    assert len(dispatch_store.db.rows) == 1  # Retained for a safe retry after queue recovery.
    assert dispatch_store.db.statuses == [JobStatus.FAILED]


@pytest.mark.parametrize("route", ["file", "direct", "url"])
def test_http_success_has_committed_work_and_completes_job(dispatch_client, dispatch_store, route):
    response = _request(dispatch_client, route)

    assert response.status_code == 200
    assert len(dispatch_store.committed) == 1
    task = dispatch_store.committed[0]
    assert task["tenant_id"] == TENANT_ID
    assert task["payload"]["document_id"] == response.json()["document_id"]
    assert task["payload"]["source_url"] == response.json()["source_url"]
    assert dispatch_store.db.statuses == [JobStatus.COMPLETED]


def test_pg_import_success_requires_committed_nlp_task(dispatch_store):
    event = _ingest(dispatch_store)

    assert len(dispatch_store.committed) == 1, "Import returned success without a committed NLP task"
    task = dispatch_store.committed[0]
    assert task["task_type"] == "nlp_extraction"
    assert task["tenant_id"] == TENANT_ID
    assert task["payload"]["document_id"] == event.document_id
    assert task["payload"]["text"] == "Actual normalized regulatory text."
    assert task["payload"]["source_url"] == SOURCE_URL
    assert task["payload"]["document_hash"] == hashlib.sha256(CONTENT).hexdigest()
    assert task["payload"].get("tenant_id", TENANT_ID) == TENANT_ID


@pytest.mark.parametrize("concurrent", [False, True])
def test_pg_duplicate_without_task_dispatches_stored_normalized_content(dispatch_store, monkeypatch, concurrent):
    content_hash = hashlib.sha256(CONTENT).hexdigest()
    stored_uri = "s3://legacy/normalized/stored/current.json"
    document_id = "33333333-3333-3333-3333-333333333333"
    dispatch_store.db.rows[(TENANT_ID, content_hash)] = {
        "id": document_id,
        "tenant_id": TENANT_ID,
        "content_sha256": content_hash,
        "storage_key": stored_uri,
        "source_url": "https://8.8.8.8/original.json",
    }
    dispatch_store.objects[stored_uri] = json.dumps(
        {
            "document_id": "legacy-normalized-identifier",
            "text": "Stored canonical normalized text, not retry input.",
            "content_sha256": content_hash,
            "source_url": "https://8.8.8.8/original.json",
        }
    ).encode()
    if concurrent:
        monkeypatch.setattr(dispatch_store.db, "get_document_by_hash", lambda *args, **kwargs: None)

    event = _ingest(dispatch_store)

    assert event.is_duplicate
    assert len(dispatch_store.committed) == 1, "Duplicate success left the missing NLP task unrepaired"
    payload = dispatch_store.committed[0]["payload"]
    assert payload["document_id"] == document_id
    assert payload["text"] == "Stored canonical normalized text, not retry input."
    assert payload["source_url"] == "https://8.8.8.8/original.json"
    assert payload["document_hash"] == content_hash
    assert dispatch_store.reads == [stored_uri]
    if not concurrent:
        assert list(dispatch_store.objects) == [stored_uri]


def _event_and_normalized():
    content_hash = hashlib.sha256(CONTENT).hexdigest()
    event = NormalizedEvent(
        event_id="attempt-one",
        document_id="33333333-3333-3333-3333-333333333333",
        document_hash=content_hash,
        tenant_id=TENANT_ID,
        source_system="synthetic",
        source_url=SOURCE_URL,
        raw_s3_path="s3://synthetic/raw/document.json",
        normalized_s3_path="s3://synthetic/normalized/document.json",
        timestamp=datetime.now(timezone.utc),
        content_sha256=content_hash,
    )
    normalized = {
        "content_sha256": content_hash,
        "text": "Canonical normalized text.",
        "source_url": SOURCE_URL,
    }
    return event, normalized


@pytest.mark.parametrize("status", ["pending", "processing", "completed"])
def test_matching_live_or_completed_task_is_idempotent(dispatch_store, status):
    event, normalized = _event_and_normalized()
    document_dispatch.dispatch_document(event, normalized)
    dispatch_store.committed[0]["status"] = status

    document_dispatch.dispatch_document(event.model_copy(update={"event_id": "attempt-two"}), normalized)

    assert len(dispatch_store.committed) == 1
    assert dispatch_store.committed[0]["status"] == status
    assert dispatch_store.control.commits == 2
    assert get_rls_tenant_id() is None
    assert len(dispatch_store.committed[0]["idempotency_key"]) < 128


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "dead"),
        ("status", "failed"),
        ("status", "unknown"),
        ("task_type", "review_item"),
        ("payload", {"text": "not this document"}),
    ],
)
def test_inconsistent_or_dead_existing_task_never_counts_as_dispatched(dispatch_store, field, value):
    event, normalized = _event_and_normalized()
    document_dispatch.dispatch_document(event, normalized)
    dispatch_store.committed[0][field] = value

    with pytest.raises(HTTPException) as error:
        document_dispatch.dispatch_document(event, normalized)

    assert error.value.status_code == 503
    assert len(dispatch_store.committed) == 1
    assert dispatch_store.committed[0][field] == value
    assert dispatch_store.control.commits == 1
    assert dispatch_store.control.rollbacks == 1


@pytest.mark.parametrize("failure", ["session", "insert", "read", "commit"])
def test_queue_failure_never_leaves_a_committed_task(dispatch_store, failure, caplog):
    event, normalized = _event_and_normalized()
    dispatch_store.control.failure = failure

    with pytest.raises(HTTPException) as error:
        document_dispatch.dispatch_document(event, normalized)

    assert error.value.status_code == 503
    assert "private queue diagnostic" not in error.value.detail
    assert "private queue diagnostic" not in caplog.text
    assert "private queue diagnostic" not in "".join(traceback.format_exception(error.value))
    assert dispatch_store.committed == []
    assert dispatch_store.control.commits == 0
    assert get_rls_tenant_id() is None


def test_rollback_failure_preserves_safe_error_and_closes_session(dispatch_store, monkeypatch):
    event, normalized = _event_and_normalized()
    dispatch_store.control.failure = "commit"
    dispatch_store.control.rollback_failure = True
    logger = Mock()
    monkeypatch.setattr(document_dispatch, "logger", logger)

    with pytest.raises(HTTPException) as error:
        document_dispatch.dispatch_document(event, normalized)

    assert error.value.status_code == 503
    assert dispatch_store.committed == []
    assert dispatch_store.control.closes == 1
    assert [call.kwargs for call in logger.error.call_args_list] == [
        {"error_type": "RuntimeError"},
        {"error_type": "RuntimeError"},
    ]


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", ""),
        ("text", "  "),
        ("text", None),
        ("text", 123),
        ("content_sha256", "wrong"),
        ("source_url", "manual://untrusted"),
        ("source_url", "https://8.8.8.8/other"),
    ],
)
def test_invalid_normalized_content_never_enqueues(dispatch_store, field, value):
    event, normalized = _event_and_normalized()
    normalized[field] = value

    with pytest.raises(HTTPException) as error:
        document_dispatch.dispatch_document(event, normalized)

    assert error.value.status_code == 503
    assert dispatch_store.committed == []
    assert dispatch_store.control.commits == 0


def test_different_tenants_never_share_an_nlp_task(dispatch_store):
    event, normalized = _event_and_normalized()
    document_dispatch.dispatch_document(event, normalized)
    second_tenant = "22222222-2222-2222-2222-222222222222"
    document_dispatch.dispatch_document(event.model_copy(update={"tenant_id": second_tenant}), normalized)

    assert len(dispatch_store.committed) == 2
    assert {row["tenant_id"] for row in dispatch_store.committed} == {TENANT_ID, second_tenant}
    assert all(row["payload"]["tenant_id"] == row["tenant_id"] for row in dispatch_store.committed)


def test_committed_dispatch_survives_close_failure(dispatch_store):
    event, normalized = _event_and_normalized()
    dispatch_store.control.failure = "close"

    document_dispatch.dispatch_document(event, normalized)

    assert len(dispatch_store.committed) == 1
    assert dispatch_store.control.commits == 1


def test_kafka_mode_does_not_create_pg_work(dispatch_store, monkeypatch):
    monkeypatch.setenv("EVENT_BACKBONE", "kafka")
    event, normalized = _event_and_normalized()

    document_dispatch.dispatch_document(event, normalized)

    assert dispatch_store.committed == []
    assert dispatch_store.control.commits == 0


@pytest.mark.parametrize("tenant_id", [None, "", "not-a-tenant"])
def test_missing_or_invalid_authoritative_tenant_never_enqueues(dispatch_store, tenant_id):
    event, normalized = _event_and_normalized()

    with pytest.raises(HTTPException) as error:
        document_dispatch.dispatch_document(event.model_copy(update={"tenant_id": tenant_id}), normalized)

    assert error.value.status_code == 503
    assert dispatch_store.committed == []
    assert dispatch_store.control.closes == 0


@pytest.mark.parametrize(
    "uri",
    [
        "https://169.254.169.254/document.json",
        "s3://bucket/../document.json",
        "s3://user:password@bucket/document.json",  # pragma: allowlist secret - synthetic rejected URI
        "s3://bucket/document.json?other=object",
        "s3://bucket/document.json#other",
        "s3://bucket//document.json",
    ],
)
def test_invalid_stored_pointer_never_fetches_or_dispatches(dispatch_store, uri):
    event, _ = _event_and_normalized()

    with pytest.raises(HTTPException) as error:
        document_dispatch.dispatch_document(event.model_copy(update={"normalized_s3_path": uri}))

    assert error.value.status_code == 503
    assert dispatch_store.objects == {}
    assert dispatch_store.reads == []
    assert dispatch_store.committed == []


@pytest.mark.parametrize("content", [b"not JSON", b"null", b"[]", b"{}", b'{"text":"no source or hash"}'])
def test_unusable_persisted_object_never_dispatches(dispatch_store, content):
    event, _ = _event_and_normalized()
    dispatch_store.objects[event.normalized_s3_path] = content

    with pytest.raises(HTTPException) as error:
        document_dispatch.dispatch_document(event)

    assert error.value.status_code == 503
    assert dispatch_store.committed == []


def test_missing_persisted_object_never_dispatches(dispatch_store):
    event, _ = _event_and_normalized()

    with pytest.raises(HTTPException) as error:
        document_dispatch.dispatch_document(event)

    assert error.value.status_code == 503
    assert dispatch_store.committed == []
