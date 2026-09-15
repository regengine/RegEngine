"""v121 — tenant inbound email address mapping for Postmark webhook.

Adds fsma.tenant_inbound_email_addresses, mapping a registered recipient
address (e.g. ingest+acme@inbound.regengine.co) to the tenant that owns it,
so the inbound-email ingestion webhook can resolve which tenant a supplier
email belongs to before any tenant context exists. Follows the same
SECURITY DEFINER lookup shape as v075's
fsma.get_active_portal_link_by_token — the address lookup happens before
authentication, so it must bypass RLS narrowly through a single-purpose
function rather than a broad grant.

Tenant self-service isolation uses the fail-hard predicate converged on by
v090 (``tenant_id = get_tenant_context()``, raising on an unset GUC) with
the v074 sysadmin-bypass shape, not the older text-compare style — this is
a new table, so it starts on the canonical predicate directly.

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

# Canonical fail-hard tenant predicate with sysadmin bypass branch.
# Identical shape to v074's/v090's _TENANT_POLICY.
_TENANT_POLICY = """\
tenant_id = get_tenant_context()
OR (current_setting('regengine.is_sysadmin', true) = 'true'
    AND current_user = 'regengine_sysadmin')"""


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
    # This branch's TABLE-returning shape conflicts with the sibling v121
    # branch (ccaa01e4fd7c, RETURNS UUID). CREATE OR REPLACE cannot change a
    # return type, so on a scratch database that replays both branches the
    # second definition must drop first; the security-hardened v122
    # (d14f8a2b9c31) redefines the function last in topological order, so the
    # final shape is identical regardless of branch replay order.
    op.execute("DROP FUNCTION IF EXISTS fsma.get_tenant_by_inbound_address(TEXT)")
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

    # Tenant self-service: a tenant may manage only its own registered
    # addresses. Fail-hard predicate (v090 convergence) — an unset
    # app.tenant_id GUC raises via get_tenant_context() rather than
    # silently matching the wrong rows.
    op.execute("DROP POLICY IF EXISTS tenant_isolation_inbound_email_addresses ON fsma.tenant_inbound_email_addresses")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_inbound_email_addresses
            ON fsma.tenant_inbound_email_addresses
            FOR ALL TO regengine, regengine_sysadmin
            USING ({_TENANT_POLICY})
            WITH CHECK ({_TENANT_POLICY})
        """
    )

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
    op.execute("DROP POLICY IF EXISTS tenant_isolation_inbound_email_addresses ON fsma.tenant_inbound_email_addresses")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_inbound_email_addresses")
