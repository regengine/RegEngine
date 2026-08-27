-- A hardcoded constant tenant in the WRITE arm, with no COALESCE at all.
-- Only the policy-predicate patterns can see this one, and only because they
-- alternate USING|WITH CHECK — it is the fixture that pins blind spot 3 shut.
CREATE POLICY tenant_isolation_demo_write ON fsma.demo_events
    FOR INSERT
    WITH CHECK (tenant_id = '00000000-0000-0000-0000-000000000001'::UUID);
