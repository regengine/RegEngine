import io
import re
import sys
from pathlib import Path

import requests
import structlog

# Add shared module to path for URL validation
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
from shared.url_validation import SSRFError, validate_url

logger = structlog.get_logger("text-loader")

try:
    import pdfminer.high_level as pdfminer
except ImportError:  # optional dependency
    pdfminer = None


def load_artifact(url_or_s3: str) -> str:
    """
    Load artifact content and return best-effort plain text.
    For demo, supports http(s) URLs; extend to S3 by replacing with boto3 fetch.

    Raises:
        SSRFError: If URL fails SSRF validation
        ValueError: If URL scheme is not supported
    """
    # Simple URL check; replace with S3 handling if needed
    if not re.match(r"^https?://", url_or_s3):
        raise ValueError("Only http(s) URLs supported in demo loader")

    # Validate URL against SSRF attacks
    validate_url(url_or_s3)

    resp = requests.get(url_or_s3, timeout=20)
    resp.raise_for_status()
    ctype = resp.headers.get("Content-Type", "application/octet-stream")
    data = resp.content

    if "pdf" in ctype and pdfminer:
        with io.BytesIO(data) as bio:
            try:
                return pdfminer.extract_text(bio) or ""
            except Exception:
                pass
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
        text_extractor.feed(data.decode(errors="ignore"))
        # Basic markdown-ish conversion: join text blocks and collapse whitespace
        text = "\n\n".join([s.strip() for s in text_extractor.parts if s.strip()])
        logger.info("html_to_text", bytes=len(data), chars=len(text))
        return text

    # Fallback to bytes decode
    text = data.decode(errors="ignore")
    logger.info("bytes_to_text", bytes=len(data), chars=len(text), content_type=ctype)
    return text
