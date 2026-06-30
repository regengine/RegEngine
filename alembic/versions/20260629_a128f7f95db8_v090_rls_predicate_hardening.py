"""v090 -- converge divergent RLS predicates to fail-hard get_tenant_context().

Background (#2526)
------------------
Tenant-scoped RLS policies in the ``fsma`` schema drifted into two
incompatible predicate styles:

  * ``tenant_id = get_tenant_context()`` -- fails HARD (raises) when the
    ``app.tenant_id`` GUC is unset. This is the canonical contract every
    modern policy relies on (``get_tenant_context()`` is created by v056
    on Alembic-only DBs / Flyway V29 elsewhere and raises on an empty
    GUC).
  * ``tenant_id::text = current_setting('app.tenant_id', true)`` -- a
    text-compare that fails OPEN: an unset GUC silently yields the wrong
    row set instead of raising.

This migration forward-ports the remaining LIVE text-compare policies to
the fail-hard predicate so tenant isolation has a single, loud safety
default:

  1. The 8 V042 ``fsma.tenant_*`` feature tables. v051 Part 1 created
     four ``tenant_isolation_{select,insert,update,delete}`` policies per
     table using the text-compare style and no later migration ever
     replaced them. We drop those four and install one fail-hard
     ``FOR ALL`` policy per table, matching the v074 ``_TENANT_POLICY``
     shape already used for ``tenant_portal_links`` /
     ``supplier_integration_profiles`` (USING + WITH CHECK, sysadmin
     bypass branch, ``TO regengine, regengine_sysadmin``).

  2. ``fsma.fda_sla_requests`` (``tenant_isolation_sla``) and
     ``fsma.chain_verification_log`` (``tenant_isolation_chain_log``)
     from v048 -- the only other live tenant-isolation policies still on
     the text-compare style. Same conversion.

  3. ``fsma.task_queue`` (``tenant_isolation_tasks``). v050/v063 created
     this with an explicit ``OR current_setting('app.tenant_id', true) = ''``
     clause that returns EVERY tenant's rows when the GUC is unset.
     v067 already drops+recreates it as ``tenant_id = get_tenant_context()``
     in the live chain, so on a healthy DB this step is a no-op
     re-assertion. We re-state it here (drop + recreate without the
     empty-string OR) as a belt-and-suspenders guard for any environment
     where v067's ``task_queue`` block was skipped because the table did
     not yet exist at v067 time. ``task_queue.tenant_id`` is UUID after
     v067; the predicate compares UUID = UUID directly.

All ``tenant_id`` columns touched here are already ``UUID`` (V042 for the
tenant_* tables, v048 for the two operational tables, v067 for
task_queue), so the bare ``tenant_id = get_tenant_context()`` predicate
type-checks without a cast.

Idempotent: every policy install is DROP-IF-EXISTS + CREATE, and every
table reference is guarded by ``to_regclass`` so the migration is safe on
fresh, legacy, and partially-migrated databases.

Note: ``alembic/sql/V053__rls_standardize_1271.sql`` proposes the
*opposite* convergence (everything onto the text-compare style). It is
dead -- not wired into any Alembic revision -- and is intentionally left
untouched here.

Revision ID: a128f7f95db8
Revises: 38e02636e340
Create Date: 2026-06-29
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a128f7f95db8"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "d1bdfe74d1fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Canonical fail-hard tenant predicate with sysadmin bypass branch.
# Identical shape to v074's _TENANT_POLICY.
_TENANT_POLICY = """\
tenant_id = get_tenant_context()
OR (current_setting('regengine.is_sysadmin', true) = 'true'
    AND current_user = 'regengine_sysadmin')"""

# 8 V042 tenant_* feature tables that carry v051's text-compare policies.
_TENANT_FEATURE_TABLES = (
    "tenant_suppliers",
    "tenant_products",
    "tenant_team_members",
    "tenant_notification_prefs",
    "tenant_settings",
    "tenant_onboarding",
    "tenant_exchanges",
    "tenant_portal_links",
)

# v048 operational tables with text-compare tenant-isolation policies.
# (table, policy_name)
_OPERATIONAL_TABLES = (
    ("fda_sla_requests", "tenant_isolation_sla"),
    ("chain_verification_log", "tenant_isolation_chain_log"),
)


def _converge_feature_table(table: str) -> str:
    """Drop v051's four split text-compare policies and install one
    fail-hard FOR ALL policy. Guarded by to_regclass for fresh DBs."""
    fq = f"fsma.{table}"
    return f"""
        DO $mig$
        BEGIN
            IF to_regclass('{fq}') IS NULL THEN
                RETURN;
            END IF;

            EXECUTE 'ALTER TABLE {fq} ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE {fq} FORCE ROW LEVEL SECURITY';

            -- Remove the v051 Part-1 fail-open text-compare policies.
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_select ON {fq}';
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_insert ON {fq}';
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_update ON {fq}';
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_delete ON {fq}';
            -- tenant_portal_links also carries v074's fail-hard
            -- tenant_isolation_portal_links policy; drop it so this table
            -- ends with exactly one canonical policy (no-op elsewhere).
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_portal_links ON {fq}';

            -- Install the single fail-hard policy.
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_{table} ON {fq}';
            EXECUTE $pol$
                CREATE POLICY tenant_isolation_{table}
                    ON {fq}
                    FOR ALL TO regengine, regengine_sysadmin
                    USING ({_TENANT_POLICY})
                    WITH CHECK ({_TENANT_POLICY})
            $pol$;
        END
        $mig$;
    """


def _converge_operational_table(table: str, policy: str) -> str:
    """Replace a v048 text-compare policy with the fail-hard predicate."""
    fq = f"fsma.{table}"
    return f"""
        DO $mig$
        BEGIN
            IF to_regclass('{fq}') IS NULL THEN
                RETURN;
            END IF;

            EXECUTE 'ALTER TABLE {fq} ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE {fq} FORCE ROW LEVEL SECURITY';

            EXECUTE 'DROP POLICY IF EXISTS {policy} ON {fq}';
            EXECUTE $pol$
                CREATE POLICY {policy}
                    ON {fq}
                    FOR ALL TO regengine, regengine_sysadmin
                    USING ({_TENANT_POLICY})
                    WITH CHECK ({_TENANT_POLICY})
            $pol$;
        END
        $mig$;
    """


def upgrade() -> None:
    # 1. + 2. Feature and operational tables.
    for table in _TENANT_FEATURE_TABLES:
        op.execute(_converge_feature_table(table))

    for table, policy in _OPERATIONAL_TABLES:
        op.execute(_converge_operational_table(table, policy))

    # 3. task_queue -- belt-and-suspenders re-assert of the fail-hard
    #    policy v067 already installs. Drops the v050/v063 empty-string
    #    OR clause if it somehow survived (table created after v067 ran).
    op.execute(
        """
        DO $mig$
        BEGIN
            IF to_regclass('fsma.task_queue') IS NULL THEN
                RETURN;
            END IF;

            EXECUTE 'ALTER TABLE fsma.task_queue ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE fsma.task_queue FORCE ROW LEVEL SECURITY';
            EXECUTE 'DROP POLICY IF EXISTS tenant_isolation_tasks ON fsma.task_queue';
            EXECUTE 'CREATE POLICY tenant_isolation_tasks ON fsma.task_queue '
                    'USING (tenant_id = get_tenant_context())';
        END
        $mig$;
        """
    )


def downgrade() -> None:
    """Forward-only hardening.

    Reverting to the fail-open text-compare predicates would re-introduce
    the cross-tenant exposure this migration closes, so the downgrade
    deliberately does not restore them. The fail-hard policies installed
    here remain in place. Tables/policies can still be dropped by the
    downgrades of their originating migrations (v051, v048, v063) if a
    full teardown is required.
    """
    pass
