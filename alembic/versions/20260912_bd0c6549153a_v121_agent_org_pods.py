"""v121 — agent organization: pods, agent identities, inboxes, suppression list.

Revision ID: bd0c6549153a
Revises: c6a120b4e901
Create Date: 2026-09-12

New schema ``agent_org`` (own-schema convention, mirroring ``fsma`` — see
``20260716_c7a1e5f2b9d4_v095_supplier_remediation_slice.py``):

1. ``agent_org.agent_pods`` — one row per pod (``department`` is one of
   ``research``, ``outreach``, ``ops``, ``legal_review``). ``UNIQUE
   (tenant_id, name)`` makes onboarding idempotent at the pod level.
2. ``agent_org.agent_identities`` — one row per agent, belonging to exactly
   one pod. ``tenant_id`` is denormalized alongside ``pod_id`` (same
   choice v095 makes for ``manifest_records.tenant_id``) so RLS and
   downstream queries never need a join to ``agent_pods`` just to filter
   by tenant. ``UNIQUE (tenant_id, pod_id, name)`` is the agent-level
   idempotency key.
3. ``agent_org.agent_inboxes`` — one inbox per agent. ``email_address`` is
   globally unique (not per-tenant): addresses are derived from the
   tenant's own slug, and two tenants must never collide on one address.
4. ``agent_org.email_suppressions`` — hard-suppression rows gating the
   existing remediation outbound-email path. No uniqueness constraint: an
   address can be suppressed more than once for different reasons and
   every row is kept for audit; ``is_suppressed()`` only cares whether any
   row matches.

All four tables: ``tenant_id UUID NOT NULL`` + ENABLE/FORCE ROW LEVEL
SECURITY with the ``get_tenant_context()`` policy, via the same
``_tenant_rls`` helper body v095 defines (each migration file in this repo
is self-contained rather than importing a shared migrations-lib module).
``get_tenant_context()`` itself is pinned fail-hard, STABLE by v097
(``20260721_e4d7b2a9c561_v097_pin_get_tenant_context_fail_hard.py``) —
this migration only consumes that function, it does not touch it.

Also extends the existing ``api_keys`` table (same file, one logical
change) with a nullable ``agent_id`` column, following the exact
precedent of the existing ``partner_id`` column
(``20260502_e1f2a3b4c5d6_v076_api_keys_partner_id.py``): NULL for
ordinary tenant keys, populated for keys minted via
``mint_agent_scoped_key()``. No FK to ``agent_org.agent_identities`` —
``api_keys`` lives in ``public`` and is looked up before any tenant/agent
context is established, so this stays a plain UUID column, exactly like
``partner_id`` is a plain, unconstrained string.

Idempotent and reversible. Downgrade drops the four new tables in
FK-safe order and reverts the ``api_keys`` column/index, but does not
``DROP SCHEMA agent_org`` — other migrations in this repo don't drop
their own schema either (v095 never does ``DROP SCHEMA fsma``).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "bd0c6549153a"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c6a120b4e901"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_rls(table: str, column: str, policy: str) -> None:
    schema, table_name = table.split(".", 1)
    op.execute(
        f"""
        DO $$
        DECLARE
            column_type text;
            predicate text;
        BEGIN
            IF to_regclass('{table}') IS NULL THEN
                RETURN;
            END IF;
            SELECT data_type INTO column_type
            FROM information_schema.columns
            WHERE table_schema = '{schema}'
              AND table_name = '{table_name}'
              AND column_name = '{column}';
            IF column_type IS NULL THEN
                RETURN;
            END IF;
            IF column_type IN ('text', 'character varying') THEN
                predicate := '{column} = get_tenant_context()::text';
            ELSE
                predicate := '{column} = get_tenant_context()';
            END IF;
            EXECUTE 'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE {table} FORCE ROW LEVEL SECURITY';
            EXECUTE 'DROP POLICY IF EXISTS {policy} ON {table}';
            EXECUTE format(
                'CREATE POLICY {policy} ON {table}
                    FOR ALL
                    USING (%s)
                    WITH CHECK (%s)',
                predicate,
                predicate
            );
        END $$;
        """
    )


def _create_tables() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS agent_org")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_org.agent_pods (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            department TEXT NOT NULL
                CHECK (department IN ('research', 'outreach', 'ops', 'legal_review')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, name)
        );
        CREATE INDEX IF NOT EXISTS idx_agent_pods_tenant
            ON agent_org.agent_pods (tenant_id);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_org.agent_identities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pod_id UUID NOT NULL REFERENCES agent_org.agent_pods(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, pod_id, name)
        );
        CREATE INDEX IF NOT EXISTS idx_agent_identities_tenant_pod
            ON agent_org.agent_identities (tenant_id, pod_id);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_org.agent_inboxes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            agent_id UUID NOT NULL
                REFERENCES agent_org.agent_identities(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email_address TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL,
            provider_ref TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_agent_inboxes_tenant_agent
            ON agent_org.agent_inboxes (tenant_id, agent_id);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_org.email_suppressions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email_address TEXT NOT NULL,
            reason TEXT NOT NULL
                CHECK (reason IN ('bounce', 'complaint', 'manual_unsubscribe')),
            source TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_email_suppressions_tenant_email
            ON agent_org.email_suppressions (tenant_id, email_address);
        """
    )


def _api_keys_exists() -> bool:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return bool(bind.execute(sa.text("SELECT to_regclass('api_keys') IS NOT NULL")).scalar())

    return sa.inspect(bind).has_table("api_keys")


def _add_api_keys_agent_id() -> None:
    if not _api_keys_exists():
        return

    # Idempotent — safe to run twice if a partial deploy needs replay.
    op.execute(
        """
        ALTER TABLE api_keys
            ADD COLUMN IF NOT EXISTS agent_id UUID
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_keys_agent_id
            ON api_keys (agent_id)
        """
    )


def _drop_api_keys_agent_id() -> None:
    if not _api_keys_exists():
        return

    op.execute("DROP INDEX IF EXISTS ix_api_keys_agent_id")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS agent_id")


def upgrade() -> None:
    _create_tables()
    _tenant_rls("agent_org.agent_pods", "tenant_id", "tenant_isolation_agent_pods")
    _tenant_rls("agent_org.agent_identities", "tenant_id", "tenant_isolation_agent_identities")
    _tenant_rls("agent_org.agent_inboxes", "tenant_id", "tenant_isolation_agent_inboxes")
    _tenant_rls("agent_org.email_suppressions", "tenant_id", "tenant_isolation_email_suppressions")
    _add_api_keys_agent_id()


def downgrade() -> None:
    _drop_api_keys_agent_id()
    op.execute("DROP TABLE IF EXISTS agent_org.agent_inboxes")
    op.execute("DROP TABLE IF EXISTS agent_org.agent_identities")
    op.execute("DROP TABLE IF EXISTS agent_org.agent_pods")
    op.execute("DROP TABLE IF EXISTS agent_org.email_suppressions")
    # Schema left in place intentionally — see module docstring; matches
    # v095's own downgrade(), which never DROP SCHEMA fsma.
