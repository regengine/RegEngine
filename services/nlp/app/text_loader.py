import io
import os
import re
import sys
from pathlib import Path

import httpx
import structlog

# Import shared utilities
from shared.url_validation import SSRFError, validate_url

logger = structlog.get_logger("text-loader")

try:
    import pdfminer.high_level as pdfminer
except ImportError:  # optional dependency
    pdfminer = None

# Hard limits on fetched artifacts (see issue #1120).
# These cap network-loaded content to prevent DoS (multi-GB payloads) and
# silent corruption from decoding arbitrary binary blobs as text.
MAX_DOC_BYTES = int(os.getenv("NLP_MAX_DOC_BYTES", "25000000"))  # 25 MB
MAX_PDF_PAGES = int(os.getenv("NLP_MAX_PDF_PAGES", "500"))
ALLOWED_MIMES = frozenset(
    {
        "application/pdf",
        "text/plain",
        "text/html",
        "text/csv",
        "application/xml",
        "text/xml",
        "application/json",
    }
)


def load_artifact(url_or_s3: str) -> str:
    """
    Load artifact content and return best-effort plain text.
    For demo, supports http(s) URLs; extend to S3 by replacing with boto3 fetch.

    Enforces size (``MAX_DOC_BYTES``) and MIME (``ALLOWED_MIMES``) limits to
    prevent DoS via oversized payloads and silent corruption from arbitrary
    binary inputs. Decoding uses ``errors="strict"`` so malformed UTF-8 raises
    rather than getting silently dropped (which could mutilate TLCs and other
    identifiers).

    Raises:
        SSRFError: If URL fails SSRF validation
        ValueError: If URL scheme is not supported, the declared or streamed
            body exceeds ``MAX_DOC_BYTES``, the Content-Type is not in
            ``ALLOWED_MIMES``, or the body is not valid UTF-8.
    """
    # Simple URL check; replace with S3 handling if needed
    if not re.match(r"^https?://", url_or_s3):
        raise ValueError("Only http(s) URLs supported in demo loader")

    # Validate URL against SSRF attacks
    validate_url(url_or_s3)

    # Stream the response so we can enforce size caps before buffering
    # the full body in memory. An attacker could advertise a small
    # Content-Length and then stream indefinitely -- we guard both paths.
    with httpx.stream("GET", url_or_s3, timeout=20) as resp:
        resp.raise_for_status()

        declared = int(resp.headers.get("Content-Length") or 0)
        if declared > MAX_DOC_BYTES:
            raise ValueError(
                "E_DOC_TOO_LARGE: Content-Length exceeds cap"
            )

        ctype_full = resp.headers.get("Content-Type", "application/octet-stream")
        ctype = ctype_full.split(";")[0].strip().lower()
        if ctype and ctype not in ALLOWED_MIMES:
            raise ValueError(f"E_DOC_MIME_DISALLOWED: {ctype}")

        chunks = []
        total = 0
        for chunk in resp.iter_bytes():
            total += len(chunk)
            if total > MAX_DOC_BYTES:
                raise ValueError(
                    "E_DOC_TOO_LARGE: streamed bytes exceed cap"
                )
            chunks.append(chunk)
        data = b"".join(chunks)

    if "pdf" in ctype and pdfminer:
        with io.BytesIO(data) as bio:
            try:
                # Cap pages parsed to bound pdfminer CPU/memory on
                # adversarial PDFs (nested objects, XFA, etc.).
                return pdfminer.extract_text(bio, maxpages=MAX_PDF_PAGES) or ""
            except Exception:
                logger.debug("pdf_text_extraction_failed", exc_info=True)
    if "text/html" in ctype:
        # naive HTML to text
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []

            def handle_data(self, data):
                self.parts.append(data)

        text_extractor = TextExtractor()
        try:
            decoded = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("E_DOC_DECODE_FAILED") from exc
        text_extractor.feed(decoded)
        # Basic markdown-ish conversion: join text blocks and collapse whitespace
        text = "\n\n".join([s.strip() for s in text_extractor.parts if s.strip()])
        logger.info("html_to_text", bytes=len(data), chars=len(text))
        return text

    # Fallback to bytes decode -- fail loudly on malformed UTF-8 rather than
    # silently dropping bytes (which corrupts TLCs/lot codes downstream).
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("E_DOC_DECODE_FAILED") from exc
    logger.info("bytes_to_text", bytes=len(data), chars=len(text), content_type=ctype)
    return text
