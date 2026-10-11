"""Regression tests: direct/file ingest must survive synthetic source URLs.

``ingest_direct`` stores ``manual://direct`` and ``ingest_file`` stores an
upload provenance ref as ``NormalizedDocument.source_url``. The SSRF guard
added to that model only accepts resolvable public http(s) URLs, so both
endpoints raised an uncaught pydantic ``ValidationError`` inside
``_process_and_emit`` and every real request to ``POST /v1/ingest`` or
``POST /v1/ingest/file`` answered 500.

The fix keeps the SSRF screen for http(s) values (fail-closed, DNS failure
still rejects) and accepts non-http provenance refs as opaque strings,
since no consumer ever fetches a stored ``source_url``. These tests pin:

* ``_process_and_emit`` succeeds for ``manual://direct`` and file-upload refs
* ``NormalizedDocument`` still rejects private http(s) hosts
* ``ingest_direct`` preserves downstream HTTP statuses instead of 500
* ``ingest_direct`` rejects empty text with 400 (parity with ``ingest_file``)
* tenantless keys still get 403 on both endpoints
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import routes_ingest  # noqa: E402
from app.models import NormalizedDocument, NormalizedEvent  # noqa: E402
from fastapi import HTTPException  # noqa: E402


def _api_key(tenant_id="tenant-x"):
    key = MagicMock()
    key.tenant_id = tenant_id
    key.allowed_jurisdictions = ["US"]
    return key


def _doc(**kwargs):
    base = {
        "document_id": "doc-1",
        "source_system": "generic",
        "retrieved_at": datetime(2026, 4, 19, tzinfo=timezone.utc),
        "text": "regulation text",
        "content_sha256": "a" * 64,
    }
    base.update(kwargs)
    return NormalizedDocument(**base)


class _MemoryUpload:
    """Minimal UploadFile stub for handler-level tests."""

    def __init__(self, payload: bytes, filename="report.txt", content_type="text/plain"):
        self._payload = payload
        self._pos = 0
        self.filename = filename
        self.content_type = content_type

    async def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._payload):
            return b""
        chunk = self._payload[self._pos : self._pos + size if size > 0 else len(self._payload)]
        self._pos += len(chunk)
        return chunk


@pytest.fixture()
def _no_side_effects(monkeypatch):
    """Run the real pipeline with storage and messaging stubbed out."""
    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)
    monkeypatch.setattr(routes_ingest, "put_bytes", lambda bucket, key, data, *a: f"s3://{bucket}/{key}")
    monkeypatch.setattr(routes_ingest, "put_json", lambda bucket, key, data, *a: f"s3://{bucket}/{key}")
    monkeypatch.setattr(routes_ingest, "send", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Model level: synthetic refs accepted, http(s) SSRF screen unchanged
# ---------------------------------------------------------------------------


class TestSyntheticSourceUrls:
    def test_manual_scheme_accepted(self):
        assert _doc(source_url="manual://direct").source_url == "manual://direct"

    def test_upload_scheme_accepted(self):
        doc = _doc(source_url="upload://file/report.txt")
        assert doc.source_url == "upload://file/report.txt"

    def test_private_http_literal_still_rejected(self):
        with pytest.raises(ValidationError, match="private or reserved"):
            _doc(source_url="https://10.1.2.3/x")

    def test_metadata_host_still_rejected(self):
        with pytest.raises(ValidationError, match="metadata endpoint"):
            _doc(source_url="https://169.254.169.254/x")

    def test_event_accepts_synthetic_ref(self):
        event = NormalizedEvent(
            event_id="e",
            document_id="d",
            document_hash="h",
            source_system="s",
            source_url="manual://direct",
            raw_s3_path="r",
            normalized_s3_path="n",
            timestamp=datetime.now(timezone.utc),
            content_sha256="a" * 64,
        )
        assert event.source_url == "manual://direct"


# ---------------------------------------------------------------------------
# Pipeline level: the real _process_and_emit must not raise for these origins
# ---------------------------------------------------------------------------


class TestProcessAndEmit:
    def test_direct_origin_succeeds(self, _no_side_effects):
        with (
            patch.object(routes_ingest, "put_bytes", return_value="s3://raw/x"),
            patch.object(routes_ingest, "put_json", return_value="s3://proc/x"),
            patch.object(routes_ingest, "send", return_value=None),
        ):
            event = routes_ingest._process_and_emit(
                raw_bytes=b"hello regulation text",
                url_str="manual://direct",
                source_system="generic",
                tenant_id="t1",
                content_type="text/plain",
            )
        assert not event.is_duplicate
        assert event.tenant_id == "t1"

    def test_file_upload_origin_succeeds(self, _no_side_effects):
        with (
            patch.object(routes_ingest, "put_bytes", return_value="s3://raw/x"),
            patch.object(routes_ingest, "put_json", return_value="s3://proc/x"),
            patch.object(routes_ingest, "send", return_value=None),
        ):
            event = routes_ingest._process_and_emit(
                raw_bytes=b"hello regulation text",
                url_str="upload://file/report.txt",
                source_system="generic",
                tenant_id="t1",
                content_type="text/plain",
            )
        assert not event.is_duplicate


# ---------------------------------------------------------------------------
# Handler level
# ---------------------------------------------------------------------------


class TestIngestDirect:
    def test_success_returns_event(self, _no_side_effects):
        payload = routes_ingest.DirectIngestRequest(text="some regulation text", source_system="generic")
        event = asyncio.run(routes_ingest.ingest_direct(payload=payload, api_key=_api_key()))
        assert event.tenant_id == "tenant-x"
        assert not event.is_duplicate

    def test_downstream_http_status_preserved(self, monkeypatch):
        """A 413 from the pipeline must reach the caller, not become a 500."""
        monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)

        def _boom(**kwargs):
            raise HTTPException(status_code=413, detail="Payload exceeds size limits")

        monkeypatch.setattr(routes_ingest, "_process_and_emit", _boom)
        payload = routes_ingest.DirectIngestRequest(text="x" * 10, source_system="generic")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(routes_ingest.ingest_direct(payload=payload, api_key=_api_key()))
        assert exc.value.status_code == 413

    def test_empty_text_rejected(self, _no_side_effects):
        payload = routes_ingest.DirectIngestRequest(text="", source_system="generic")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(routes_ingest.ingest_direct(payload=payload, api_key=_api_key()))
        assert exc.value.status_code == 400

    def test_missing_text_rejected(self, _no_side_effects):
        payload = routes_ingest.DirectIngestRequest(text=None, source_system="generic")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(routes_ingest.ingest_direct(payload=payload, api_key=_api_key()))
        assert exc.value.status_code == 400

    def test_tenantless_key_rejected(self, _no_side_effects):
        payload = routes_ingest.DirectIngestRequest(text="some text", source_system="generic")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(routes_ingest.ingest_direct(payload=payload, api_key=_api_key(tenant_id=None)))
        assert exc.value.status_code == 403


class TestIngestFile:
    def test_success_returns_event(self, _no_side_effects):
        upload = _MemoryUpload(b"hello regulation text", filename="report.txt")
        event = asyncio.run(
            routes_ingest.ingest_file(file=upload, source_system="generic", vertical=None, api_key=_api_key())
        )
        assert event.tenant_id == "tenant-x"
        assert not event.is_duplicate

    def test_empty_file_rejected(self, _no_side_effects):
        upload = _MemoryUpload(b"", filename="empty.txt")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                routes_ingest.ingest_file(file=upload, source_system="generic", vertical=None, api_key=_api_key())
            )
        assert exc.value.status_code == 400

    def test_tenantless_key_rejected(self, _no_side_effects):
        upload = _MemoryUpload(b"data", filename="report.txt")
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                routes_ingest.ingest_file(
                    file=upload, source_system="generic", vertical=None, api_key=_api_key(tenant_id=None)
                )
            )
        assert exc.value.status_code == 403
