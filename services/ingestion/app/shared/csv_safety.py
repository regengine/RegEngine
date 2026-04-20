"""CSV formula-injection sanitization (ingestion-service shim).

The canonical implementation lives in
``services/shared/fda_export/csv_safety.py`` so that both the ingestion
and compliance services share one safe-export surface (EPIC-L, #1655).

This module exists to keep the existing ``app.shared.csv_safety``
import path working for ingestion-service callers during the rollout.
New code should import from :mod:`shared.fda_export`.
"""
from __future__ import annotations

from shared.fda_export.csv_safety import (
    DANGEROUS_PREFIXES as _DANGEROUS_PREFIXES,
    safe_cell as sanitize_cell,
    safe_row as sanitize_row,
    safe_sequence as sanitize_sequence,
)

__all__ = ["sanitize_cell", "sanitize_row", "sanitize_sequence"]
