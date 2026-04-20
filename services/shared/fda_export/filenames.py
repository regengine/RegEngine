"""Safe filename builders for ``Content-Disposition``.

HTTP attachment responses that interpolate query-string values into
``Content-Disposition: attachment; filename=...`` can be tricked into
either (a) splitting the header with a CRLF pair, creating a second
response header, or (b) dropping a ``/`` or ``\\`` so the browser saves
the file outside the user's download directory on some platforms.

All of the EPIC-L exporters must build their filenames through
:func:`safe_filename` — no raw ``tlc=``, ``start_date=``, or
``filename=`` query value may appear in the header value.

Related issues: #1283, EPIC-L (#1655).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

# Cap per token (e.g. a TLC). Long enough for real FSMA lot codes,
# short enough that stitched filenames stay under typical OS/filesystem
# filename limits once combined with date + timestamp + extension.
MAX_FILENAME_TOKEN = 64

# Whitelist for filename tokens: alphanumerics, dot, underscore, hyphen.
# Anything else is replaced with ``_``. No whitespace, no CRLF, no
# quote, no path separator — all of which are the actual attack surface.
_SAFE_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789"
    "._-"
)


def safe_filename_token(raw: object, *, max_len: int = MAX_FILENAME_TOKEN) -> str:
    """Reduce ``raw`` to an ASCII-only filename token.

    * Non-whitelisted characters become ``_``.
    * ``..`` is collapsed to ``_`` post-substitution to foreclose any
      residual traversal concern.
    * Length capped at ``max_len``.
    * Empty result falls back to ``"all"`` — a filename fragment still
      has to exist for the ``Content-Disposition`` to be well-formed.
    """
    if raw is None:
        return "all"
    s = str(raw)
    cleaned_chars = [c if c in _SAFE_CHARS else "_" for c in s]
    cleaned = "".join(cleaned_chars)[:max_len]
    # Post-strip traversal. A valid token could theoretically contain
    # ``..`` via two adjacent dots — collapse to be safe.
    while ".." in cleaned:
        cleaned = cleaned.replace("..", "_")
    return cleaned or "all"


def _format_date(value: Optional[object]) -> str:
    """Normalize a date-like value into ``YYYY-MM-DD``.

    Accepts ``date``, ``datetime``, or a pre-formatted string. Unknown
    inputs pass through :func:`safe_filename_token`.
    """
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return safe_filename_token(value, max_len=10)


def safe_filename(
    prefix: str,
    *,
    start: Optional[object] = None,
    end: Optional[object] = None,
    scope: Optional[str] = None,
    timestamp: Optional[str] = None,
    extension: str = "csv",
) -> str:
    """Build a safe filename for ``Content-Disposition``.

    The output shape is ``<prefix>[_<scope>][_<start>_<end>][_<ts>].<ext>``.
    Every component is passed through :func:`safe_filename_token`, so
    the returned string is guaranteed to match
    ``[A-Za-z0-9._-]+``.

    Parameters
    ----------
    prefix:
        Required base name (e.g. ``"fda_export"``).
    start, end:
        Optional window bounds. Accept ``date``, ``datetime``, or
        pre-formatted strings.
    scope:
        Optional scope label (e.g. a TLC or ``"all"``).
    timestamp:
        Optional caller-provided UTC timestamp. If omitted, no
        timestamp is appended (callers that need reproducibility pass
        one in; callers that want a fresh one generate it externally).
    extension:
        File extension, without leading dot. Whitespace-stripped and
        token-sanitized.
    """
    parts = [safe_filename_token(prefix)]
    if scope:
        parts.append(safe_filename_token(scope))
    start_s = _format_date(start)
    end_s = _format_date(end)
    if start_s:
        parts.append(safe_filename_token(start_s, max_len=10))
    if end_s:
        parts.append(safe_filename_token(end_s, max_len=10))
    if timestamp:
        parts.append(safe_filename_token(timestamp, max_len=32))
    ext = safe_filename_token(extension.strip(". ") or "csv", max_len=8)
    return "_".join(parts) + "." + ext


__all__ = [
    "MAX_FILENAME_TOKEN",
    "safe_filename",
    "safe_filename_token",
]
