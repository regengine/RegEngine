"""QA coverage for ``app/shared`` edge cases and two bug fixes.

Covers behavior the existing ``*_1342`` suites leave untested:

* ``stream_upload_to_file_with_limit`` removes a partial staging file when
  the stream fails (oversize upload or mid-write error). Previously the
  helper left whatever it had already written on disk.
* ``validated_image_content_type`` had no tests at all. It now also accepts
  a case-variant declared content type (media types are case-insensitive),
  while Pillow-sniffed bytes remain authoritative.
* filename, regulation, tenant-resolution, and csv-shim parity edges.
"""

from __future__ import annotations

import asyncio
import io

import pytest
from app.shared import upload_limits
from app.shared.csv_safety import sanitize_cell, sanitize_row, sanitize_sequence
from app.shared.tenant_resolution import resolve_principal_tenant_id, resolve_tenant_id
from app.shared.upload_limits import (
    regulation_upload_type,
    sanitize_upload_filename,
    stream_upload_to_file_with_limit,
    validate_regulation_upload_content,
    validated_image_content_type,
)
from fastapi import HTTPException, UploadFile


def _run(coro):
    return asyncio.run(coro)


def _make_upload(data: bytes, filename: str = "test.bin") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(data))


class _FailingUpload:
    """Yields ``fail_after`` chunks, then raises OSError (disk full)."""

    def __init__(self, chunks: list[bytes], fail_after: int = 1) -> None:
        self._chunks = list(chunks)
        self._fail_after = fail_after
        self._reads = 0

    async def read(self, size: int = -1) -> bytes:
        if self._reads >= self._fail_after:
            raise OSError("disk full")
        chunk = self._chunks[self._reads] if self._reads < len(self._chunks) else b""
        self._reads += 1
        return chunk


def _png_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (8, 8), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (8, 8), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _ppm_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (8, 8), color="green")
    buf = io.BytesIO()
    img.save(buf, format="PPM")
    return buf.getvalue()


class _FakeRow:
    def __init__(self, *cols):
        self._cols = cols

    def __getitem__(self, idx):
        return self._cols[idx]


class _FakeDb:
    def __init__(self, fetch_row=None):
        self._fetch_row = fetch_row
        self.executed: list = []
        self.closed = False

    def execute(self, statement, params=None):
        from unittest.mock import MagicMock

        self.executed.append({"statement": str(statement), "params": params})
        result = MagicMock()
        result.fetchone = MagicMock(return_value=self._fetch_row)
        return result

    def close(self):
        self.closed = True


# ===========================================================================
# stream_upload_to_file_with_limit: partial-file cleanup (bug fix)
# ===========================================================================


class TestStreamPartialFileCleanup:
    def test_oversize_removes_partial_path_file(self, tmp_path):
        """First chunk is written, second exceeds the cap: no file may remain."""
        payload = b"A" * (64 * 1024) + b"B" * 100
        destination = tmp_path / "upload.bin"
        with pytest.raises(HTTPException) as exc_info:
            _run(
                stream_upload_to_file_with_limit(
                    _make_upload(payload),
                    destination,
                    max_bytes=64 * 1024,
                    label="streamed file",
                )
            )
        assert exc_info.value.status_code == 413
        assert not destination.exists()

    def test_mid_write_error_removes_partial_path_file(self, tmp_path):
        """A disk error after bytes were staged must not leave the fragment."""
        destination = tmp_path / "upload.bin"
        with pytest.raises(OSError, match="disk full"):
            _run(
                stream_upload_to_file_with_limit(
                    _FailingUpload([b"x" * 100]),
                    destination,
                    max_bytes=1024 * 1024,
                )
            )
        assert not destination.exists()

    def test_success_keeps_file_and_returns_prefix(self, tmp_path):
        payload = b"%PDF-" + b"A" * 100
        destination = tmp_path / "upload.pdf"
        total, prefix = _run(
            stream_upload_to_file_with_limit(
                _make_upload(payload), destination, max_bytes=1024, prefix_bytes=8
            )
        )
        assert total == len(payload)
        assert prefix == payload[:8]
        assert destination.read_bytes() == payload

    def test_empty_upload_to_path_writes_empty_file(self, tmp_path):
        destination = tmp_path / "empty.bin"
        total, prefix = _run(
            stream_upload_to_file_with_limit(_make_upload(b""), destination, max_bytes=1024)
        )
        assert total == 0
        assert prefix == b""
        assert destination.exists()
        assert destination.read_bytes() == b""

    def test_prefix_accumulates_across_chunks(self, tmp_path):
        payload = b"P" * (64 * 1024) + b"Q" * (64 * 1024)
        destination = tmp_path / "upload.bin"
        total, prefix = _run(
            stream_upload_to_file_with_limit(
                _make_upload(payload), destination, max_bytes=1024 * 1024, prefix_bytes=70 * 1024
            )
        )
        assert total == len(payload)
        assert prefix == payload[: 70 * 1024]

    def test_file_like_destination_still_streams(self):
        payload = b"hello"
        buf = io.BytesIO()
        total, prefix = _run(
            stream_upload_to_file_with_limit(_make_upload(payload), buf, max_bytes=1024)
        )
        assert total == len(payload)
        assert prefix == payload
        assert buf.getvalue() == payload


