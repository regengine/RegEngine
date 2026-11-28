-- alembic-revision: 20ef2227dc73
-- rendered-from: alembic/versions/20261128_20ef2227dc73_v146_cte_event_supersessions.py (upgrade)
-- Apply before deploying the EDI line completion writer.

CREATE TABLE IF NOT EXISTS fsma.cte_event_supersessions (
    tenant_id uuid NOT NULL,
    superseded_event_id uuid NOT NULL,
    superseding_event_id uuid NOT NULL,
    superseded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, superseded_event_id),
    CHECK (superseded_event_id <> superseding_event_id)
);
ALTER TABLE fsma.cte_event_supersessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.cte_event_supersessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cte_event_supersessions_tenant ON fsma.cte_event_supersessions;
CREATE POLICY cte_event_supersessions_tenant ON fsma.cte_event_supersessions
    TO regengine
    USING (tenant_id = public.get_tenant_context())
    WITH CHECK (tenant_id = public.get_tenant_context());
REVOKE ALL ON fsma.cte_event_supersessions FROM PUBLIC;
GRANT SELECT, INSERT ON fsma.cte_event_supersessions TO regengine;

ALTER TABLE fsma.edi_line_identities ADD COLUMN IF NOT EXISTS canonical_event_id uuid;
GRANT UPDATE (canonical_event_id) ON fsma.edi_line_identities TO regengine;
