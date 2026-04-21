"""Consolidated v059 head -- post-incident graph repair 2026-04-20.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-20

INCIDENT CONTEXT
----------------
Prior to this consolidation the alembic revision graph was corrupt:

  * Five distinct files all claimed revision = "f5a6b7c8d9e0"
    (the v059 series from 2026-04-17).
  * Two files claimed revision = "a1b2c3d4e5f6"
    (v043_v047 and v073_dlq_replay_columns_1192).
  * Two files claimed revision = "a7b8c9d0e1f2"
    (graph_outbox_v060 and v061_task_queue_rls_fail_closed).
  * Two files claimed revision = "b4c5d6e7f8a9"
    (v068_identity_review_reopen and v068_transformation_links).
  * One file (v073_cte_events_append_only_trigger) used legacy-style
    revision = "v073" / down_revision = "v072", but no "v072" revision
    exists -- an orphan pointer that broke alembic's revision map on
    startup with KeyError: 'v072'.

This caused every Railway deploy to fail: migrations could not run,
the healthcheck never came up, and the old 3-day-old container stayed
serving traffic.

REPAIR
------
Prod's alembic_version was stamped at "f5a6b7c8d9e0". All 21 broken
files (five v059 duplicates + 16 downstream v060-v073 files) have been
moved to docs/abandoned_migrations_20260420_incident/ for audit. The
ops they would have performed are forward-ported piecemeal in
follow-up PRs, verified one at a time.

This migration is a NO-OP: it exists only so the revision graph has a
single head matching prod's stamp. `alembic upgrade head` on prod is
therefore a no-op and deploys become green again.
"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op -- graph repair only."""
    pass


def downgrade() -> None:
    """No-op -- graph repair only."""
    pass
