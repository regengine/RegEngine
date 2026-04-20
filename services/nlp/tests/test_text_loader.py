"""Tests for NLP text_loader module.

Covers:
- URL validation and SSRF protection
- PDF text extraction
- HTML to text conversion
- Fallback text decoding

Mocks the streaming ``httpx.stream(...)`` context manager introduced by the
size/MIME hardening in #1120.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class _StreamCM:
    """Stand-in for ``httpx.stream(...)`` context manager.

    ``httpx.stream`` returns a context manager whose ``__enter__`` yields a
    ``Response``-like object exposing ``.headers`` / ``.iter_bytes()`` /
    ``.raise_for_status()``. Using a concrete class keeps test intent
    obvious and avoids surprises from ``MagicMock``'s auto-spec.
    """

    def __init__(self, headers: dict, chunks: list[bytes], raise_exc=None):
        self._headers = headers
        self._chunks = chunks
        self._raise_exc = raise_exc

    def __enter__(self):
        resp = MagicMock()
        resp.headers = self._headers
        resp.iter_bytes.return_value = iter(self._chunks)
        if self._raise_exc is not None:
            resp.raise_for_status.side_effect = self._raise_exc
        else:
            resp.raise_for_status.return_value = None
        return resp

    def __exit__(self, exc_type, exc, tb):
        return False


def _headers(ctype: str, body: bytes) -> dict:
    return {"Content-Type": ctype, "Content-Length": str(len(body))}


class TestLoadArtifact:
    """Tests for load_artifact function."""

    def test_rejects_non_http_urls(self):
        """Verify non-http URLs are rejected."""
        from services.nlp.app.text_loader import load_artifact

        with pytest.raises(ValueError, match="Only http"):
            load_artifact("ftp://example.com/file.pdf")

        with pytest.raises(ValueError, match="Only http"):
            load_artifact("file:///etc/passwd")

        with pytest.raises(ValueError, match="Only http"):
            load_artifact("s3://bucket/key")

    def test_accepts_http_url(self):
        """Verify http URLs are accepted (with mocked request)."""
        from services.nlp.app.text_loader import load_artifact

        body = b"Sample text content"
        with patch("services.nlp.app.text_loader.validate_url") as mock_validate:
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(_headers("text/plain", body), [body]),
            ):
                result = load_artifact("http://example.com/doc.txt")

                assert result == "Sample text content"
                mock_validate.assert_called_once_with("http://example.com/doc.txt")

    def test_accepts_https_url(self):
        """Verify https URLs are accepted."""
        from services.nlp.app.text_loader import load_artifact

        body = b"Secure content"
        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(_headers("text/plain", body), [body]),
            ):
                result = load_artifact("https://secure.example.com/doc.txt")

                assert result == "Secure content"

    def test_validates_url_against_ssrf(self):
        """Verify SSRF validation is called."""
        from services.nlp.app.text_loader import load_artifact
        from shared.url_validation import SSRFError

        with patch("services.nlp.app.text_loader.validate_url") as mock_validate:
            mock_validate.side_effect = SSRFError("Private IP blocked")

            with pytest.raises(SSRFError):
                load_artifact("http://127.0.0.1/internal")

    def test_extracts_text_from_html(self):
        """Verify HTML content is converted to text."""
        from services.nlp.app.text_loader import load_artifact

        html_content = b"""
        <html>
            <head><title>Test</title></head>
            <body>
                <h1>Header</h1>
                <p>Paragraph text here.</p>
            </body>
        </html>
        """

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(
                    _headers("text/html", html_content), [html_content]
                ),
            ):
                result = load_artifact("https://example.com/page.html")

                assert "Header" in result
                assert "Paragraph text here" in result

    def test_handles_utf8_content(self):
        """Verify UTF-8 encoded content is handled."""
        from services.nlp.app.text_loader import load_artifact

        utf8_content = "Unicode: café, naïve, 日本語".encode("utf-8")

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(
                    _headers("text/plain; charset=utf-8", utf8_content),
                    [utf8_content],
                ),
            ):
                result = load_artifact("https://example.com/utf8.txt")

                assert "café" in result
                assert "日本語" in result

    def test_bad_utf8_raises_after_hardening(self):
        """Invalid UTF-8 must now raise (was: silently dropped pre-#1120)."""
        from services.nlp.app.text_loader import load_artifact

        # Invalid UTF-8 byte sequence -- prior behavior was to silently
        # drop these via ``errors="ignore"``, which mutilated TLCs and
        # other identifiers. Post-#1120 we fail loudly instead.
        binary_content = b"Valid text \xff\xfe invalid bytes"

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(
                    _headers("text/plain", binary_content), [binary_content]
                ),
            ):
                with pytest.raises(ValueError, match="E_DOC_DECODE_FAILED"):
                    load_artifact("https://example.com/binary.bin")


class TestPdfExtraction:
    """Tests for PDF text extraction."""

    def test_pdf_extraction_with_pdfminer(self):
        """Verify PDF content is extracted using pdfminer."""
        from services.nlp.app.text_loader import load_artifact

        pdf_content = b"%PDF-1.4 fake pdf content"

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(
                    _headers("application/pdf", pdf_content), [pdf_content]
                ),
            ):
                with patch("services.nlp.app.text_loader.pdfminer") as mock_pdfminer:
                    mock_pdfminer.extract_text.return_value = "Extracted PDF text"

                    result = load_artifact("https://example.com/doc.pdf")

                    assert result == "Extracted PDF text"

    def test_pdf_extraction_fallback_on_error(self):
        """Verify fallback when pdfminer fails."""
        from services.nlp.app.text_loader import load_artifact

        # Use a UTF-8-decodable body so the fallback path (bytes decode)
        # succeeds after pdfminer throws. Pre-#1120 invalid bytes would
        # have been swallowed; post-#1120 they raise, so the legitimate
        # fallback path now needs clean UTF-8.
        pdf_content = b"%PDF-1.4 corrupted pdf"

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(
                    _headers("application/pdf", pdf_content), [pdf_content]
                ),
            ):
                with patch("services.nlp.app.text_loader.pdfminer") as mock_pdfminer:
                    mock_pdfminer.extract_text.side_effect = Exception("PDF error")

                    # Should not raise, falls back to decode
                    result = load_artifact("https://example.com/corrupt.pdf")

                    assert "%PDF" in result  # Falls back to raw bytes decode


class TestHttpErrors:
    """Tests for HTTP error handling."""

    def test_raises_on_http_error(self):
        """Verify HTTP errors are propagated."""
        from services.nlp.app.text_loader import load_artifact
        import httpx

        err = httpx.HTTPStatusError(
            "404 Not Found", request=MagicMock(), response=MagicMock()
        )
        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream",
                return_value=_StreamCM(
                    _headers("application/pdf", b""), [], raise_exc=err
                ),
            ):
                with pytest.raises(httpx.HTTPStatusError):
                    load_artifact("https://example.com/missing.pdf")

    def test_timeout_handling(self):
        """Verify request timeout is set."""
        from services.nlp.app.text_loader import load_artifact
        import httpx

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch(
                "services.nlp.app.text_loader.httpx.stream"
            ) as mock_stream:
                mock_stream.side_effect = httpx.TimeoutException("Connection timed out")

                with pytest.raises(httpx.TimeoutException):
                    load_artifact("https://slow.example.com/doc.pdf")
