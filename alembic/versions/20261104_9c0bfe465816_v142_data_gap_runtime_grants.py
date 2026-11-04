"""Grant the runtime role what data gap tracking needs (v142).

v135 granted ``public.data_gap_events`` to ``regengine``, but only in that
migration. ``apply_runtime_role_cutover`` rebuilds runtime grants from v111's
closed inventory on every deploy, so the grant was revoked at once. The gap
insert also reads ``public.supplier_traceability_lots``, which ``regengine``
never had. Every gap write failed with ``permission denied``, and because gap
logging is fail-open the only trace was a ``data_gap_write_failed`` log line.

This revision applies the grants, and the matching v111 inventory entries keep
them across deploys. ``supplier_traceability_lots`` gets only the three columns
the lookup reads. Both tables are tenant-scoped by forced RLS.

Mirrors ``supabase/migrations/20261104120000_v142_data_gap_runtime_grants.sql``.

Revision ID: 9c0bfe465816
Revises: 08c7cf36ddbe
Create Date: 2026-11-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "9c0bfe465816"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "08c7cf36ddbe"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $grant$
        BEGIN
            IF to_regclass('public.data_gap_events') IS NOT NULL
               AND to_regclass('public.supplier_traceability_lots') IS NOT NULL
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine')
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                GRANT SELECT, INSERT, UPDATE ON TABLE public.data_gap_events TO regengine;
                GRANT SELECT ON TABLE public.data_gap_events TO regengine_sysadmin;
                GRANT SELECT (tenant_id, tlc_code, facility_id) ON TABLE public.supplier_traceability_lots TO regengine;
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
            IF to_regclass('public.data_gap_events') IS NOT NULL
               AND to_regclass('public.supplier_traceability_lots') IS NOT NULL
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine')
               AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                REVOKE SELECT, INSERT, UPDATE ON TABLE public.data_gap_events FROM regengine;
                REVOKE SELECT ON TABLE public.data_gap_events FROM regengine_sysadmin;
                REVOKE SELECT (tenant_id, tlc_code, facility_id) ON TABLE public.supplier_traceability_lots FROM regengine;
            END IF;
        END
        $revoke$;
        """
    )
