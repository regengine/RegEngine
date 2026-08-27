"""Single source of truth for ``fsma.task_queue`` task-type classification (#2903).

``fsma.task_queue`` is shared by two populations of rows with
irreconcilable lifecycles:

* **worker rows** — real background work, claimed by
  ``server/workers/task_processor.py`` / ``shared.task_queue.TaskWorker``,
  and garbage once terminal;
* **evidence rows** — records that merely *live* in the queue table
  because it was convenient. ``recall_drill`` (and the future ``recall``
  state-machine row) are parked at ``status='completed'`` by
  ``services/graph/app/fsma_recall/persistence.py`` precisely so the
  worker skips them (#1199). ``fsma.task_queue`` is their **only**
  persistent store.

#2903: those two readings of the ``status`` column collided.  The
scheduler's 30-day retention purge treated ``status IN ('completed',
'dead')`` as the definition of garbage and deleted with no ``task_type``
predicate, so it destroyed FSMA 204 mock-recall evidence — the exact
artifact an FDA 24-hour traceability request asks for — silently and
unrecoverably (hard DELETE, no archive table, no audit trigger).

The classification lives *here*, in one module, imported by both the
worker and the purge, so the two can never drift apart again.

Fail-closed by design
---------------------
:data:`PURGEABLE_TASK_TYPES` is a **positive allowlist**, not a denylist.
A task type nobody has classified is RETAINED, not deleted — so the next
module that parks evidence in ``fsma.task_queue`` is safe on day one
without its author ever learning that this purge exists.
:data:`NON_WORKER_TASK_TYPES` is kept as a second, independent reason
those rows survive: a careless edit to the allowlist alone cannot
re-expose them.
"""

from __future__ import annotations

from typing import FrozenSet, List

__all__ = [
    "NON_WORKER_TASK_TYPES",
    "PURGEABLE_TASK_TYPES",
    "is_purgeable",
    "protected_task_types",
    "purgeable_task_types",
]


# Task types that share fsma.task_queue but are NOT background work.
# The worker must never claim them (#1199) and retention must never
# delete them (#2903).  Every entry here is compliance evidence with no
# other store; adding one is a records-retention decision.
NON_WORKER_TASK_TYPES: FrozenSet[str] = frozenset(
    {
        "recall_drill",  # #1199 — FSMA 204 mock-recall drill history
        "recall",  # #1199 — recall state machine rows (future)
    }
)


# Explicit ALLOWLIST of task types the 30-day retention purge (#1382) may
# delete.  Every entry is genuine background work whose row carries no
# evidentiary value once terminal.
#
# Sources, kept deliberately explicit rather than derived from a live
# registry (an unpopulated registry would silently disable retention):
#   server/workers/task_processor.TASK_HANDLERS
#   server/main.py::_ingestion_task_types (register_*_handlers)
#   shared.agent_task_bridge.AGENT_ARTIFACT_TASK_TYPE
PURGEABLE_TASK_TYPES: FrozenSet[str] = frozenset(
    {
        # server/workers/task_processor.py
        "nlp_extraction",
        "graph_update",
        "review_item",
        # services/ingestion/app/task_handlers_sources.py
        "federal_register_ingest",
        "ecfr_ingest",
        "fda_ingest",
        # services/ingestion/app/task_handlers_scraping.py
        "state_scrape",
        "generic_scrape",
        # services/ingestion/app/task_handlers_discovery.py
        "discovery_scrape",
        # services/ingestion/app/task_handlers_regulation.py
        "regulation_ingest",
        # services/shared/agent_task_bridge.py
        "agent_artifact_review",
    }
)


# Import-time invariant: a type may never be both purgeable and protected.
# Failing here is loud and immediate; the alternative is a silent deletion
# of evidence months later.
_CONFLICTS = PURGEABLE_TASK_TYPES & NON_WORKER_TASK_TYPES
if _CONFLICTS:  # pragma: no cover — guards an edit, not a runtime path
    raise RuntimeError(
        "shared.task_types: task types classified as both purgeable and "
        f"non-worker/evidence: {sorted(_CONFLICTS)}. Retention would delete "
        "compliance evidence; resolve the classification before shipping."
    )


def purgeable_task_types() -> List[str]:
    """Sorted allowlist, shaped for binding into a SQL ``= ANY(:param)``."""
    return sorted(PURGEABLE_TASK_TYPES)


def protected_task_types() -> List[str]:
    """Sorted denylist, shaped for binding into a SQL ``!= ALL(:param)``."""
    return sorted(NON_WORKER_TASK_TYPES)


def is_purgeable(task_type: str) -> bool:
    """True only for a task type explicitly classified as disposable.

    Unknown types return False — retention fails closed.
    """
    if not task_type:
        return False
    return task_type in PURGEABLE_TASK_TYPES and task_type not in NON_WORKER_TASK_TYPES
