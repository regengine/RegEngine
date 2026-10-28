"""Internal source markers for direct/file ingests.

``_process_and_emit`` (``app/routes_ingest.py``) stores source identifiers
that are never fetched over the network: ``manual://direct`` (the
direct-text default) and ``http://upload.internal/<name>`` (server-built
file marker). The shared SSRF guard rejects both (unresolvable host), which
used to fail the whole ingest with a 500 from ``NormalizedDocument`` /
``NormalizedEvent`` validation. The stored models now exempt exactly these
non-routable markers; the fetch boundary (``IngestRequest``,
``_validate_url``, ``_fetch``) stays strict.
"""

from __future__ import annotations

import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

service_dir = Path(__file__).parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

from app.models import IngestRequest, NormalizedDocument, NormalizedEvent  # noqa: E402

MANUAL_MARKER = "manual://direct"
UPLOAD_MARKER = "http://upload.internal/report.txt"


def _boom_resolver(*_a, **_kw):
    pytest.fail("DNS resolver must not be called for internal markers")


def _doc_kwargs(**overrides):
    kwargs = {
        "document_id": "doc-1",
        "source_url": MANUAL_MARKER,
        "source_system": "direct",
        "retrieved_at": datetime(2026, 4, 19, tzinfo=timezone.utc),
        "text": "regulation text",
        "content_sha256": "a" * 64,
    }
    kwargs.update(overrides)
    return kwargs


def _event_kwargs(**overrides):
    kwargs = {
        "event_id": "evt-1",
        "document_id": "doc-1",
        "document_hash": "a" * 64,
        "tenant_id": "tenant-qa",
        "source_system": "direct",
        "source_url": MANUAL_MARKER,
        "raw_s3_path": "s3://raw/x",
        "normalized_s3_path": "s3://processed/y",
        "timestamp": datetime(2026, 4, 19, tzinfo=timezone.utc),
        "content_sha256": "a" * 64,
    }
    kwargs.update(overrides)
    return kwargs


class TestStoredSourceMarkers:
    @pytest.mark.parametrize("marker", [MANUAL_MARKER, UPLOAD_MARKER])
    def test_document_accepts_markers_without_dns(self, monkeypatch: pytest.MonkeyPatch, marker: str) -> None:
        monkeypatch.setattr("app.models.socket.getaddrinfo", _boom_resolver)
        doc = NormalizedDocument(**_doc_kwargs(source_url=marker))
        assert doc.source_url == marker

    @pytest.mark.parametrize("marker", [MANUAL_MARKER, UPLOAD_MARKER])
    def test_event_accepts_markers_without_dns(self, monkeypatch: pytest.MonkeyPatch, marker: str) -> None:
        monkeypatch.setattr("app.models.socket.getaddrinfo", _boom_resolver)
        event = NormalizedEvent(**_event_kwargs(source_url=marker))
        assert event.source_url == marker

    def test_lookalike_host_still_consults_dns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # upload.internal.evil.com is NOT the allowlisted host: validation
        # must fall through to the SSRF guard. A private resolution must
        # reject (an allowlisted host would have been accepted with no DNS).
        def _fake(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.1", 0))]

        monkeypatch.setattr("app.models.socket.getaddrinfo", _fake)
        with pytest.raises(ValidationError, match="private or reserved"):
            NormalizedDocument(**_doc_kwargs(source_url="http://upload.internal.evil.com/x"))

    def test_private_http_still_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 0))]

        monkeypatch.setattr("app.models.socket.getaddrinfo", _fake)
        with pytest.raises(ValidationError, match="private or reserved"):
            NormalizedDocument(**_doc_kwargs(source_url="https://loopback.example.com/"))

    @pytest.mark.parametrize("bad", ["not a url", "ftp://example.com/x", ""])
    def test_garbage_still_rejected(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            NormalizedDocument(**_doc_kwargs(source_url=bad))

    def test_public_http_still_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 0))]

        monkeypatch.setattr("app.models.socket.getaddrinfo", _fake)
        doc = NormalizedDocument(**_doc_kwargs(source_url="https://example.com/reg/1"))
        parsed = urlparse(doc.source_url)
        assert parsed.scheme == "https"
        assert parsed.hostname == "example.com"


