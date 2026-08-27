-- The approved fail-closed pattern: get_tenant_context() RAISES when
-- app.tenant_id is unset rather than defaulting to a constant tenant.
-- This is what alembic/sql/V043, V044 and V002 actually use.
ALTER TABLE fsma.demo_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.demo_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_demo ON fsma.demo_events
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context()::uuid)
    WITH CHECK (tenant_id = get_tenant_context()::uuid);