# ===========================================================================
# validated_image_content_type (previously untested)
# ===========================================================================


class TestValidatedImageContentType:
    def test_valid_png_returns_detected_type(self):
        assert validated_image_content_type(_png_bytes(), "image/png") == "image/png"

    def test_valid_jpeg_returns_detected_type(self):
        assert validated_image_content_type(_jpeg_bytes(), "image/jpeg") == "image/jpeg"

    def test_sniffed_bytes_win_over_declared_type(self):
        """A PNG declared as JPEG is still identified as PNG."""
        assert validated_image_content_type(_png_bytes(), "image/jpeg") == "image/png"

    def test_uppercase_declared_type_accepted(self):
        """Media types are case-insensitive; Pillow still verifies the bytes."""
        assert validated_image_content_type(_png_bytes(), "Image/PNG") == "image/png"

    def test_declared_type_with_parameters_accepted(self):
        assert (
            validated_image_content_type(_jpeg_bytes(), "IMAGE/JPEG; charset=binary")
            == "image/jpeg"
        )

    def test_missing_declared_type_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validated_image_content_type(_png_bytes(), None)
        assert exc_info.value.status_code == 400

    def test_non_image_declared_type_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validated_image_content_type(_png_bytes(), "text/plain")
        assert exc_info.value.status_code == 400

    def test_empty_bytes_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validated_image_content_type(b"", "image/png")
        assert exc_info.value.status_code == 400
        assert "empty" in exc_info.value.detail.lower()

    def test_corrupt_bytes_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validated_image_content_type(b"\x89PNG not really an image", "image/png")
        assert exc_info.value.status_code == 400

    def test_svg_markup_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validated_image_content_type(
                b'<svg xmlns="http://www.w3.org/2000/svg"></svg>', "image/svg+xml"
            )
        assert exc_info.value.status_code == 400

    def test_unsupported_raster_format_rejected(self):
        """PPM opens in Pillow but is not an accepted upload format."""
        with pytest.raises(HTTPException) as exc_info:
            validated_image_content_type(_ppm_bytes(), "image/x-portable-pixmap")
        assert exc_info.value.status_code == 400
        assert "Unsupported" in exc_info.value.detail


# ===========================================================================
# sanitize_upload_filename and regulation validation edges
# ===========================================================================


class TestSanitizeFilenameEdges:
    def test_none_uses_fallback(self):
        assert sanitize_upload_filename(None) == "upload"
        assert sanitize_upload_filename(None, fallback="attachment.csv") == "attachment.csv"

    def test_windows_fakepath_reduced_to_basename(self):
        assert sanitize_upload_filename("C:\\fakepath\\report.pdf") == "report.pdf"

    def test_absolute_path_traversal_reduced_to_basename(self):
        assert sanitize_upload_filename("/etc/passwd") == "passwd"
        assert sanitize_upload_filename("..\\..\\secret.pdf") == "secret.pdf"

    def test_hidden_dotfile_without_stem_is_safe(self):
        assert sanitize_upload_filename(".pdf") == "pdf"

    def test_control_characters_stripped(self):
        assert sanitize_upload_filename("re\x00port\t.pdf") == "report.pdf"

    def test_truncation_preserves_extension_within_cap(self):
        long_stem = "r" * 200
        out = sanitize_upload_filename(f"{long_stem}.pdf")
        assert len(out) <= 120
        assert out.endswith(".pdf")

    def test_truncation_without_extension_truncates(self):
        out = sanitize_upload_filename("x" * 200)
        assert out == "x" * 120


