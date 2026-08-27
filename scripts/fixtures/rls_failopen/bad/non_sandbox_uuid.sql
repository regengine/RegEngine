-- A fallback to ANY fixed tenant is fail-open. Pre-#2935 the only surviving
-- (incidental) heuristic keyed on the literal 00000000-...-000000000001, so a
-- different constant sailed through. This is the shape that actually shipped
-- in alembic/versions/..._v080_rule_rejections_audit.py, with the nil UUID.
CREATE POLICY tenant_isolation_demo_other ON fsma.demo_events
    USING (
        tenant_id = COALESCE(
            NULLIF(current_setting('app.tenant_id', true), ''),
            '00000000-0000-0000-0000-000000000000'
        )::uuid
    );
