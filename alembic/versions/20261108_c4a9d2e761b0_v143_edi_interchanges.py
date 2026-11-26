"""Persist tenant-scoped ISA13 replay receipts with their events (v143).

Revision ID: c4a9d2e761b0
Revises: 9c0bfe465816
"""

from alembic import op

revision = "c4a9d2e761b0"  # pragma: allowlist secret
down_revision = "9c0bfe465816"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create a forced-RLS receipt table with narrowly scoped runtime grants."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS fsma.edi_interchanges (
            tenant_id uuid NOT NULL,
            sender_id text NOT NULL CHECK (sender_id <> ''),
            receiver_id text NOT NULL,
            isa13 text NOT NULL CHECK (isa13 <> ''),
            stored_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL CHECK (expires_at > stored_at),
            PRIMARY KEY (tenant_id, sender_id, receiver_id, isa13)
        );
        ALTER TABLE fsma.edi_interchanges ENABLE ROW LEVEL SECURITY;
        ALTER TABLE fsma.edi_interchanges FORCE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS edi_interchanges_tenant ON fsma.edi_interchanges;
        CREATE POLICY edi_interchanges_tenant ON fsma.edi_interchanges
            TO regengine
            USING (tenant_id = public.get_tenant_context())
            WITH CHECK (tenant_id = public.get_tenant_context());
        REVOKE ALL ON fsma.edi_interchanges FROM PUBLIC;
        GRANT SELECT, INSERT ON fsma.edi_interchanges TO regengine;
        GRANT UPDATE (stored_at, expires_at) ON fsma.edi_interchanges TO regengine;
    """)


def downgrade() -> None:
    """Remove replay receipts; deploy the previous application before downgrade."""
    op.execute("DROP TABLE fsma.edi_interchanges")