class TestFetchBoundaryStillStrict:
    def test_ingest_request_rejects_manual_marker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.models.socket.getaddrinfo", _boom_resolver)
        with pytest.raises(ValidationError):
            IngestRequest(url=MANUAL_MARKER, source_system="direct")

    def test_ingest_request_rejects_upload_internal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The fetch boundary has no marker allowlist: an unresolvable
        # host must fail closed with a validation error.
        def _fail(*_a, **_kw):
            raise socket.gaierror("nxdomain")

        monkeypatch.setattr("app.models.socket.getaddrinfo", _fail)
        with pytest.raises(ValidationError, match="Unable to resolve"):
            IngestRequest(url=UPLOAD_MARKER, source_system="file")

    def test_validate_url_rejects_markers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.routes_ingest as routes_ingest

        def _fail(*_a, **_kw):
            raise socket.gaierror("nxdomain")

        monkeypatch.setattr("socket.getaddrinfo", _fail)
        with pytest.raises(HTTPException) as exc:
            routes_ingest._validate_url(MANUAL_MARKER)
        assert exc.value.status_code == 400
        with pytest.raises(HTTPException) as exc:
            routes_ingest._validate_url(UPLOAD_MARKER)
        assert exc.value.status_code == 400


class TestProcessAndEmitWithMarkers:
    @pytest.mark.parametrize("marker", [MANUAL_MARKER, UPLOAD_MARKER])
    def test_emit_succeeds_for_internal_markers(self, monkeypatch: pytest.MonkeyPatch, marker: str) -> None:
        import app.routes_ingest as routes_ingest

        monkeypatch.setattr(routes_ingest, "put_bytes", lambda *a, **k: "s3://raw/x")
        monkeypatch.setattr(routes_ingest, "put_json", lambda *a, **k: "s3://processed/y")
        monkeypatch.setattr(routes_ingest, "send", lambda *a, **k: None)

        event = routes_ingest._process_and_emit(
            raw_bytes=b"regulation text for marker ingest",
            url_str=marker,
            source_system="direct",
            tenant_id="tenant-qa",
            content_type="text/plain",
            db_manager=None,
            vertical="fsma",
        )
        assert event.source_url == marker
        assert event.tenant_id == "tenant-qa"
        assert event.is_duplicate is False


class TestIngestDirectErrorPassthrough:
    async def test_http_exception_not_masked_as_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.routes_ingest as routes_ingest
        from app.models import DirectIngestRequest

        def _boom(*_a, **_k):
            raise HTTPException(status_code=422, detail="Document parsing failed")

        monkeypatch.setattr(routes_ingest, "_process_and_emit", _boom)
        monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)

        with pytest.raises(HTTPException) as exc:
            await routes_ingest.ingest_direct(
                DirectIngestRequest(text="hi", source_system="s"),
                SimpleNamespace(tenant_id="tenant-qa"),
            )
        assert exc.value.status_code == 422

    async def test_direct_ingest_succeeds_with_default_marker(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.routes_ingest as routes_ingest
        from app.models import DirectIngestRequest

        monkeypatch.setattr(routes_ingest, "put_bytes", lambda *a, **k: "s3://raw/x")
        monkeypatch.setattr(routes_ingest, "put_json", lambda *a, **k: "s3://processed/y")
        monkeypatch.setattr(routes_ingest, "send", lambda *a, **k: None)
        monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)

        event = await routes_ingest.ingest_direct(
            DirectIngestRequest(text="regulation text", source_system="s"),
            SimpleNamespace(tenant_id="tenant-qa"),
        )
        assert event.source_url == MANUAL_MARKER


class TestRateLimitPrefixBoundaries:
    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/ingest",
            "/api/v1/ingest/url",
            "/api/v1/records",
            "/api/v1/records/sample",
            "/api/v1/webhooks/recent",
            "/api/v1/fda/export/run",
        ],
    )
    def test_limited_paths_match(self, path: str) -> None:
        from app.middleware.ratelimit_headers import _RATE_LIMITED_PREFIXES, _path_matches

        assert _path_matches(path, _RATE_LIMITED_PREFIXES) is True

    @pytest.mark.parametrize(
        "path",
        [
            "/healthz",
            "/api/v1/ingestion",  # prefix string but different route
            "/api/v1/recordsXYZ",
            "/api/v1/webhook",  # singular: no such prefix
            "/api/v1/fda/exporter/run",
        ],
    )
    def test_unlimited_paths_do_not_match(self, path: str) -> None:
        from app.middleware.ratelimit_headers import _RATE_LIMITED_PREFIXES, _path_matches

        assert _path_matches(path, _RATE_LIMITED_PREFIXES) is False
