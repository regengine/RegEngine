"""
Backward-compatibility shim — re-exports from schema_bootstrap.

NOT an Alembic migration — bootstraps schema if absent. Use Alembic for
versioned migrations.

This file is retained so that existing callers (writer.py, tests, docs) that
import ``shared.canonical_persistence.migration`` continue to work. New code
should import from ``shared.canonical_persistence.schema_bootstrap`` directly.
"""

import warnings

warnings.warn(
    "Importing from 'shared.canonical_persistence.migration' is deprecated. "
    "This module is NOT an Alembic migration — it bootstraps schema if absent. "
    "Use 'shared.canonical_persistence.schema_bootstrap' for direct imports, "
    "and Alembic for versioned migrations.",
    DeprecationWarning,
    stacklevel=2,
)

from shared.canonical_persistence.schema_bootstrap import (  # noqa: F401
    dual_write_legacy,
    publish_graph_sync,
    stage_graph_sync,
    _drain_pending_graph_sync,
    _clear_pending_graph_sync,
    _clear_pending_graph_sync_soft,
    _neo4j_sync_enabled,
    _neo4j_sync_max_queue,
    _NEO4J_SYNC_QUEUE_KEY,
    _SESSION_PENDING_KEY,
    _SESSION_HOOKS_INSTALLED_KEY,
)
