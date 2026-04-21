"""Make review_items.tenant_id NOT NULL (fix #1389)

Before this migration, `review_items.tenant_id` was nullable. The
`list_hallucinations` query only added a tenant filter when the caller
passed a truthy tenant_id, so an API key with `tenant_id IS NULL`
(legacy keys pre-multitenancy) effectively saw every review row
across every tenant -- a read-side cross-tenant leak.

This migration:
  1. Backfills any existing NULL rows to the System Tenant UUID so a
     later re-enable of RLS cannot orphan them.
  2. Sets the column to NOT NULL.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa


revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


_SYSTEM_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # Guard: the migration is idempotent on environments where the
    # table does not exist (e.g., tests that stand up a subset of
    # tables).
    op.execute(
        f"""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'review_items'
                  AND column_name = 'tenant_id'
            ) THEN
                -- Backfill orphaned rows to the System Tenant so that
                -- the NOT NULL constraint can be applied without
                -- surprise violations from pre-multitenancy data.
                EXECUTE $exec$
                    UPDATE review_items
                    SET tenant_id = '{_SYSTEM_TENANT_ID}'::uuid
                    WHERE tenant_id IS NULL
                $exec$;

                -- Now lock down the column.
                EXECUTE 'ALTER TABLE review_items
                         ALTER COLUMN tenant_id SET NOT NULL';
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'review_items'
                  AND column_name = 'tenant_id'
            ) THEN
                EXECUTE 'ALTER TABLE review_items
                         ALTER COLUMN tenant_id DROP NOT NULL';
            END IF;
        END $$
        """
    )
