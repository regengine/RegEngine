"""
Canonical Event Persistence — re-exports from submodules.

Package layout:
    shared/canonical_persistence/models.py     — CanonicalStoreResult
    shared/canonical_persistence/writer.py     — CanonicalEventStore (main class)
    shared/canonical_persistence/legacy_dual_write.py — TEMPORARY dual-write + graph sync
"""

from shared.canonical_persistence.models import CanonicalStoreResult  # noqa: F401
from shared.canonical_persistence.writer import CanonicalEventStore  # noqa: F401