class TestRegulationValidationEdges:
    def test_none_filename_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            regulation_upload_type(None)
        assert exc_info.value.status_code == 400

    def test_double_extension_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            regulation_upload_type("report.pdf.exe")
        assert exc_info.value.status_code == 400

    def test_docx_bad_magic_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_regulation_upload_content("docx", b"not-a-zip-header")
        assert exc_info.value.status_code == 400

    def test_docx_corrupt_zip_rejected(self, tmp_path):
        corrupt = tmp_path / "corrupt.docx"
        corrupt.write_bytes(b"PK\x03\x04" + b"\x00" * 64)
        with pytest.raises(HTTPException) as exc_info:
            validate_regulation_upload_content("docx", b"PK\x03\x04" + b"\x00" * 4, path=corrupt)
        assert exc_info.value.status_code == 400

    def test_unknown_file_type_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_regulation_upload_content("txt", b"whatever")
        assert exc_info.value.status_code == 400

    def test_empty_pdf_prefix_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_regulation_upload_content("pdf", b"")
        assert exc_info.value.status_code == 400


# ===========================================================================
# tenant resolution edges (auth boundaries)
# ===========================================================================


class TestTenantResolutionEdges:
    def test_whitespace_only_inputs_resolve_to_none_without_db(self, monkeypatch):
        from app.shared import tenant_resolution

        called = {"flag": False}

        def _sentinel():
            called["flag"] = True
            return _FakeDb()

        monkeypatch.setattr(tenant_resolution, "get_db_safe", _sentinel)
        assert resolve_tenant_id("   ", "  ", "  ") is None
        assert called["flag"] is False

    def test_surrounding_whitespace_ignored_before_conflict_check(self):
        assert resolve_tenant_id("  tenant-a  ", "tenant-a", None) == "tenant-a"

    def test_malformed_api_key_falls_back_without_db_query(self, monkeypatch):
        """A key without the ``rge_`` prefix cannot arm a lookup: no query runs."""
        from app.shared import tenant_resolution

        db = _FakeDb(fetch_row=_FakeRow("tenant-xyz"))
        monkeypatch.setattr(tenant_resolution, "get_db_safe", lambda: db)
        assert resolve_tenant_id(None, "header-tenant", "not-a-real-key") == "header-tenant"
        assert db.executed == []

    def test_db_tenant_value_with_whitespace_is_stripped(self, monkeypatch):
        from app.shared import tenant_resolution

        db = _FakeDb(fetch_row=_FakeRow("  tenant-xyz  "))
        monkeypatch.setattr(tenant_resolution, "get_db_safe", lambda: db)
        assert (
            resolve_tenant_id(None, None, "rge_test.secret-key-material")  # pragma: allowlist secret
            == "tenant-xyz"
        )

    def test_session_acquire_failure_propagates(self, monkeypatch):
        """If no DB session can be acquired, the error surfaces: the request
        is never silently treated as an unauthenticated header-tenant call."""
        from app.shared import tenant_resolution

        def _boom():
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(tenant_resolution, "get_db_safe", _boom)
        with pytest.raises(RuntimeError, match="db unavailable"):
            resolve_tenant_id(None, "header-tenant", "rge_test.secret-key-material")  # pragma: allowlist secret

    def test_whitespace_principal_treated_as_missing(self):
        assert resolve_principal_tenant_id(None, "header-tenant", "   ") == "header-tenant"

    def test_principal_helper_seeds_rls_context(self):
        from shared.tenant_context import get_rls_tenant_id, set_rls_tenant_id

        try:
            assert resolve_principal_tenant_id(None, None, "principal-tenant") == "principal-tenant"
            assert get_rls_tenant_id() == "principal-tenant"
        finally:
            set_rls_tenant_id(None)


# ===========================================================================
# csv_safety shim parity with the canonical implementation
# ===========================================================================


class TestCsvShimParity:
    def test_shim_functions_are_canonical_objects(self):
        from shared.fda_export import csv_safety as canonical

        assert sanitize_cell is canonical.safe_cell
        assert sanitize_row is canonical.safe_row
        assert sanitize_sequence is canonical.safe_sequence

    def test_module_exports_expected_names(self):
        assert upload_limits.MAX_FILE_SIZE_BYTES == 10 * 1024 * 1024
        assert set(upload_limits._IMAGE_CONTENT_TYPES.values()) == {
            "image/bmp",
            "image/gif",
            "image/jpeg",
            "image/png",
            "image/tiff",
            "image/webp",
        }
