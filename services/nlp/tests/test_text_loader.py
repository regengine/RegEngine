"""Tests for NLP text_loader module.

Covers:
- URL validation and SSRF protection
- PDF text extraction
- HTML to text conversion
- Fallback text decoding
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import io

import pytest


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

        with patch("services.nlp.app.text_loader.validate_url") as mock_validate:
            with patch("services.nlp.app.text_loader.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.content = b"Sample text content"
                mock_response.headers = {"Content-Type": "text/plain"}
                mock_get.return_value = mock_response

                result = load_artifact("http://example.com/doc.txt")

                assert result == "Sample text content"
                mock_validate.assert_called_once_with("http://example.com/doc.txt")

    def test_accepts_https_url(self):
        """Verify https URLs are accepted."""
        from services.nlp.app.text_loader import load_artifact

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch("services.nlp.app.text_loader.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.content = b"Secure content"
                mock_response.headers = {"Content-Type": "text/plain"}
                mock_get.return_value = mock_response

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
            with patch("services.nlp.app.text_loader.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.content = html_content
                mock_response.headers = {"Content-Type": "text/html"}
                mock_get.return_value = mock_response

                result = load_artifact("https://example.com/page.html")

                assert "Header" in result
                assert "Paragraph text here" in result

    def test_handles_utf8_content(self):
        """Verify UTF-8 encoded content is handled."""
        from services.nlp.app.text_loader import load_artifact

        utf8_content = "Unicode: café, naïve, 日本語".encode("utf-8")

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch("services.nlp.app.text_loader.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.content = utf8_content
                mock_response.headers = {"Content-Type": "text/plain; charset=utf-8"}
                mock_get.return_value = mock_response

                result = load_artifact("https://example.com/utf8.txt")

                assert "café" in result
                assert "日本語" in result

    def test_handles_binary_fallback(self):
        """Verify binary content falls back to decode with errors=ignore."""
        from services.nlp.app.text_loader import load_artifact

        # Content with invalid UTF-8 bytes
        binary_content = b"Valid text \xff\xfe invalid bytes"

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch("services.nlp.app.text_loader.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.content = binary_content
                mock_response.headers = {"Content-Type": "application/octet-stream"}
                mock_get.return_value = mock_response

                result = load_artifact("https://example.com/binary.bin")

                # Should not raise, invalid bytes are ignored
                assert "Valid text" in result


class TestPdfExtraction:
    """Tests for PDF text extraction."""

    def test_pdf_extraction_with_pdfminer(self):
        """Verify PDF content is extracted using pdfminer."""
        from services.nlp.app.text_loader import load_artifact

        pdf_content = b"%PDF-1.4 fake pdf content"

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch("services.nlp.app.text_loader.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.content = pdf_content
                mock_response.headers = {"Content-Type": "application/pdf"}
                mock_get.return_value = mock_response

                with patch("services.nlp.app.text_loader.pdfminer") as mock_pdfminer:
                    mock_pdfminer.extract_text.return_value = "Extracted PDF text"

                    result = load_artifact("https://example.com/doc.pdf")

                    assert result == "Extracted PDF text"

    def test_pdf_extraction_fallback_on_error(self):
        """Verify fallback when pdfminer fails."""
        from services.nlp.app.text_loader import load_artifact

        pdf_content = b"%PDF-1.4 corrupted pdf"

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch("services.nlp.app.text_loader.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.content = pdf_content
                mock_response.headers = {"Content-Type": "application/pdf"}
                mock_get.return_value = mock_response

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

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch("services.nlp.app.text_loader.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "404 Not Found", request=MagicMock(), response=MagicMock()
                )
                mock_get.return_value = mock_response

                with pytest.raises(httpx.HTTPStatusError):
                    load_artifact("https://example.com/missing.pdf")

    def test_timeout_handling(self):
        """Verify request timeout is set."""
        from services.nlp.app.text_loader import load_artifact
        import httpx

        with patch("services.nlp.app.text_loader.validate_url"):
            with patch("services.nlp.app.text_loader.httpx.get") as mock_get:
                mock_get.side_effect = httpx.TimeoutException("Connection timed out")

                with pytest.raises(httpx.TimeoutException):
                    load_artifact("https://slow.example.com/doc.pdf")
