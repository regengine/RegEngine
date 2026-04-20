"""Regression test for GitHub issue #1080.

A PDF bomb -- a small wire-size PDF that decompresses into tens of thousands
of pages -- would previously pin the admin service at 100% CPU for minutes
because ``_parse_pdf_bytes`` iterated ``pdf.pages`` twice with no upper
bound. The 10 MB upload-size cap in ``parse_incoming_file`` bounds wire size
only; it does not bound post-decompression page count.

The fix caps page count at 200 (override: ``BULK_UPLOAD_MAX_PDF_PAGES``) and
raises HTTP 413 before the first ``page.extract_tables()`` / ``extract_text``
call. These tests assert that behavior.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.bulk_upload import parsers
from app.bulk_upload.parsers import (
    DEFAULT_MAX_PDF_PAGES,
    _max_pdf_pages,
    _parse_pdf_bytes,
)


class _FakePdf:
    """Minimal stand-in for ``pdfplumber.PDF`` for bomb-simulation tests.

    Supports context-manager protocol and exposes ``pages`` as a real list
    of ``MagicMock`` instances so ``len(pdf.pages)`` works identically to
    the real object.
    """

    def __init__(self, page_count: int) -> None:
        self.pages = [MagicMock(name=f"page-{i}") for i in range(page_count)]
        # If anything *does* try to iterate, fail loudly so the test
        # surfaces the regression instead of silently hanging.
        for page in self.pages:
            page.extract_tables.side_effect = AssertionError(
                "page.extract_tables called despite page-count guard"
            )
            page.extract_text.side_effect = AssertionError(
                "page.extract_text called despite page-count guard"
            )

    def __enter__(self) -> "_FakePdf":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        return None


def _fake_pdfplumber_module(page_count: int) -> SimpleNamespace:
    """Build a stand-in module whose ``open()`` yields a ``_FakePdf``."""
    return SimpleNamespace(open=lambda _buf: _FakePdf(page_count))


def test_parse_pdf_bytes_rejects_page_bomb():
    """300-page PDF bomb -> HTTPException(413) before any page is touched."""
    bomb = _fake_pdfplumber_module(page_count=300)

    parsed: dict = {
        "detected_format": "pdf",
        "facilities": [],
        "ftl_scopes": [],
        "tlcs": [],
        "events": [],
        "warnings": [],
    }
    warnings: list[str] = parsed["warnings"]

    with patch.dict("sys.modules", {"pdfplumber": bomb}):
        with pytest.raises(HTTPException) as exc_info:
            _parse_pdf_bytes(b"%PDF-1.4 fake-bomb", parsed, warnings)

    assert exc_info.value.status_code == 413
    assert "300" in exc_info.value.detail
    assert str(DEFAULT_MAX_PDF_PAGES) in exc_info.value.detail


def test_parse_pdf_bytes_accepts_under_cap_no_page_iteration_error():
    """At-cap page count is accepted -- the guard only raises *above* cap.

    Uses ``DEFAULT_MAX_PDF_PAGES`` pages. Each page is a ``MagicMock`` that
    returns no tables and no text, so the parser should fall through to the
    "no structured rows detected" warning rather than raising.
    """
    under_cap_module = SimpleNamespace(
        open=lambda _buf: _UnderCapFakePdf(DEFAULT_MAX_PDF_PAGES)
    )

    parsed: dict = {
        "detected_format": "pdf",
        "facilities": [],
        "ftl_scopes": [],
        "tlcs": [],
        "events": [],
        "warnings": [],
    }
    warnings: list[str] = parsed["warnings"]

    with patch.dict("sys.modules", {"pdfplumber": under_cap_module}):
        _parse_pdf_bytes(b"%PDF-1.4 fake", parsed, warnings)

    # No HTTPException raised. The parser falls through to the empty-PDF
    # branch and appends a warning, which is fine for this test.
    assert any("no structured rows detected" in w for w in warnings)


class _UnderCapFakePdf:
    """Like ``_FakePdf`` but pages return empty so iteration completes."""

    def __init__(self, page_count: int) -> None:
        self.pages = []
        for _ in range(page_count):
            page = MagicMock()
            page.extract_tables.return_value = []
            page.extract_text.return_value = ""
            self.pages.append(page)

    def __enter__(self) -> "_UnderCapFakePdf":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_max_pdf_pages_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BULK_UPLOAD_MAX_PDF_PAGES", raising=False)
    assert _max_pdf_pages() == DEFAULT_MAX_PDF_PAGES


def test_max_pdf_pages_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BULK_UPLOAD_MAX_PDF_PAGES", "50")
    assert _max_pdf_pages() == 50


def test_max_pdf_pages_invalid_env_falls_back(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BULK_UPLOAD_MAX_PDF_PAGES", "not-a-number")
    assert _max_pdf_pages() == DEFAULT_MAX_PDF_PAGES


def test_max_pdf_pages_zero_or_negative_falls_back(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("BULK_UPLOAD_MAX_PDF_PAGES", "0")
    assert _max_pdf_pages() == DEFAULT_MAX_PDF_PAGES
    monkeypatch.setenv("BULK_UPLOAD_MAX_PDF_PAGES", "-5")
    assert _max_pdf_pages() == DEFAULT_MAX_PDF_PAGES


def test_page_cap_env_override_rejects_small_bomb(
    monkeypatch: pytest.MonkeyPatch,
):
    """With the cap lowered via env, a smaller "bomb" still trips 413."""
    monkeypatch.setenv("BULK_UPLOAD_MAX_PDF_PAGES", "10")
    bomb = _fake_pdfplumber_module(page_count=25)

    parsed: dict = {
        "detected_format": "pdf",
        "facilities": [],
        "ftl_scopes": [],
        "tlcs": [],
        "events": [],
        "warnings": [],
    }
    warnings: list[str] = parsed["warnings"]

    with patch.dict("sys.modules", {"pdfplumber": bomb}):
        with pytest.raises(HTTPException) as exc_info:
            _parse_pdf_bytes(b"%PDF-1.4 fake", parsed, warnings)

    assert exc_info.value.status_code == 413
    assert "25" in exc_info.value.detail
    assert "10" in exc_info.value.detail
    # Ensure ``parsers`` is referenced so pyflakes doesn't strip the import
    assert hasattr(parsers, "_parse_pdf_bytes")
