-- The write arm. Pre-#2935 every pattern anchored on USING\s*\(, so a
-- FOR INSERT ... WITH CHECK policy — the one governing whether a row can be
-- written INTO another tenant — matched nothing at all.
CREATE POLICY tenant_isolation_demo_insert ON fsma.demo_events
    FOR INSERT
    WITH CHECK (tenant_id = COALESCE(
        NULLIF(current_setting('app.tenant_id', TRUE), '')::UUID,
        '00000000-0000-0000-0000-000000000001'::UUID
    ));
