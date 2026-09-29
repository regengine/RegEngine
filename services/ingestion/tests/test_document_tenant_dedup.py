"""Authenticated document identity and storage must be tenant-scoped."""

from __future__ import annotations

import hashlib
import socket
from types import SimpleNamespace
from uuid import UUID, uuid5

import pytest
from app import routes_ingest

TENANT_A = "11111111-1111-1111-1111-111111111111"
TENANT_B = "22222222-2222-2222-2222-222222222222"
URL_A = "https://example.com/a.txt"
URL_B = "https://example.com/b.txt"
CONTENT = b"Synthetic regulatory document."


class _TenantDocuments:
    def __init__(self):
        self.rows = {}
        self.race_winner = None

    def get_document_by_hash(self, content_hash, *, tenant_id):
        return self.rows.get((tenant_id, content_hash))

    def insert_document(self, document):
        key = (document.tenant_id, document.hash.content_sha256)
        if self.race_winner:
            self.rows[key] = self.race_winner
            return self.race_winner
        if key not in self.rows:
            if any(row["id"] == document.id for row in self.rows.values()):
                raise RuntimeError("document primary key collision")
            self.rows[key] = {
                "id": document.id,
                "tenant_id": document.tenant_id,
                "content_sha256": document.hash.content_sha256,
                "storage_key": document.storage_key,
                "source_url": document.source_metadata.source_url,
            }
        return self.rows[key]


@pytest.fixture
def store(monkeypatch):
    objects, writes, events = {}, [], []
    database = _TenantDocuments()
    # Tenant identity/object ownership is separate from the durable dispatch tests.
    monkeypatch.setattr(routes_ingest, "dispatch_document", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )

    def put(bucket, key, value):
        uri = f"s3://{bucket}/{key}"
        writes.append(uri)
        objects[uri] = value
        return uri

    monkeypatch.setattr(routes_ingest, "put_bytes", put)
    monkeypatch.setattr(routes_ingest, "put_json", put)
    monkeypatch.setattr(routes_ingest, "send", lambda topic, event, **kwargs: events.append(event))
    return SimpleNamespace(db=database, objects=objects, writes=writes, events=events)


def _ingest(store, tenant, *, content=CONTENT, url=URL_A, content_type="text/plain"):
    return routes_ingest._process_and_emit(
        raw_bytes=content,
        url_str=url,
        source_system="synthetic",
        tenant_id=tenant,
        content_type=content_type,
        db_manager=store.db,
    )


@pytest.mark.parametrize("second_url", [URL_A, URL_B])
def test_same_tenant_same_content_keeps_one_identity_and_stored_path(store, second_url):
    first = _ingest(store, TENANT_A)
    first_writes = list(store.writes)
    second = _ingest(store, TENANT_A, url=second_url)

    assert second.is_duplicate
    assert second.document_id == first.document_id
    assert second.normalized_s3_path == first.normalized_s3_path
    assert second.source_url == first.source_url
    assert store.writes == first_writes
    assert len(store.db.rows) == 1


@pytest.mark.parametrize("second_url", [URL_A, URL_B])
def test_cross_tenant_same_content_has_independent_rows_and_objects(store, second_url):
    first = _ingest(store, TENANT_A)
    first_objects = dict(store.objects)
    first_write_count = len(store.writes)
    second = _ingest(store, TENANT_B, url=second_url)

    assert first.document_id != second.document_id
    assert not second.is_duplicate
    assert len(store.db.rows) == 2
    assert set(first_objects).isdisjoint(store.writes[first_write_count:])
    assert all(store.objects[key] == value for key, value in first_objects.items())
    for event, tenant in ((first, TENANT_A), (second, TENANT_B)):
        row = store.db.rows[(tenant, hashlib.sha256(CONTENT).hexdigest())]
        normalized = store.objects[event.normalized_s3_path]
        assert row["id"] == event.document_id == normalized["document_id"]
        assert event.document_id == str(uuid5(UUID(tenant), hashlib.sha256(CONTENT).hexdigest()))


def test_full_content_hash_distinguishes_same_first_4096_characters(store):
    first = _ingest(store, TENANT_A, content=b"a" * 4096 + b"first")
    second = _ingest(store, TENANT_A, content=b"a" * 4096 + b"second")

    assert first.document_id != second.document_id
    assert first.normalized_s3_path != second.normalized_s3_path
    assert len(store.db.rows) == 2


def test_caller_document_id_cannot_override_authenticated_identity(store):
    content = b'{"document_id":"caller-selected","text":"synthetic"}'
    event = _ingest(store, TENANT_A, content=content, content_type="application/json")

    assert event.document_id == str(uuid5(UUID(TENANT_A), hashlib.sha256(content).hexdigest()))
    assert store.objects[event.normalized_s3_path]["document_id"] == event.document_id


def test_concurrent_duplicate_keeps_winner_metadata_and_pointer(store, monkeypatch):
    first = _ingest(store, TENANT_A)
    winner_payload = dict(store.objects[first.normalized_s3_path])
    winner_writes = list(store.writes)
    # Simulate the second request's lookup happening before the first commits.
    monkeypatch.setattr(store.db, "get_document_by_hash", lambda *args, **kwargs: None)

    second = _ingest(store, TENANT_A, url=URL_B)

    assert second.is_duplicate
    assert second.document_id == first.document_id
    assert second.normalized_s3_path == first.normalized_s3_path
    assert second.source_url == first.source_url
    assert store.objects[first.normalized_s3_path] == winner_payload
    assert set(winner_writes).isdisjoint(store.writes[len(winner_writes) :])
    assert len(store.db.rows) == 1


@pytest.mark.parametrize("concurrent", [False, True])
def test_legacy_existing_row_preserves_identity_and_stored_uri(store, concurrent):
    legacy = {
        "id": "33333333-3333-3333-3333-333333333333",
        "tenant_id": TENANT_A,
        "content_sha256": hashlib.sha256(CONTENT).hexdigest(),
        "storage_key": "s3://legacy/normalized/old-hash/current.json",
        "source_url": URL_B,
    }
    if concurrent:
        store.db.race_winner = legacy
    else:
        store.db.rows[(TENANT_A, legacy["content_sha256"])] = legacy

    event = _ingest(store, TENANT_A)

    assert event.document_id == legacy["id"]
    assert event.normalized_s3_path == legacy["storage_key"]
    assert str(event.source_url) == URL_B
    assert event.is_duplicate
    assert legacy["storage_key"] not in store.writes
    if not concurrent:
        assert store.writes == []
