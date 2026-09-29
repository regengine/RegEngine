"""Internal source provenance must not bypass caller URL validation."""

import socket
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from app.models import NormalizedDocument, _ServerDocumentSource
from pydantic import HttpUrl, ValidationError

from services.ingestion.tests.test_document_ingest_durability import (  # noqa: F401
    CONTENT,
    SOURCE_URL,
    TENANT_ID,
    harness,
)


@pytest.fixture
def source_harness(harness, monkeypatch):
    queries = []

    def resolve(host, *args, **kwargs):
        queries.append(host)
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        raise socket.gaierror(socket.EAI_NONAME, "Synthetic unresolved host")

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    harness.dns_queries = queries
    return harness


@pytest.mark.parametrize("route", ["file", "direct_omitted", "direct_null", "direct_empty"])
def test_server_generated_source_is_http_provenance_without_dns_or_fetch(source_harness, route):
    if route == "file":
        response = source_harness.client.post(
            "/v1/ingest/file", files={"file": ("supplier.txt", CONTENT, "text/plain")}
        )
    else:
        payload = {"text": CONTENT.decode(), "source_system": "synthetic"}
        if route == "direct_null":
            payload["source_url"] = None
        elif route == "direct_empty":
            payload["source_url"] = ""
        response = source_harness.client.post("/v1/ingest", json=payload)

    assert response.status_code == 200
    event = response.json()
    source_url = HttpUrl(event["source_url"])
    assert source_url.host == "provenance.invalid"
    document = source_harness.db.documents[0]
    assert document.source_type == ("file_upload" if route == "file" else "direct")
    assert document.source_metadata.source_url == event["source_url"]
    normalized = source_harness.normalized_writes.call_args.args[2]
    assert normalized["source_url"] == event["source_url"]
    assert source_harness.dns_queries == []
    source_harness.fetch.assert_not_called()


@pytest.mark.parametrize("duplicate", [False, True])
@pytest.mark.parametrize(
    "source_url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://127.0.0.1/document",
        "http://upload.internal/supplier.txt",
        "https://provenance.invalid/direct/123",
        "manual://direct",
        "   ",
        "https://unknown.invalid/document",
    ],
)
def test_caller_source_is_validated_before_duplicate_lookup_or_storage(source_harness, source_url, duplicate):
    existing = {
        "id": "33333333-3333-3333-3333-333333333333",
        "source_url": SOURCE_URL,
        "storage_key": "s3://existing/document.json",
    }
    lookup = Mock(return_value=existing if duplicate else None)
    source_harness.db.get_document_by_hash = lookup

    response = source_harness.client.post(
        "/v1/ingest",
        json={"text": CONTENT.decode(), "source_system": "synthetic", "source_url": source_url},
    )

    assert response.status_code == 422
    lookup.assert_not_called()
    assert source_harness.db.documents == []
    source_harness.writes.assert_not_called()
    source_harness.normalized_writes.assert_not_called()
    source_harness.sends.assert_not_called()


@pytest.mark.parametrize("route,source_type", [("direct", "direct"), ("url", "url")])
def test_external_source_keeps_public_validation_and_correct_source_type(source_harness, route, source_type):
    if route == "direct":
        response = source_harness.client.post(
            "/v1/ingest", json={"text": CONTENT.decode(), "source_url": SOURCE_URL, "source_system": "synthetic"}
        )
    else:
        response = source_harness.client.post("/v1/ingest/url", json={"url": SOURCE_URL, "source_system": "synthetic"})

    assert response.status_code == 200
    assert source_harness.db.documents[0].source_type == source_type
    assert response.json()["source_url"] == SOURCE_URL
    assert "example.com" in source_harness.dns_queries


def test_callers_cannot_forge_internal_validation_context(source_harness):
    payload = {
        "document_id": "synthetic",
        "source_url": "https://provenance.invalid/direct/123",
        "source_system": "synthetic",
        "retrieved_at": datetime.now(timezone.utc),
        "text": "synthetic",
        "content_sha256": "a" * 64,
    }
    with pytest.raises(ValidationError):
        NormalizedDocument.model_validate(
            payload,
            context={"source_url": payload["source_url"], "server_provenance": True},
        )


def test_internal_context_only_trusts_its_exact_reference(source_harness):
    payload = {
        "document_id": "synthetic",
        "source_url": "https://provenance.invalid/direct/different-job",
        "source_system": "synthetic",
        "retrieved_at": datetime.now(timezone.utc),
        "text": "synthetic",
        "content_sha256": "a" * 64,
    }
    with pytest.raises(ValidationError):
        NormalizedDocument.model_validate(
            payload,
            context=_ServerDocumentSource(HttpUrl("https://provenance.invalid/direct/original-job")),
        )


def test_caller_cannot_reuse_generated_reference_as_trusted_source(source_harness):
    first = source_harness.client.post("/v1/ingest", json={"text": CONTENT.decode(), "source_system": "synthetic"})
    assert first.status_code == 200
    lookup = Mock()
    source_harness.db.get_document_by_hash = lookup
    writes = source_harness.writes.call_count
    sends = source_harness.sends.call_count

    second = source_harness.client.post(
        "/v1/ingest",
        json={"text": CONTENT.decode(), "source_system": "synthetic", "source_url": first.json()["source_url"]},
    )

    assert second.status_code == 422
    lookup.assert_not_called()
    assert source_harness.writes.call_count == writes
    assert source_harness.sends.call_count == sends


def test_duplicate_file_still_uses_persisted_provenance(source_harness):
    first = source_harness.client.post("/v1/ingest/file", files={"file": ("first.txt", CONTENT, "text/plain")})
    assert first.status_code == 200
    document = source_harness.db.documents[0]
    source_harness.db.get_document_by_hash = Mock(
        return_value={
            "id": document.id,
            "tenant_id": TENANT_ID,
            "source_url": document.source_metadata.source_url,
            "storage_key": document.storage_key,
        }
    )
    writes = source_harness.writes.call_count

    second = source_harness.client.post("/v1/ingest/file", files={"file": ("second.txt", CONTENT, "text/plain")})

    assert second.status_code == 200
    assert second.json()["is_duplicate"]
    assert second.json()["source_url"] == first.json()["source_url"]
    assert source_harness.writes.call_count == writes
    assert source_harness.dns_queries == []
