"""v081 -- index cte_events on (tenant_id, sha256_hash).

Revision ID: a7b8c9d0e1f2
Revises: d2e3f4a5b6c7
Create Date: 2026-06-12

The append-only duplicate check ``_assert_not_exists`` runs on every single
and batch CTE write:

    SELECT id FROM fsma.cte_events
    WHERE sha256_hash = :sha AND tenant_id = :tid LIMIT 1

Only ``tenant_id`` is indexed, so this scans the whole tenant partition on the
hot ingestion path and gets linearly slower as a tenant accumulates events.
Add a composite ``(tenant_id, sha256_hash)`` index to make the lookup a point
probe.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a7b8c9d0e1f2"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UPGRADE_SQL = """
CREATE INDEX IF NOT EXISTS idx_cte_events_tenant_sha256
    ON fsma.cte_events (tenant_id, sha256_hash);
"""

_DOWNGRADE_SQL = """
DROP INDEX IF EXISTS fsma.idx_cte_events_tenant_sha256;
"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
