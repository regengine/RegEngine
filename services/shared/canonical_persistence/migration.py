"""
DEPRECATED: This module has been renamed to ``legacy_dual_write``.

Import ``shared.canonical_persistence.legacy_dual_write`` instead.
This shim exists only for backward compatibility and will be removed once
all callers are updated.

Tracked: https://github.com/PetrefiedThunder/RegEngine/issues/1293
"""
# Re-export everything from the canonical location so existing imports keep
# working without any change.
from shared.canonical_persistence.legacy_dual_write import (  # noqa: F401
    validate_tables_exist,
    dual_write_legacy,
    publish_graph_sync,
    stage_graph_sync,
    _neo4j_sync_enabled,
    _neo4j_sync_max_queue,
    _drain_pending_graph_sync,
    _clear_pending_graph_sync,
    _clear_pending_graph_sync_soft,
    _NEO4J_SYNC_QUEUE_KEY,
    _SESSION_PENDING_KEY,
    _SESSION_HOOKS_INSTALLED_KEY,
)

import warnings as _warnings
_warnings.warn(
    "shared.canonical_persistence.migration is deprecated — "
    "import from shared.canonical_persistence.legacy_dual_write instead. "
    "See https://github.com/PetrefiedThunder/RegEngine/issues/1293",
    DeprecationWarning,
    stacklevel=2,
)
