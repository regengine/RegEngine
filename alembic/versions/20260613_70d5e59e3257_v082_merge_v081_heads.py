"""v082 -- merge the two v081 heads into a single revision DAG head.

Revision ID: 70d5e59e3257
Revises: 3e7a1c5b9f24, a7b8c9d0e1f2
Create Date: 2026-06-13

#2447 (v081 fsma RLS coverage repair, 3e7a1c5b9f24) and #2450 (v081
cte_events sha256 index, a7b8c9d0e1f2) both branched from v080
(d2e3f4a5b6c7) and merged to main independently, leaving the revision
DAG with two heads. The "Alembic revision ID guard" CI job fails on
every PR until the DAG has exactly one head.

This is a NO-OP merge revision (the standard ``alembic merge`` shape):
both parents are kept as-is, so databases that already applied one or
both heads upgrade cleanly to this single head. Do NOT repair this by
rewriting either parent's ``down_revision`` -- production deploys run
on every main merge, so the parallel rows may already be recorded in
``alembic_version``, and rebasing an applied revision corrupts that
state (see docs/abandoned_migrations_20260420_incident/).
"""

from typing import Sequence, Union

revision: str = "70d5e59e3257"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "3e7a1c5b9f24",  # pragma: allowlist secret
    "a7b8c9d0e1f2",  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op -- DAG merge only."""
    pass


def downgrade() -> None:
    """No-op -- DAG merge only."""
    pass
