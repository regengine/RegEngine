"""v115 — task_queue idempotency index dedupes tenantless rows (#2852).

Revision ID: c1d4e8f20a37
Revises: d8b2056471a7
Create Date: 2026-08-27

v063 created the enqueue-idempotency index (#1164) as::

    CREATE UNIQUE INDEX idx_task_queue_idempotency
    ON fsma.task_queue (tenant_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL

Under PostgreSQL's default ``NULLS DISTINCT`` semantics two rows whose
``tenant_id`` is NULL never conflict with each other, no matter how equal
their ``idempotency_key`` is. So for tenantless rows the index enforces
nothing and ``ON CONFLICT (tenant_id, idempotency_key) DO NOTHING`` in
``server.workers.task_processor.enqueue_task`` never fires — the INSERT
simply succeeds again and returns a brand new id.

That matters because ``_run_hardened_extraction`` enqueues ``review_item``
rows with ``tenant_id=str(tenant_id) if tenant_id else None`` alongside an
idempotency key (``server/workers/task_processor.py`` line 281-289). When a
document carries no tenant, every re-run of its ``nlp_extraction`` task
appends another copy of the same human-in-the-loop review item, and the
``enqueue_task_idempotent_hit`` log line that would have made the
duplication visible never runs.

Tenanted rows were never affected: a non-NULL ``tenant_id`` compares by
equality, so the index has always deduped the authenticated path correctly.

Fix: recreate the index with ``NULLS NOT DISTINCT`` (PostgreSQL 15+), which
makes two NULL ``tenant_id`` values compare as equal *for this index only*.
The behaviour tenanted rows already had now extends to tenantless ones:

  * ``(NULL, 'review_item:doc1:OBLIGATION:5')`` twice  → one row.
  * ``(NULL, 'review_item:doc1:OBLIGATION:9')``        → still a separate row.
  * ``idempotency_key IS NULL``                        → still unconstrained,
    because the partial predicate excludes those rows entirely. Callers that
    pass no key keep the documented legacy "duplicates are possible" contract.

``enqueue_task``'s existing conflict-recovery SELECT already reads
``tenant_id IS NOT DISTINCT FROM :tenant_id`` — NULL-safe by construction —
so once the index fires, the existing-row lookup and the idempotent-hit log
work for tenantless rows with no change to the query.

The alternative considered was mirroring the guard in
``services/shared/task_queue.py`` line 157 and rejecting a tenantless key
outright. It was rejected here: ``enqueue_task`` wraps its body in
``except Exception: return None``, so raising would convert a duplicated
review item into a *silently dropped* one. Losing a flagged extraction is
strictly worse than showing a reviewer two copies of it.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c1d4e8f20a37"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c4f1a7e93b28"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _require_nulls_not_distinct_support() -> None:
    """Fail loudly on PostgreSQL < 15 rather than silently leaving the bug.

    ``NULLS NOT DISTINCT`` landed in PostgreSQL 15. Every environment in
    this repo pins 17 (``docker-compose.dev.yml``, every ``postgres:17``
    service in ``.github/workflows``), so this is a guard against an
    unexpected target, not an expected branch. Skipping the recreate
    quietly would leave a deployment believing #2852 was fixed when the
    index still ignores tenantless duplicates.
    """
    bind = op.get_bind()
    server_version = bind.exec_driver_sql("SHOW server_version_num").scalar()
    if int(server_version) < 150000:
        raise RuntimeError(
            "v115 requires PostgreSQL 15+ for NULLS NOT DISTINCT "
            f"(server_version_num={server_version}). Upgrade the server, or "
            "adopt a sentinel tenant id for system-scoped tasks instead."
        )


def upgrade() -> None:
    _require_nulls_not_distinct_support()

    # A unique index cannot be built over rows that already violate it, and
    # the whole point of this migration is that such rows were reachable.
    # Collapse any existing tenantless duplicates onto the row the index
    # would have kept — the lowest id, i.e. the one ON CONFLICT DO NOTHING
    # would have preserved had it been able to fire.
    #
    # Scope is deliberately tight: tenantless rows only (tenanted rows have
    # always been unique), and only where a key is actually present, which
    # is the sole set the partial index covers. Rows with no idempotency_key
    # are never touched.
    op.execute(
        """
        DELETE FROM fsma.task_queue AS dup
        USING fsma.task_queue AS keep
        WHERE dup.tenant_id IS NULL
          AND keep.tenant_id IS NULL
          AND dup.idempotency_key IS NOT NULL
          AND keep.idempotency_key IS NOT NULL
          AND dup.idempotency_key = keep.idempotency_key
          AND dup.id > keep.id
        """
    )

    # CREATE ... IF NOT EXISTS would be a no-op against the v063 index, so
    # the old definition has to go first.
    op.execute("DROP INDEX IF EXISTS fsma.idx_task_queue_idempotency")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_task_queue_idempotency
        ON fsma.task_queue (tenant_id, idempotency_key)
        NULLS NOT DISTINCT
        WHERE idempotency_key IS NOT NULL
        """
    )


def downgrade() -> None:
    # Back to v063's NULLS DISTINCT definition. Nothing to clean up: the
    # looser index accepts every row the stricter one did.
    op.execute("DROP INDEX IF EXISTS fsma.idx_task_queue_idempotency")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_task_queue_idempotency
        ON fsma.task_queue (tenant_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )
