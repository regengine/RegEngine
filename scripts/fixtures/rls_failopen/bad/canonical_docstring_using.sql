-- The canonical fail-open form quoted verbatim in check_rls_fallback.py's
-- own docstring. The pre-#2935 _PAT_FALLBACK_UUID could not match it: its
-- [^)]* window stopped at the first ")" of the nested NULLIF(current_setting(...)).
ALTER TABLE fsma.demo_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_demo ON fsma.demo_events
    USING (tenant_id = COALESCE(
        NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
        '00000000-0000-0000-0000-000000000001'::UUID
    ));
