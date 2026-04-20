"""CSV formula-injection sanitization (compliance-service shim).

The canonical implementation lives in
``services/shared/fda_export/csv_safety.py`` so both the ingestion and
compliance services share one safe-export surface (EPIC-L, #1655).
This module keeps ``app.csv_safety`` working for existing compliance
callers.
"""
from __future__ import annotations

from shared.fda_export.csv_safety import (
    safe_cell as sanitize_cell,
    safe_sequence as sanitize_sequence,
)

__all__ = ["sanitize_cell", "sanitize_sequence"]
