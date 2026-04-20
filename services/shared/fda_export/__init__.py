"""Shared FDA / FSMA-204 CSV export primitives.

One module, two services: the ingestion service's ``fda_export_service``
and the compliance service's ``fsma_spreadsheet`` both produce
auditor-facing spreadsheets. Before EPIC-L they each carried their own
(diverging) copies of: formula-prefix escaping, filename sanitization,
date-window validation, PII redaction, and pagination. Two
implementations of the same safety net is one too many — a fix landed
in one service would miss the other (issue #1081 vs #1272 is the
canonical example).

This package is the single safe-export surface. Both services import
from here; nothing under ``services/ingestion/app/`` or
``services/compliance/app/`` is allowed to open a file and write a CSV
row that didn't first pass through :func:`safe_cell`.

See ``docs/audits/GH_ISSUES_CONSOLIDATION_2026_04_17.md`` §2 EPIC-L
for the consolidated plan this package implements.
"""
from __future__ import annotations

from .csv_safety import (
    DANGEROUS_PREFIXES,
    safe_cell,
    safe_row,
    safe_sequence,
)
from .filenames import (
    MAX_FILENAME_TOKEN,
    safe_filename,
    safe_filename_token,
)
from .pagination import paginate
from .pii import (
    PII_PERMISSION,
    PII_REDACTION_PLACEHOLDER,
    hash_pii_value,
    redact_pii_row,
)
from .windows import (
    MAX_EXPORT_WINDOW_DAYS,
    ExportWindow,
    ExportWindowError,
    validate_export_window,
)

__all__ = [
    "DANGEROUS_PREFIXES",
    "ExportWindow",
    "ExportWindowError",
    "MAX_EXPORT_WINDOW_DAYS",
    "MAX_FILENAME_TOKEN",
    "PII_PERMISSION",
    "PII_REDACTION_PLACEHOLDER",
    "hash_pii_value",
    "paginate",
    "redact_pii_row",
    "safe_cell",
    "safe_filename",
    "safe_filename_token",
    "safe_row",
    "safe_sequence",
    "validate_export_window",
]
