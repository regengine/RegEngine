-- alembic-revision: 62355c37e367
-- rendered-from: alembic/versions/20261121_62355c37e367_v145_edi_line_identities.py (upgrade)
-- Apply before deploying the EDI line identity writer.

CREATE TABLE IF NOT EXISTS fsma.edi_line_identities (
    tenant_id uuid NOT NULL,
    identity_key text NOT NULL CHECK (identity_key <> ''),
    content_digest text NOT NULL CHECK (content_digest <> ''),
    event_id uuid NOT NULL,
    stored_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, identity_key)
);
ALTER TABLE fsma.edi_line_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.edi_line_identities FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS edi_line_identities_tenant ON fsma.edi_line_identities;
CREATE POLICY edi_line_identities_tenant ON fsma.edi_line_identities
    TO regengine
    USING (tenant_id = public.get_tenant_context())
    WITH CHECK (tenant_id = public.get_tenant_context());
REVOKE ALL ON fsma.edi_line_identities FROM PUBLIC;
GRANT SELECT, INSERT ON fsma.edi_line_identities TO regengine;
GRANT UPDATE (content_digest, event_id, stored_at) ON fsma.edi_line_identities TO regengine;
