-- Verification Script for RLS
-- Run this in psql

-- 1. Create two tenants
INSERT INTO tenants (id, name, slug) VALUES 
('11111111-1111-1111-1111-111111111111', 'Tenant A', 'tenant-a'),
('22222222-2222-2222-2222-222222222222', 'Tenant B', 'tenant-b')
ON CONFLICT (id) DO NOTHING;

-- 2. Switch to Tenant A
SELECT set_tenant_context('11111111-1111-1111-1111-111111111111');

-- 3. Insert item for Tenant A
INSERT INTO review_items (doc_hash, text_raw, extraction, confidence_score)
VALUES ('hash_a', 'Data for A', '{}', 0.5);

-- 4. Verify visibility for A
SELECT count(*) as count_for_a FROM review_items;

-- 5. Switch to Tenant B
SELECT set_tenant_context('22222222-2222-2222-2222-222222222222');

-- 6. Verify visibility for B (Should be 0)
SELECT count(*) as count_for_b FROM review_items;

-- 7. Reset Context (Default Tenant)
SELECT set_tenant_context('00000000-0000-0000-0000-000000000001');
SELECT count(*) as count_for_default FROM review_items;
