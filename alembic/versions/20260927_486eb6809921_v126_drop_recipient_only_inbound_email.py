"""v126 — drop the recipient-only inbound_email tenant mapping.

The ``inbound_email`` router (``/api/v1/webhooks/inbound-email``) resolved
the owning tenant from the recipient address alone through
``fsma.get_tenant_by_inbound_address(text)`` over
``fsma.tenant_inbound_email_addresses`` (8301f3cad96a). That is the
cross-tenant write v122 (d14f8a2b9c31) closed for ``email_ingest``: anyone
who knows a registered address can inject CTE rows into that tenant. The
router is deleted in the same change; ``email_ingest`` (sender-allowlisted
``get_tenant_by_inbound_address(text, text)`` over
``fsma.tenant_inbound_addresses``) is the only inbound-email path.

The one-arg overload survives only where 8301f3cad96a ran after v122 (the
two v121 branches are siblings, so replay order decides); it is dropped
wherever it exists. The v122 two-arg lookup is a different function and is
untouched.

The table is dropped only when empty. It is FORCE RLS and the migration
owner is NOBYPASSRLS, so a plain count would see no rows through the
tenant/lookup policies and the guard would pass vacuously; FORCE is lifted
first, as v124 does for owner writes. A non-empty table aborts the whole
revision (FORCE included) so an operator decides what happens to those
mappings instead of this migration deleting them.

Downgrade restores the empty table, indexes, and policies exactly as
8301f3cad96a created them, but not the recipient-only function: v125
reached through a fresh chain has no such function either, and restoring
it would re-grant the cross-tenant lookup to ``regengine``.

Revision ID: 486eb6809921
Revises: 22a278f6dc78
Create Date: 2026-09-27
"""

from alembic import op

revision = "486eb6809921"  # pragma: allowlist secret
down_revision = "22a278f6dc78"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_TABLE = "fsma.tenant_inbound_email_addresses"

# 8301f3cad96a's canonical fail-hard tenant predicate with sysadmin bypass.
_TENANT_POLICY = """\
tenant_id = get_tenant_context()
OR (current_setting('regengine.is_sysadmin', true) = 'true'
    AND current_user = 'regengine_sysadmin')"""


def upgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fsma.get_tenant_by_inbound_address(TEXT)")
    op.execute(
        f"""
        DO $$
        DECLARE
            v_rows BIGINT;
        BEGIN
            IF to_regclass('{_TABLE}') IS NULL THEN
                RETURN;
            END IF;
            ALTER TABLE {_TABLE} NO FORCE ROW LEVEL SECURITY;
            SELECT count(*) INTO v_rows FROM {_TABLE};
            IF v_rows > 0 THEN
                RAISE EXCEPTION
                    '{_TABLE} holds % row(s); refusing to drop recipient-only '
                    'inbound email mappings. Move each one to '
                    'fsma.tenant_inbound_addresses with an allowed_senders list '
                    '(docs/engineering/EMAIL_INGESTION.md), delete it, then rerun.',
                    v_rows;
            END IF;
        END
        $$;
        """
    )
    op.execute(f"DROP TABLE IF EXISTS {_TABLE}")


def downgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            inbound_address TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_inbound_email_addresses_addr
            ON {_TABLE} (LOWER(inbound_address))
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_tenant_inbound_email_addresses_tid
            ON {_TABLE} (tenant_id)
        """
    )
    op.execute(
        f"COMMENT ON TABLE {_TABLE} IS 'Maps a Postmark inbound-parse recipient address to the owning tenant (v121)'"
    )
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_inbound_email_addresses ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_inbound_email_addresses
            ON {_TABLE}
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_TENANT_POLICY})
            WITH CHECK ({_TENANT_POLICY})
        """
    )
    op.execute(f"DROP POLICY IF EXISTS inbound_email_address_lookup ON {_TABLE}")
    op.execute(
        f"""
        CREATE POLICY inbound_email_address_lookup
            ON {_TABLE}
            FOR SELECT
            USING (
                LOWER(inbound_address) = NULLIF(LOWER(current_setting('app.inbound_email_lookup_address', true)), '')
                AND status = 'active'
            )
        """
    )
