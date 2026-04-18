"""
Source-text sanitization helpers for review items.

Issue #1390: ``source_text`` in review items originates from
user-uploaded PDFs/Excel/OCR -- untrusted document content. If a
reviewer UI renders this with ``dangerouslySetInnerHTML`` or a
permissive Markdown renderer, an attacker can smuggle ``<script>``
payloads into the admin UI via a malicious supplier document.

Strategy:
- Store the raw text verbatim in the DB (so downstream analytics /
  model training / audit exports can access the original). The raw
  field is never returned to the client directly.
- On API response, HTML-escape and strip anything that parses as an
  HTML tag. We purposefully do NOT use ``bleach`` (optional
  dependency) so that this ships without a new requirement -- the
  escaping strategy used here is the one in the Python stdlib.

If ``bleach`` is available in the environment, we fall through to it
for defense-in-depth (attribute-level stripping), but it is optional.
"""

from __future__ import annotations

import html
import re
from typing import Any, Optional

try:  # pragma: no cover -- optional dependency
    import bleach as _bleach  # type: ignore

    _BLEACH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _bleach = None  # type: ignore
    _BLEACH_AVAILABLE = False


# Strip entire <script>...</script> and <style>...</style> blocks even
# when the closing tag is broken -- this is belt-and-braces after the
# html.escape() pass already turns < and > into &lt;/&gt;. Included so
# that if escape() is ever swapped for a lenient variant, the XSS path
# does not silently reopen.
_SCRIPT_TAG_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_ANY_TAG_RE = re.compile(r"<[^>]*>")

# Event handler and javascript: URI patterns that escape() does not
# neutralize when the surrounding markup has already been rendered
# before sanitization runs (belt-and-braces again).
_JS_URI_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


def sanitize_source_text_for_store(value: Optional[str]) -> str:
    """Sanitize user-supplied document text before DB store.

    Escapes HTML-special characters and removes tag-like structures.
    Preserves line breaks and whitespace so that the downstream review
    UI can still show the extracted text faithfully.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    # Strip dangerous container tags entirely (script/style/iframe/object/embed).
    cleaned = _SCRIPT_TAG_RE.sub("", value)
    # Remove any remaining tag-like tokens.
    cleaned = _ANY_TAG_RE.sub("", cleaned)
    # Neutralize javascript: URIs.
    cleaned = _JS_URI_RE.sub("", cleaned)
    # HTML-escape the remaining text. quote=True escapes both " and '.
    cleaned = html.escape(cleaned, quote=True)

    if _BLEACH_AVAILABLE:
        # Strip allows no tags and no attributes -- defense in depth.
        cleaned = _bleach.clean(cleaned, tags=[], attributes={}, strip=True)

    return cleaned


def sanitize_source_text_for_response(value: Any) -> str:
    """Sanitize source text at the API boundary before returning to clients.

    Re-sanitizes on read even if data was stored before the write-time
    sanitization was added. Callers should pass the raw ``text_raw``
    field from the DB row.
    """
    if value is None:
        return ""
    return sanitize_source_text_for_store(str(value))


__all__ = [
    "sanitize_source_text_for_store",
    "sanitize_source_text_for_response",
]
