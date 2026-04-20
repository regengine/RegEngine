"""
Canonical Event Persistence — re-exports from submodules.

Package layout:
    shared/canonical_persistence/models.py          — CanonicalStoreResult
    shared/canonical_persistence/writer.py          — CanonicalEventStore (main class)
    shared/canonical_persistence/schema_bootstrap.py — runtime schema bootstrap (NOT an Alembic migration, see #1293)
    shared/canonical_persistence/legacy_shim.py     — TEMPORARY dual-write + graph sync (was migration.py, see #1293)
"""

from shared.canonical_persistence.models import CanonicalStoreResult  # noqa: F401
from shared.canonical_persistence.writer import CanonicalEventStore  # noqa: F401
from shared.canonical_persistence.schema_bootstrap import bootstrap as bootstrap_schema  # noqa: F401
