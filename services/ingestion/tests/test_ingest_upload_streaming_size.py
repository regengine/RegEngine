"""Tests for streaming size enforcement on file-upload endpoints.

RE-SEC-INGEST-002: ``ingest_file`` (and ``ingest_regulation``) previously called
``await file.read()`` with no size argument, fully buffering an oversize upload
into memory before ``_enforce_size_limit`` ran. An authenticated attacker
(rate-limited at 10 req/min/key) could memory-DoS the service by submitting
oversize uploads.

These tests confirm the handler stream-reads the upload in 1 MiB chunks and
short-circuits with HTTP 413 the moment the running total exceeds the
threshold, BEFORE the whole payload has been consumed.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app import routes_ingest


class _ChunkingUploadFile:
    """Minimal ``UploadFile``-compatible stub.

    ``read(size)`` returns up to ``size`` bytes per call from a backing
    bytestring, tracking how many ``read`` calls were made so the test can
    prove the handler did NOT consume the entire stream when it exceeded the
    cap.
    """

    def __init__(self, total_size: int, *, filename: str = "big.pdf",
                 content_type: str = "application/pdf"):
        self._total = total_size
        self._pos = 0
        self.filename = filename
        self.content_type = content_type
        self.read_calls = 0
        self.bytes_read = 0

    async def read(self, size: int = -1) -> bytes:
        self.read_calls += 1
        remaining = self._total - self._pos
        if remaining <= 0:
            return b""
        if size is None or size < 0:
            n = remaining
        else:
            n = min(size, remaining)
        self._pos += n
        self.bytes_read += n
        # Return a constant byte; content is irrelevant for the size guard.
        return b"\x00" * n


def _api_key(tenant_id: str = "tenant-x"):
    key = MagicMock()
    key.tenant_id = tenant_id
    key.allowed_jurisdictions = ["US"]
    return key


# ---------------------------------------------------------------------------
# /v1/ingest/file
# ---------------------------------------------------------------------------


def test_ingest_file_oversize_short_circuits_with_413(monkeypatch):
    """An upload larger than MAX_PAYLOAD_BYTES must raise 413 BEFORE the
    whole payload is buffered."""
    # Skip DB; the handler tolerates a None db_manager.
    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)

    oversize = routes_ingest.MAX_PAYLOAD_BYTES + (5 * 1024 * 1024)  # +5 MiB
    upload = _ChunkingUploadFile(total_size=oversize)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            routes_ingest.ingest_file(
                file=upload,
                source_system="generic",
                vertical=None,
                api_key=_api_key(),
            )
        )

    assert exc.value.status_code == 413
    # Critical: handler must NOT have consumed more than ~1 chunk past the
    # cap. Allow one extra chunk for the chunk that tripped the guard.
    one_chunk = 1 << 20
    assert upload.bytes_read <= routes_ingest.MAX_PAYLOAD_BYTES + one_chunk, (
        f"handler buffered {upload.bytes_read} bytes; expected early "
        f"termination near {routes_ingest.MAX_PAYLOAD_BYTES}"
    )
    # And it must be substantially less than the full oversize payload.
    assert upload.bytes_read < oversize


def test_ingest_file_under_limit_succeeds_in_size_check(monkeypatch):
    """An upload at exactly MAX_PAYLOAD_BYTES must pass the streaming guard.

    We don't run the full pipeline — we just confirm the streaming loop
    consumed the whole stream and did not raise 413.
    """
    monkeypatch.setattr(routes_ingest, "get_db_manager", lambda: None)
    # Stub _process_and_emit so we don't actually parse anything; the test
    # only cares that the streaming size check did not 413.
    monkeypatch.setattr(
        routes_ingest, "_process_and_emit",
        lambda **kwargs: MagicMock(name="event"),
    )

    upload = _ChunkingUploadFile(total_size=routes_ingest.MAX_PAYLOAD_BYTES)
    # Should not raise
    result = asyncio.run(
        routes_ingest.ingest_file(
            file=upload,
            source_system="generic",
            vertical=None,
            api_key=_api_key(),
        )
    )
    assert result is not None
    assert upload.bytes_read == routes_ingest.MAX_PAYLOAD_BYTES


# ---------------------------------------------------------------------------
# /v1/ingest/regulation
# ---------------------------------------------------------------------------


def test_ingest_regulation_oversize_short_circuits_with_413(monkeypatch):
    """The regulation upload handler must also stream-check size to 100 MB."""
    # Make sure no DB / Redis / enqueue side effects fire before the size guard.
    monkeypatch.setattr(routes_ingest, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(routes_ingest, "enqueue_task", MagicMock())
    monkeypatch.setattr(routes_ingest.redis, "from_url", lambda *a, **kw: MagicMock())

    oversize = (100 * 1024 * 1024) + (2 * 1024 * 1024)  # 102 MiB
    upload = _ChunkingUploadFile(
        total_size=oversize, filename="reg.pdf", content_type="application/pdf"
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            routes_ingest.ingest_regulation(
                file=upload,
                name="some-reg",
                webhook=None,
                api_key=_api_key(),
            )
        )

    assert exc.value.status_code == 413
    one_chunk = 1 << 20
    assert upload.bytes_read <= (100 * 1024 * 1024) + one_chunk
    assert upload.bytes_read < oversize
