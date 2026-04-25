"""v068 — Add tenant-isolation RLS policy to fsma.transformation_links.

Phase C #1 of tenant-isolation convergence: forward-port the policy that
was lost in the 2026-04-20 alembic consolidation incident
(``docs/abandoned_migrations_20260420_incident/20260418_v067_transformation_links_policies.py``).

Background:

  V057 (commit 2026-04-15) created ``fsma.transformation_links`` with::

      ALTER TABLE fsma.transformation_links ENABLE ROW LEVEL SECURITY;
      ALTER TABLE fsma.transformation_links FORCE ROW LEVEL SECURITY;

  but never created the matching ``CREATE POLICY``. With RLS enabled
  AND forced and no policy, Postgres returns zero rows for every SELECT
  and rejects every INSERT/UPDATE/DELETE — regardless of tenant. The
  table behaves as a permanently empty fortress.

  ``services/shared/canonical_persistence/writer.py:599``
  (``_create_transformation_links``) writes to this table on every
  TRANSFORMATION CTE persist. ``services/ingestion/app/fda_export/
  queries.py:570`` reads from it for FDA recall lot expansion. Both
  paths have been silently broken since v057. A TRANSFORMATION CTE
  that loses its input/output lot linkage is an FSMA 204 traceability
  audit failure — recall expansion can't follow the trail.

  An abandoned migration ``v067_transformation_links_policies`` was
  written 2026-04-18 to fix this, but got quarantined to
  ``docs/abandoned_migrations_20260420_incident/`` during the alembic
  consolidation incident on 2026-04-20 (#1864 / v062). The fix was
  scheduled to be forward-ported "piecemeal in follow-up PRs" per the
  v059 consolidated-head migration's docstring; this is that
  forward-port.

What this migration does:

  Adds the same tenant-isolation policy shape v056 installs on every
  other ``fsma.*`` tenant-scoped table, plus the sysadmin-branch
  carve-out and the sysadmin-access audit trigger:

    * ``USING tenant_id = get_tenant_context()`` — fail-hard tenant
      scoping.
    * ``OR (current_setting('regengine.is_sysadmin', true) = 'true'
      AND current_user = 'regengine_sysadmin')`` — the sysadmin
      bypass branch. Activates only when BOTH conditions hold; the
      role check defeats a session-variable-only spoof.
    * ``trg_audit_sysadmin_transformation_links`` — every cross-
      tenant write by a sysadmin session lands in
      ``audit.sysadmin_access_log`` for after-the-fact review.

Idempotent: each statement is wrapped in a DO block so re-running is
safe. Tolerates the table being absent (fresh DB where the upstream
``transformation_links`` creation hasn't run) — silently skips.

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-04-24
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f0a1b2c3d4e5"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'transformation_links'
            ) THEN
                RAISE NOTICE 'fsma.transformation_links does not exist - skipping RLS policy create';
                RETURN;
            END IF;

            -- Drop any pre-existing partial policy to keep this idempotent.
            DROP POLICY IF EXISTS tenant_isolation_transformation_links
                ON fsma.transformation_links;

            CREATE POLICY tenant_isolation_transformation_links
                ON fsma.transformation_links
                FOR ALL TO regengine, regengine_sysadmin
                USING (
                    tenant_id = get_tenant_context()
                    OR (current_setting('regengine.is_sysadmin', true) = 'true'
                        AND current_user = 'regengine_sysadmin')
                )
                WITH CHECK (
                    tenant_id = get_tenant_context()
                    OR (current_setting('regengine.is_sysadmin', true) = 'true'
                        AND current_user = 'regengine_sysadmin')
                );

            -- Sysadmin-access audit trigger matches the v056 pattern
            -- so every cross-tenant write by a sysadmin session lands
            -- in audit.sysadmin_access_log.
            DROP TRIGGER IF EXISTS trg_audit_sysadmin_transformation_links
                ON fsma.transformation_links;
            CREATE TRIGGER trg_audit_sysadmin_transformation_links
                AFTER INSERT OR UPDATE OR DELETE ON fsma.transformation_links
                FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();
        END $$;
        """
    )


def downgrade() -> None:
    # Dropping the policy does NOT re-open the table to broad reads —
    # RLS is still FORCEd by v057. The result is the pre-fix empty-
    # fortress state: every SELECT returns zero rows. Operators should
    # roll forward with a corrective migration rather than downgrade.
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_tables
                WHERE schemaname = 'fsma' AND tablename = 'transformation_links'
            ) THEN
                RETURN;
            END IF;
            DROP TRIGGER IF EXISTS trg_audit_sysadmin_transformation_links
                ON fsma.transformation_links;
            DROP POLICY IF EXISTS tenant_isolation_transformation_links
                ON fsma.transformation_links;
        END $$;
        """
    )
