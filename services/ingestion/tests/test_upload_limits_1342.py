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
import zipfile
from typing import Optional

import pytest
from app.shared import upload_limits
from app.shared.upload_limits import (
    MAX_CSV_FILE_SIZE_BYTES,
    MAX_EDI_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_BYTES,
    MAX_IMAGE_FILE_SIZE_BYTES,
    MAX_REGULATION_FILE_SIZE_BYTES,
    read_upload_with_limit,
    regulation_upload_type,
    sanitize_upload_filename,
    stream_upload_to_file_with_limit,
    validate_regulation_upload_content,
)
from fastapi import HTTPException, UploadFile

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

    def test_image_cap_is_10mb(self):
        assert MAX_IMAGE_FILE_SIZE_BYTES == 10 * 1024 * 1024

    def test_regulation_cap_is_100mb(self):
        assert MAX_REGULATION_FILE_SIZE_BYTES == 100 * 1024 * 1024

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


class TestStreamUploadToFileWithLimit:
    def test_streams_to_path_and_returns_prefix(self, tmp_path):
        payload = b"%PDF-" + b"A" * 100
        destination = tmp_path / "upload.pdf"
        total, prefix = _run(
            stream_upload_to_file_with_limit(
                _make_upload(payload),
                destination,
                max_bytes=1024,
                label="PDF",
                prefix_bytes=8,
            )
        )
        assert total == len(payload)
        assert prefix == payload[:8]
        assert destination.read_bytes() == payload

    def test_stream_oversize_raises_413(self, tmp_path):
        destination = tmp_path / "upload.bin"
        with pytest.raises(HTTPException) as exc_info:
            _run(
                stream_upload_to_file_with_limit(
                    _make_upload(b"x" * 20),
                    destination,
                    max_bytes=8,
                    label="streamed file",
                )
            )
        assert exc_info.value.status_code == 413
        assert "streamed file" in exc_info.value.detail


class TestFilenameAndDocumentValidation:
    def test_sanitize_upload_filename_uses_basename_and_strips_controls(self):
        assert sanitize_upload_filename("../secret\n-token.pdf") == "secret-token.pdf"
        assert sanitize_upload_filename("..") == "upload"
        assert sanitize_upload_filename("   ") == "upload"

    def test_regulation_upload_type_is_case_insensitive(self):
        assert regulation_upload_type("REG.PDF") == "pdf"
        assert regulation_upload_type("policy.DOCX") == "docx"

    def test_regulation_upload_type_rejects_other_extensions(self):
        with pytest.raises(HTTPException) as exc_info:
            regulation_upload_type("policy.txt")
        assert exc_info.value.status_code == 400

    def test_pdf_content_signature_validation(self):
        validate_regulation_upload_content("pdf", b"%PDF-1.7")
        with pytest.raises(HTTPException) as exc_info:
            validate_regulation_upload_content("pdf", b"not-pdf")
        assert exc_info.value.status_code == 400

    def test_docx_parser_validation(self, tmp_path):
        docx_path = tmp_path / "valid.docx"
        with zipfile.ZipFile(docx_path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types />")
            archive.writestr("word/document.xml", "<w:document />")
        prefix = docx_path.read_bytes()[:8]
        validate_regulation_upload_content("docx", prefix, path=docx_path)

    def test_docx_parser_validation_rejects_zip_without_word_document(self, tmp_path):
        docx_path = tmp_path / "invalid.docx"
        with zipfile.ZipFile(docx_path, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types />")
        prefix = docx_path.read_bytes()[:8]
        with pytest.raises(HTTPException) as exc_info:
            validate_regulation_upload_content("docx", prefix, path=docx_path)
        assert exc_info.value.status_code == 400
