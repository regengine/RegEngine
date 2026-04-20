"""
Backward-compatibility shim — re-exports from schema_bootstrap.

This file is retained so that existing callers (writer.py, tests, docs) that
import ``shared.canonical_persistence.migration`` continue to work. New code
should import from ``shared.canonical_persistence.schema_bootstrap`` directly.

NOT an Alembic migration. Bootstraps schema if tables absent. Use Alembic for
versioned migrations.
"""

from shared.canonical_persistence.schema_bootstrap import (  # noqa: F401
    dual_write_legacy,
    publish_graph_sync,
    stage_graph_sync,
)
