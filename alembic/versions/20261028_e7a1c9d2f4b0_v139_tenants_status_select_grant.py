"""Grant regengine column-level SELECT on tenants.status (v139 / SEL-616).

Prod auth for the Compliance Dashboard readiness path fails because
``shared.api_key_store`` runs ``SELECT status FROM tenants WHERE id = ...``
and v111 only granted ``SELECT (id)`` to ``regengine``. This revision adds
the missing column privilege only — never a table-level SELECT — and the
matching v111 ``REGENGINE_COLUMN_GRANTS`` inventory entry keeps the grant
across ``apply_runtime_role_cutover``.

Mirrors ``supabase/migrations/20261028120000_v139_tenants_status_select_grant.sql``.
Do not apply to prod without C.Lee's approval via DevOps. Pairs with the
UI degrade in #3740; this PR is the DB half of SEL-616.

Revision ID: e7a1c9d2f4b0
Revises: a3f7ce361b0e
Create Date: 2026-10-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e7a1c9d2f4b0"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "a3f7ce361b0e"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $grant$
        BEGIN
            IF to_regclass('public.tenants') IS NOT NULL
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                -- Column-level only. Do not GRANT SELECT ON public.tenants
                -- (table-level); names/settings stay control-plane.
                GRANT SELECT (status) ON TABLE public.tenants TO regengine;
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
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                REVOKE SELECT (status) ON TABLE public.tenants FROM regengine;
            END IF;
        END
        $revoke$;
        """
    )
