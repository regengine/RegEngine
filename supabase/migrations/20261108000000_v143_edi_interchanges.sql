-- Mirrors Alembic c4a9d2e761b0. Apply before deploying the EDI receipt writer.

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
