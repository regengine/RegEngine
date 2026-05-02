"""v075 — supplier portal token lookup under RLS.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-05-01
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d0e1f2a3b4c5"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tenant_portal_links_token_active
            ON fsma.tenant_portal_links (link_token)
            WHERE status = 'active'
        """
    )
    op.execute("DROP POLICY IF EXISTS portal_links_token_lookup ON fsma.tenant_portal_links")
    op.execute(
        """
        CREATE POLICY portal_links_token_lookup
            ON fsma.tenant_portal_links
            FOR SELECT
            USING (
                link_token = NULLIF(current_setting('app.portal_link_token', true), '')
                AND status = 'active'
                AND expires_at > now()
            )
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.get_active_portal_link_by_token(p_link_token TEXT)
        RETURNS TABLE (
            tenant_id UUID,
            supplier_name TEXT,
            supplier_email TEXT,
            allowed_cte_types TEXT[],
            integration_profile_id TEXT,
            link_token TEXT,
            status TEXT,
            created_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = fsma, public, pg_temp
        AS $fn$
        BEGIN
            PERFORM set_config('app.portal_link_token', p_link_token, true);

            RETURN QUERY
            SELECT
                l.tenant_id,
                l.supplier_name,
                l.supplier_email,
                l.allowed_cte_types,
                l.integration_profile_id,
                l.link_token,
                l.status,
                l.created_at,
                l.expires_at
            FROM fsma.tenant_portal_links AS l
            WHERE l.link_token = p_link_token
              AND l.status = 'active'
              AND l.expires_at > now()
            LIMIT 1;
        END;
        $fn$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION fsma.get_active_portal_link_by_token(TEXT) FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                GRANT EXECUTE ON FUNCTION fsma.get_active_portal_link_by_token(TEXT) TO regengine;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                GRANT EXECUTE ON FUNCTION fsma.get_active_portal_link_by_token(TEXT) TO regengine_sysadmin;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fsma.get_active_portal_link_by_token(TEXT)")
    op.execute("DROP POLICY IF EXISTS portal_links_token_lookup ON fsma.tenant_portal_links")
    op.execute("DROP INDEX IF EXISTS fsma.idx_tenant_portal_links_token_active")
