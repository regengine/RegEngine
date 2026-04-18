"""
CSV formula-injection sanitization (compliance service copy).

Parallel module to ``services/ingestion/app/shared/csv_safety.py``.
Duplicated here so the compliance service has a local, import-stable
helper without cross-service coupling.

See the ingestion-side copy for full rationale. Summary: any cell text
starting with ``=``, ``+``, ``-``, ``@``, ``\\t``, or ``\\r`` is treated
as a formula when the CSV is opened in Excel / LibreOffice / Sheets and
executes on the *recipient's* machine.

Related issue: #1272 (compliance-service ``fsma_spreadsheet.py``
codepath, distinct from ingestion-side #1081).
"""

from __future__ import annotations

_DANGEROUS_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell(value: object) -> str:
    """Neutralize CSV formula-injection by prefixing dangerous values.

    Converts ``value`` to a string and prepends a literal single quote
    ``'`` when the string starts with any of the standard formula
    prefixes.

    ``None`` renders as ``""``. Everything else is ``str()``-coerced.
    """
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _DANGEROUS_PREFIXES:
        return "'" + s
    return s


def sanitize_sequence(seq) -> list[str]:
    """Apply :func:`sanitize_cell` to every value in a list/tuple row."""
    return [sanitize_cell(v) for v in seq]


__all__ = ["sanitize_cell", "sanitize_sequence"]
