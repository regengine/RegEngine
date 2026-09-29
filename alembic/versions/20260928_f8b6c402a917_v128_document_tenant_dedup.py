"""Scope ingestion document content uniqueness to its owning tenant.

The new targetless ON CONFLICT code supports either schema, but cross-tenant
identical content remains unavailable until this migration is applied. Deploy
the compatible code before the schema change, or pause generic ingestion for
the coordinated rollout: old code's global conflict target is invalid after
this migration. No row, identity, stored URI, grant, or RLS policy is rewritten.

Downgrade restores global uniqueness only when the existing data permits it.
If tenants now own the same content hash, PostgreSQL refuses the unique
constraint and rolls back the ALTER atomically. Never delete evidence to make
that downgrade succeed; keep the tenant-scoped schema and compatible code.

Revision ID: f8b6c402a917
Revises: ed902d03df45
"""

import sqlalchemy as sa

from alembic import op

revision = "f8b6c402a917"  # pragma: allowlist secret
down_revision = "ed902d03df45"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def _replace_constraint(old_name: str, new_name: str, columns: str) -> None:
    # Save SQL-side so both online and offline migration execution work.
    op.execute(
        sa.text(
            """SELECT
                set_config('regengine.v128_previous_statement_timeout', current_setting('statement_timeout'), true),
                set_config('regengine.v128_previous_lock_timeout', current_setting('lock_timeout'), true)"""
        )
    )
    # statement_timeout must be set BEFORE the ALTER command starts. Setting
    # it inside the same DO block as ALTER does not bound that running command.
    op.execute(sa.text("SET LOCAL statement_timeout = '60s'"))
    op.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    op.execute(
        sa.text(
            f"ALTER TABLE ingestion.documents DROP CONSTRAINT {old_name}, ADD CONSTRAINT {new_name} UNIQUE ({columns})"
        )
    )
    op.execute(
        sa.text(
            """SELECT
                set_config('statement_timeout', current_setting('regengine.v128_previous_statement_timeout'), true),
                set_config('lock_timeout', current_setting('regengine.v128_previous_lock_timeout'), true)"""
        )
    )


def upgrade() -> None:
    _replace_constraint(
        "documents_content_sha256_key", "uq_ingestion_documents_tenant_content_sha256", "tenant_id, content_sha256"
    )


def downgrade() -> None:
    _replace_constraint(
        "uq_ingestion_documents_tenant_content_sha256", "documents_content_sha256_key", "content_sha256"
    )
