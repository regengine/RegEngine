"""v093 — ORM↔schema drift forward-ports surfaced by the WS-2b gate.

When `alembic check` was first pointed at every ORM Base (WS-2b), three
pieces of real structural drift surfaced. Each one is a model that the
code already relies on but that no migration ever created — the exact
"autogenerate sees only admin's Base" failure mode the remediation plan
called out:

1. ``scheduler_seen_items`` (services/scheduler/app/state.py) existed
   only via a runtime ``Base.metadata.create_all`` in StateManager —
   deployments that never booted the standalone scheduler lack the
   table entirely.
2. ``ix_api_keys_tenant_id`` — the ORM declares ``index=True`` on
   ``api_keys.tenant_id`` (every tenant-scoped key lookup filters on
   it), but v076 created the table without the index.
3. ``tenants.slug`` is ``nullable=False`` in the ORM but nullable in
   the database. Backfilled from ``id`` before tightening so the ALTER
   cannot fail on legacy rows.

All operations are idempotent (IF NOT EXISTS / guarded) — environments
where the scheduler's create_all already made the table converge to the
same state.

Revision ID: 16cb29a3938c (random hex, not a credential)
Revises: b3c8e1f4a627
Create Date: 2026-07-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "16cb29a3938c"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "b3c8e1f4a627"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. scheduler_seen_items — mirror services/scheduler/app/state.py
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduler_seen_items (
            source_id VARCHAR(255) PRIMARY KEY,
            source_type VARCHAR(100) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            title TEXT,
            url TEXT,
            first_seen_at TIMESTAMPTZ NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL
        )
        """
    )

    # 2. api_keys.tenant_id index — ORM declares index=True (tenant-scoped
    #    key lookups filter on it); v076 never created it.
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_keys_tenant_id ON api_keys (tenant_id)")

    # 3. tenants.slug NOT NULL — backfill any legacy NULL slugs from the
    #    tenant id first so the constraint cannot fail mid-deploy.  The
    #    migration credential is NOBYPASSRLS and tenants is already FORCE-RLS,
    #    so restore owner access only for this transactional repair.
    op.execute("ALTER TABLE tenants NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE tenants SET slug = 'tenant-' || id::text WHERE slug IS NULL")
    op.execute("ALTER TABLE tenants ALTER COLUMN slug SET NOT NULL")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE tenants ALTER COLUMN slug DROP NOT NULL")
    op.execute("DROP INDEX IF EXISTS ix_api_keys_tenant_id")
    op.execute("DROP TABLE IF EXISTS scheduler_seen_items")
