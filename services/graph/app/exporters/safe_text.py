"""Per-format escape helpers for graph-service exports.

Each helper closes one injection class:

* :func:`xml_escape`        — XML attribute/CDATA content
* :func:`csv_safe`          — Excel formula-prefix neutralization
* :func:`header_filename`   — HTTP ``Content-Disposition`` filename param
* :func:`rfc5987_filename`  — RFC 5987 ``filename*`` for non-ASCII names
* :func:`zpl_safe`          — Zebra ZPL caret-command stripping

Route every export through these helpers; do NOT build structured text via
f-string concatenation directly in router files.

Background: a defensive audit (RE-SEC-001/002/003/004) found that
``services/graph`` exports interpolated tenant-controlled strings into XML,
CSV, HTTP headers, and ZPL command streams with no per-format escaping. Any
operator with write access to a tenant could corrupt FSMA 204 artifacts that
go to FDA / Walmart / Kroger / Sysco or persistently reprogram shared label
printers. These helpers — used at every export boundary — close that class.
"""

from __future__ import annotations

import html
import urllib.parse
from typing import Any

# ---------------------------------------------------------------------------
# XML
# ---------------------------------------------------------------------------

def xml_escape(text: Any) -> str:
    """Escape ``& < > " '`` for safe XML CDATA / attribute content.

    Returns ``''`` for ``None``.

    NOTE: Prefer a structural XML builder for new code. This helper exists
    only for legacy string-concat builders that are too tangled to migrate
    in one PR.
    """
    if text is None:
        return ""
    s = str(text)
    return html.escape(s, quote=True)


# ---------------------------------------------------------------------------
# CSV (Excel formula-prefix neutralization)
# ---------------------------------------------------------------------------

# Characters Excel/LibreOffice/Numbers treat as a formula trigger when they
# appear at the start of a cell. ``\t`` and ``\r`` matter because Excel will
# strip them and re-evaluate the next char.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: Any) -> str:
    """Neutralize Excel formula prefixes by prepending a single quote.

    Returns ``''`` for ``None``. The caller MUST still pass the result
    through ``csv.writer`` or equivalent so embedded commas / quotes /
    newlines are properly quoted at the CSV layer.
    """
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _CSV_FORMULA_PREFIXES:
        return "'" + s
    return s


# ---------------------------------------------------------------------------
# HTTP Content-Disposition filename
# ---------------------------------------------------------------------------

# urllib.parse.quote will percent-encode anything outside ``safe``. Newlines,
# CR, and ``"`` are stripped explicitly first as defense-in-depth even though
# Starlette/h11 reject CR/LF in headers.
_FILENAME_STRIP = ("\r", "\n", "\x00", '"', "\\")


def header_filename(name: str, max_len: int = 200) -> str:
    """Encode a filename for use in a ``Content-Disposition`` header.

    Strips control chars, restricts to a safe ASCII charset via percent
    encoding, and truncates to ``max_len``. Suitable for use as::

        f'attachment; filename={header_filename(name)}'

    For non-ASCII names, prefer :func:`rfc5987_filename`.
    """
    if not name:
        return "download"
    s = str(name)
    for ch in _FILENAME_STRIP:
        s = s.replace(ch, "")
    # Strip any remaining control bytes (0x00-0x1f, 0x7f).
    s = "".join(c for c in s if 0x20 <= ord(c) < 0x7F)
    if not s:
        return "download"
    encoded = urllib.parse.quote(s, safe="._-")
    return encoded[:max_len] or "download"


def rfc5987_filename(name: str) -> str:
    """Return an RFC 5987 ``filename*=UTF-8''<percent-encoded>`` value.

    Use as::

        f"attachment; filename*=UTF-8''{rfc5987_filename(name)}"
    """
    if not name:
        return ""
    s = str(name)
    for ch in _FILENAME_STRIP:
        s = s.replace(ch, "")
    s = "".join(c for c in s if ord(c) >= 0x20 and ord(c) != 0x7F)
    return urllib.parse.quote(s.encode("utf-8"), safe="")


# ---------------------------------------------------------------------------
# ZPL (Zebra Programming Language)
# ---------------------------------------------------------------------------

# Caret (^) and tilde (~) are ZPL command prefixes. Any control byte can
# mis-frame the printer's parser. Strip all of them before interpolating
# user input into a ZPL command stream.
_ZPL_STRIP_TABLE = str.maketrans(
    "",
    "",
    "^~" + "".join(chr(c) for c in range(0x20)) + "\x7f",
)


def zpl_safe(text: Any, max_len: int = 30) -> str:
    """Strip ZPL command-prefix chars (``^``, ``~``) and control bytes.

    Returns ``''`` for ``None``. Truncates to ``max_len`` AFTER stripping,
    so an attacker cannot smuggle a leading ``^XZ`` past the truncation
    that earlier code (``desc[:30]``) relied on as its only defense.
    """
    if text is None:
        return ""
    s = str(text).translate(_ZPL_STRIP_TABLE)
    return s[:max_len]
