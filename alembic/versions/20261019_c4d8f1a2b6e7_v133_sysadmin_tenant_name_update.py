"""Let the sysadmin role rename a tenant.

``PATCH /admin/organizations/{org_id}`` renames the passwordless-auth
organization and the tenant row that shares its ID, in one transaction. v111
granted ``regengine_sysadmin`` UPDATE on only ``tenants(settings, updated_at)``,
so the tenant rename would fail with ``permission denied``. The existing
``tenants_sysadmin_update`` policy already limits the write to an armed
sysadmin session.

Revision ID: c4d8f1a2b6e7
Revises: a9ea09050a30
Create Date: 2026-10-19
"""

from alembic import op

revision = "c4d8f1a2b6e7"  # pragma: allowlist secret
down_revision = "a9ea09050a30"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $grant$
        BEGIN
            IF to_regclass('public.tenants') IS NOT NULL
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                GRANT UPDATE (name) ON TABLE public.tenants TO regengine_sysadmin;
            END IF;
        END
        $grant$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $revoke$
        BEGIN
            IF to_regclass('public.tenants') IS NOT NULL
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                REVOKE UPDATE (name) ON TABLE public.tenants FROM regengine_sysadmin;
            END IF;
        END
        $revoke$;
        """
    )
