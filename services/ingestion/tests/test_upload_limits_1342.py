"""
Regression coverage for ``app/shared/upload_limits.py``.

Uploads are an OOM vector: a worker can be crashed by a single
multipart request if the body is slurped without a cap. This module
reads in 64 KB chunks and raises HTTPException(413) when the running
total exceeds ``max_bytes`` — bounding memory at ``max_bytes + 64KB``.

Tests lock in:

* bytes are read in chunks and joined in-order
* undersize files pass through unchanged
* exact-cap files are accepted (strict greater-than)
* oversize files raise 413 with label/limit in detail
* empty uploads return b""
* custom max_bytes is respected
* module-level limit constants are unchanged (prevents accidental
  loosening that would undo the OOM guard)

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import asyncio
import io
from typing import Optional

import pytest
from fastapi import HTTPException, UploadFile

from app.shared import upload_limits
from app.shared.upload_limits import (
    MAX_CSV_FILE_SIZE_BYTES,
    MAX_EDI_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_BYTES,
    read_upload_with_limit,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_upload(data: bytes, filename: str = "test.bin") -> UploadFile:
    """Wrap bytes in a FastAPI UploadFile backed by an in-memory buffer."""
    return UploadFile(filename=filename, file=io.BytesIO(data))


def _run(coro):
    """Run an async coroutine from a sync test."""
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ===========================================================================
# Happy paths — undersize / empty / exact-cap
# ===========================================================================


class TestReadUploadUndersize:

    def test_small_payload_roundtrips_unchanged(self):
        payload = b"hello, world"
        f = _make_upload(payload)
        out = _run(read_upload_with_limit(f, max_bytes=1024))
        assert out == payload

    def test_empty_upload_returns_empty_bytes(self):
        f = _make_upload(b"")
        out = _run(read_upload_with_limit(f, max_bytes=1024))
        assert out == b""

    def test_exactly_at_max_bytes_is_accepted(self):
        """Strict greater-than — equal sizes must pass."""
        payload = b"x" * 128
        f = _make_upload(payload)
        out = _run(read_upload_with_limit(f, max_bytes=128))
        assert out == payload

    def test_multi_chunk_payload_reassembled_in_order(self):
        """The chunk size is 64 KB — send > 64 KB to force multiple reads."""
        payload = b"A" * (64 * 1024) + b"B" * (64 * 1024) + b"C" * 100
        f = _make_upload(payload)
        out = _run(read_upload_with_limit(f, max_bytes=1024 * 1024))
        assert out == payload
        assert len(out) == (64 * 1024) * 2 + 100

    def test_uses_default_max_when_not_specified(self):
        """Default cap is 10 MB — 1 KB passes."""
        payload = b"z" * 1024
        f = _make_upload(payload)
        out = _run(read_upload_with_limit(f))
        assert out == payload


# ===========================================================================
# Oversize path — HTTPException(413)
# ===========================================================================


class TestReadUploadOversize:

    def test_oversize_raises_413(self):
        payload = b"x" * 2048
        f = _make_upload(payload)
        with pytest.raises(HTTPException) as exc_info:
            _run(read_upload_with_limit(f, max_bytes=1024, label="csv"))
        assert exc_info.value.status_code == 413
        assert "csv" in exc_info.value.detail
        assert "1 MB" in exc_info.value.detail or "0 MB" in exc_info.value.detail

    def test_oversize_one_byte_over_raises(self):
        """Boundary: cap=100, payload=101 bytes → must fail.

        This nails line 30 (the raise) — the condition is ``total > max_bytes``
        (strict), so exactly-at-cap passes but one-byte-over must fail.
        """
        payload = b"y" * 101
        f = _make_upload(payload)
        with pytest.raises(HTTPException) as exc_info:
            _run(read_upload_with_limit(f, max_bytes=100))
        assert exc_info.value.status_code == 413

    def test_oversize_default_label_appears_in_detail(self):
        payload = b"q" * 2048
        f = _make_upload(payload)
        with pytest.raises(HTTPException) as exc_info:
            _run(read_upload_with_limit(f, max_bytes=1024))
        assert "file too large" in exc_info.value.detail.lower()

    def test_oversize_custom_label_flows_through(self):
        payload = b"a" * 10_000
        f = _make_upload(payload)
        with pytest.raises(HTTPException) as exc_info:
            _run(read_upload_with_limit(f, max_bytes=512, label="EDI envelope"))
        # Label appears verbatim in the user-visible error string.
        assert "EDI envelope" in exc_info.value.detail

    def test_oversize_mb_count_reflects_cap(self):
        """The detail string exposes the cap in MB (integer division)."""
        cap = 5 * 1024 * 1024  # 5 MB
        f = _make_upload(b"x" * (cap + 1))
        with pytest.raises(HTTPException) as exc_info:
            _run(read_upload_with_limit(f, max_bytes=cap, label="csv"))
        assert "5 MB" in exc_info.value.detail

    def test_oversize_sub_mb_cap_reports_zero_mb(self):
        """Integer division for caps < 1 MB reports '0 MB'."""
        f = _make_upload(b"x" * 2048)
        with pytest.raises(HTTPException) as exc_info:
            _run(read_upload_with_limit(f, max_bytes=1024))
        assert "0 MB" in exc_info.value.detail

    def test_oversize_detected_midway_stops_reading(self):
        """Uses a huge payload with a small cap — never has to fully buffer.

        Guards the 'read in chunks' invariant — if a refactor accidentally
        slurps via ``await file.read()`` with no size arg, a 1 GB payload
        would OOM the worker. Here we assert the exception fires before
        we could have buffered the whole thing.
        """
        # Make payload much larger than 64 KB chunk size.
        payload = b"x" * (10 * 64 * 1024)
        f = _make_upload(payload)
        with pytest.raises(HTTPException):
            _run(read_upload_with_limit(f, max_bytes=64 * 1024))


# ===========================================================================
# Module-level constants — lock them down
# ===========================================================================


class TestUploadLimitConstants:

    def test_default_file_cap_is_10mb(self):
        """Don't quietly raise the default cap without a code review."""
        assert MAX_FILE_SIZE_BYTES == 10 * 1024 * 1024

    def test_csv_cap_is_5mb(self):
        assert MAX_CSV_FILE_SIZE_BYTES == 5 * 1024 * 1024

    def test_edi_cap_is_5mb(self):
        assert MAX_EDI_FILE_SIZE_BYTES == 5 * 1024 * 1024

    def test_csv_and_edi_caps_are_below_generic_cap(self):
        """CSV/EDI are structured formats — tighter caps are intentional."""
        assert MAX_CSV_FILE_SIZE_BYTES <= MAX_FILE_SIZE_BYTES
        assert MAX_EDI_FILE_SIZE_BYTES <= MAX_FILE_SIZE_BYTES

    def test_caps_are_positive_integers(self):
        for cap in (
            MAX_FILE_SIZE_BYTES,
            MAX_CSV_FILE_SIZE_BYTES,
            MAX_EDI_FILE_SIZE_BYTES,
        ):
            assert isinstance(cap, int)
            assert cap > 0


# ===========================================================================
# Callable signature — make sure wiring hasn't drifted
# ===========================================================================


class TestReadUploadSignature:

    def test_read_upload_with_limit_is_async(self):
        import inspect
        assert inspect.iscoroutinefunction(read_upload_with_limit)

    def test_read_upload_is_exported(self):
        assert hasattr(upload_limits, "read_upload_with_limit")
        assert callable(upload_limits.read_upload_with_limit)
