"""Regression tests for text_loader size + MIME + decode hardening (#1120).

Covers the DoS / silent-corruption failure modes closed by this fix:

* oversized Content-Length rejected before any bytes stream in
* streamed bytes exceeding the cap rejected even when Content-Length lies
* MIME types outside the allowlist rejected up-front
* malformed UTF-8 raises instead of being silently discarded
* an allowed MIME with a small body still proceeds normally
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _StreamCM:
    """Context manager stand-in for ``httpx.stream(...)`` that yields a
    prepared mock ``Response`` on ``__enter__``.

    ``httpx.stream`` returns a context manager whose ``__enter__`` hands
    back a ``Response``-like object with ``.headers`` / ``.iter_bytes()`` /
    ``.raise_for_status()``. Using a real class (instead of MagicMock's
    context-manager auto-spec) keeps the test intent obvious.
    """

    def __init__(self, headers: dict, chunks: list[bytes]):
        self._headers = headers
        self._chunks = chunks

    def __enter__(self):
        resp = MagicMock()
        resp.headers = self._headers
        resp.iter_bytes.return_value = iter(self._chunks)
        resp.raise_for_status.return_value = None
        return resp

    def __exit__(self, exc_type, exc, tb):
        return False


class TestTextLoaderLimits1120:
    """Enforcement of MAX_DOC_BYTES / ALLOWED_MIMES / strict decode."""

    def test_oversized_content_length_rejected(self):
        """Content-Length > MAX_DOC_BYTES must fail fast with E_DOC_TOO_LARGE."""
        from services.nlp.app import text_loader
        from services.nlp.app.text_loader import load_artifact

        headers = {
            "Content-Type": "application/pdf",
            "Content-Length": str(text_loader.MAX_DOC_BYTES + 1),
        }

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(headers, [b""]),
            ):
                with pytest.raises(ValueError, match="E_DOC_TOO_LARGE"):
                    load_artifact("https://example.com/huge.pdf")

    def test_streaming_size_exceed_rejected(self):
        """Attacker lies about Content-Length then streams past the cap."""
        from services.nlp.app import text_loader
        from services.nlp.app.text_loader import load_artifact

        # Declare tiny Content-Length, then stream far more than MAX_DOC_BYTES.
        chunk_size = 1024 * 1024  # 1 MiB
        over_cap_chunks = [b"\x00" * chunk_size] * (
            (text_loader.MAX_DOC_BYTES // chunk_size) + 5
        )
        headers = {
            "Content-Type": "application/pdf",
            "Content-Length": "100",  # lie
        }

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(headers, over_cap_chunks),
            ):
                with pytest.raises(ValueError, match="E_DOC_TOO_LARGE"):
                    load_artifact("https://example.com/lying.pdf")

    def test_disallowed_mime_rejected(self):
        """application/zip (not in ALLOWED_MIMES) must be rejected."""
        from services.nlp.app.text_loader import load_artifact

        headers = {
            "Content-Type": "application/zip",
            "Content-Length": "10",
        }

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(headers, [b"PK\x03\x04zipd"]),
            ):
                with pytest.raises(ValueError, match="E_DOC_MIME_DISALLOWED"):
                    load_artifact("https://example.com/archive.zip")

    def test_bad_utf8_raises_not_silent(self):
        """Invalid UTF-8 must raise E_DOC_DECODE_FAILED, not silently drop."""
        from services.nlp.app.text_loader import load_artifact

        # 0xff 0xfe is not valid UTF-8 as a stand-alone leading byte sequence.
        bad = b"prefix \xff\xfe\xfd suffix"
        headers = {
            "Content-Type": "text/plain",
            "Content-Length": str(len(bad)),
        }

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(headers, [bad]),
            ):
                with pytest.raises(ValueError, match="E_DOC_DECODE_FAILED"):
                    load_artifact("https://example.com/bad-utf8.txt")

    def test_allowed_mime_accepted(self):
        """Allowed MIME (application/pdf) with a small body proceeds normally."""
        from services.nlp.app.text_loader import load_artifact

        body = b"%PDF-1.4 tiny"
        headers = {
            "Content-Type": "application/pdf",
            "Content-Length": str(len(body)),
        }

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(headers, [body]),
            ):
                with patch(
                    "services.nlp.app.text_loader.pdfminer"
                ) as mock_pdfminer:
                    mock_pdfminer.extract_text.return_value = "Extracted PDF text"

                    result = load_artifact("https://example.com/doc.pdf")

                    assert result == "Extracted PDF text"
                    # Page cap must be passed through to pdfminer.
                    _, kwargs = mock_pdfminer.extract_text.call_args
                    assert "maxpages" in kwargs
                    assert kwargs["maxpages"] > 0
