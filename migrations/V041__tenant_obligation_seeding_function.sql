-- V041 — Tenant-agnostic obligation seeding function
-- ===================================================
-- V036 seeds regulations, obligations, and controls only for the demo tenant
-- (5946c58f-ddf9-4db0-9baa-acb11c6fce91). New tenants get zero obligations,
-- which means their compliance scores start at 0% and they see no regulatory
-- context in the dashboard.
--
-- This migration creates a function that clones the demo tenant's seed data
-- for any new tenant, so every tenant starts with the full FSMA 204 regulatory
-- framework out of the box.

BEGIN;

CREATE OR REPLACE FUNCTION seed_obligations_for_tenant(p_tenant_id UUID)
RETURNS void AS $$
DECLARE
    demo_tenant UUID := '5946c58f-ddf9-4db0-9baa-acb11c6fce91';
    reg_count INT;
BEGIN
    -- Skip if tenant already has regulations
    SELECT COUNT(*) INTO reg_count FROM regulations WHERE tenant_id = p_tenant_id;
    IF reg_count > 0 THEN
        RAISE NOTICE 'Tenant % already has % regulations — skipping seed', p_tenant_id, reg_count;
        RETURN;
    END IF;

    -- Clone regulations
    INSERT INTO regulations (id, tenant_id, source_name, citation, section, text, effective_date)
    SELECT gen_random_uuid(), p_tenant_id, source_name, citation, section, text, effective_date
    FROM regulations
    WHERE tenant_id = demo_tenant;

    -- Clone obligations
    INSERT INTO obligations (id, tenant_id, regulation_id, title, description, risk_category, status, due_date, created_at)
    SELECT
        gen_random_uuid(),
        p_tenant_id,
        -- Map to the new tenant's regulation by matching citation
        (SELECT nr.id FROM regulations nr
         JOIN regulations dr ON dr.id = o.regulation_id
         WHERE nr.tenant_id = p_tenant_id AND nr.citation = dr.citation
         LIMIT 1),
        o.title, o.description, o.risk_category, o.status, o.due_date, NOW()
    FROM obligations o
    WHERE o.tenant_id = demo_tenant;

    -- Clone controls
    INSERT INTO controls (id, tenant_id, obligation_id, title, description, control_type, frequency, status, created_at)
    SELECT
        gen_random_uuid(),
        p_tenant_id,
        -- Map to the new tenant's obligation by matching title
        (SELECT no2.id FROM obligations no2
         JOIN obligations do2 ON do2.id = c.obligation_id
         WHERE no2.tenant_id = p_tenant_id AND no2.title = do2.title
         LIMIT 1),
        c.title, c.description, c.control_type, c.frequency, c.status, NOW()
    FROM controls c
    WHERE c.tenant_id = demo_tenant;

    RAISE NOTICE 'Seeded FSMA 204 obligations for tenant %', p_tenant_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION seed_obligations_for_tenant(UUID) IS
    'Clones FSMA 204 regulations, obligations, and controls from demo tenant '
    'to a new tenant. Idempotent — skips if tenant already has data. (V041)';

COMMIT;
