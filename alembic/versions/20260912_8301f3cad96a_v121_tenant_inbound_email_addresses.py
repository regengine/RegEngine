"""v121 — tenant inbound email address mapping for Postmark webhook.

Adds fsma.tenant_inbound_email_addresses, mapping a registered recipient
address (e.g. ingest+acme@inbound.regengine.co) to the tenant that owns it,
so the inbound-email ingestion webhook can resolve which tenant a supplier
email belongs to before any tenant context exists. Follows the same
SECURITY DEFINER lookup shape as v075's
fsma.get_active_portal_link_by_token — the address lookup happens before
authentication, so it must bypass RLS narrowly through a single-purpose
function rather than a broad grant.

Revision ID: 8301f3cad96a
Revises: c6a120b4e901
Create Date: 2026-09-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "8301f3cad96a"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c6a120b4e901"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.tenant_inbound_email_addresses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            inbound_address TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_inbound_email_addresses_addr
            ON fsma.tenant_inbound_email_addresses (LOWER(inbound_address))
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tenant_inbound_email_addresses_tid
            ON fsma.tenant_inbound_email_addresses (tenant_id)
        """
    )
    op.execute("COMMENT ON TABLE fsma.tenant_inbound_email_addresses IS "
               "'Maps a Postmark inbound-parse recipient address to the owning tenant (v121)'")

    op.execute("ALTER TABLE fsma.tenant_inbound_email_addresses ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE fsma.tenant_inbound_email_addresses FORCE ROW LEVEL SECURITY;")

    # Tenant self-service: a tenant may manage only its own registered addresses.
    for stmt in (
        """
        DO $$ BEGIN
            CREATE POLICY tenant_isolation_select ON fsma.tenant_inbound_email_addresses
                FOR SELECT
                USING (tenant_id::text = current_setting('app.tenant_id', true));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,
        """
        DO $$ BEGIN
            CREATE POLICY tenant_isolation_insert ON fsma.tenant_inbound_email_addresses
                FOR INSERT
                WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,
        """
        DO $$ BEGIN
            CREATE POLICY tenant_isolation_update ON fsma.tenant_inbound_email_addresses
                FOR UPDATE
                USING (tenant_id::text = current_setting('app.tenant_id', true))
                WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,
        """
        DO $$ BEGIN
            CREATE POLICY tenant_isolation_delete ON fsma.tenant_inbound_email_addresses
                FOR DELETE
                USING (tenant_id::text = current_setting('app.tenant_id', true));
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
        """,
    ):
        op.execute(stmt)

    # Narrow, token-style lookup policy for the webhook path, which has no
    # tenant context yet — mirrors portal_links_token_lookup from v075.
    op.execute("DROP POLICY IF EXISTS inbound_email_address_lookup ON fsma.tenant_inbound_email_addresses")
    op.execute(
        """
        CREATE POLICY inbound_email_address_lookup
            ON fsma.tenant_inbound_email_addresses
            FOR SELECT
            USING (
                LOWER(inbound_address) = NULLIF(LOWER(current_setting('app.inbound_email_lookup_address', true)), '')
                AND status = 'active'
            )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.get_tenant_by_inbound_address(p_address TEXT)
        RETURNS TABLE (
            tenant_id UUID,
            inbound_address TEXT,
            status TEXT,
            created_at TIMESTAMPTZ
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = fsma, public, pg_temp
        AS $fn$
        BEGIN
            PERFORM set_config('app.inbound_email_lookup_address', p_address, true);

            RETURN QUERY
            SELECT
                a.tenant_id,
                a.inbound_address,
                a.status,
                a.created_at
            FROM fsma.tenant_inbound_email_addresses AS a
            WHERE LOWER(a.inbound_address) = LOWER(p_address)
              AND a.status = 'active'
            LIMIT 1;
        END;
        $fn$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION fsma.get_tenant_by_inbound_address(TEXT) FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                GRANT EXECUTE ON FUNCTION fsma.get_tenant_by_inbound_address(TEXT) TO regengine;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                GRANT EXECUTE ON FUNCTION fsma.get_tenant_by_inbound_address(TEXT) TO regengine_sysadmin;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fsma.get_tenant_by_inbound_address(TEXT)")
    op.execute("DROP POLICY IF EXISTS inbound_email_address_lookup ON fsma.tenant_inbound_email_addresses")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_delete ON fsma.tenant_inbound_email_addresses")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_update ON fsma.tenant_inbound_email_addresses")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON fsma.tenant_inbound_email_addresses")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_select ON fsma.tenant_inbound_email_addresses")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_inbound_email_addresses")
