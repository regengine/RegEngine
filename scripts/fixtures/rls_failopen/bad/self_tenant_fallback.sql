-- Silently-fail-open variant from the docstring: a context-less connection
-- satisfies tenant_id = tenant_id and reads every row.
CREATE POLICY tenant_isolation_demo_self ON fsma.demo_events
    USING (tenant_id = COALESCE(current_setting('app.tenant_id', TRUE)::UUID, tenant_id));
