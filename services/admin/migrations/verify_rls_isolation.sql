-- RLS Verification Script
-- Run this after deploying V27 and V28 to verify tenant isolation is working
--
-- Usage: psql $SUPABASE_DB_URL -f verify_rls_isolation.sql

\echo '========================================'
\echo 'RLS Tenant Isolation Verification'
\echo '========================================'
\echo ''

-- Step 1: Create test tenants
\echo 'Step 1: Creating test tenants...'
INSERT INTO tenants (id, name, slug, status) VALUES 
  ('11111111-1111-1111-1111-111111111111', 'Test Tenant A', 'test-tenant-a', 'active'),
  ('22222222-2222-2222-2222-222222222222', 'Test Tenant B', 'test-tenant-b', 'active')
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

\echo 'Created/Updated test tenants'
\echo ''

-- Step 2: Set context to Tenant A
\echo 'Step 2: Setting context to Tenant A...'
SELECT set_tenant_context('11111111-1111-1111-1111-111111111111');

-- Step 3: Insert test data for Tenant A
\echo 'Step 3: Inserting test data for Tenant A...'
INSERT INTO pcos_projects (id, tenant_id, name, status)
VALUES (
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  '11111111-1111-1111-1111-111111111111',
  'Tenant A Project',
  'active'
)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

\echo 'Inserted test project for Tenant A'
\echo ''

-- Step 4: Verify Tenant A can see their data
\echo 'Step 4: Verifying Tenant A can see their data...'
SELECT 
  CASE 
    WHEN COUNT(*) = 1 THEN '✅ PASS: Tenant A sees their project'
    ELSE '❌ FAIL: Tenant A should see 1 project, saw ' || COUNT(*)
  END AS test_result
FROM pcos_projects
WHERE id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

\echo ''

-- Step 5: Switch to Tenant B
\echo 'Step 5: Switching context to Tenant B...'
SELECT set_tenant_context('22222222-2222-2222-2222-222222222222');

-- Step 6: Verify Tenant B CANNOT see Tenant A's data
\echo 'Step 6: Verifying Tenant B cannot see Tenant A data...'
SELECT 
  CASE 
    WHEN COUNT(*) = 0 THEN '✅ PASS: Tenant B is isolated (cannot see Tenant A data)'
    ELSE '❌ FAIL: Tenant B should NOT see Tenant A project, but saw ' || COUNT(*) || ' rows'
  END AS test_result
FROM pcos_projects
WHERE id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

\echo ''

-- Step 7: Insert data for Tenant B
\echo 'Step 7: Inserting test data for Tenant B...'
INSERT INTO pcos_projects (id, tenant_id, name, status)
VALUES (
  'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
  '22222222-2222-2222-2222-222222222222',
  'Tenant B Project',
  'active'
)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name;

-- Step 8: Verify Tenant B sees only their data
\echo 'Step 8: Verifying Tenant B sees only their own data...'
SELECT 
  CASE 
    WHEN COUNT(*) = 1 THEN '✅ PASS: Tenant B sees exactly 1 project (their own)'
    ELSE '❌ FAIL: Tenant B should see 1 project, saw ' || COUNT(*) || ' projects'
  END AS test_result
FROM pcos_projects;

\echo ''

-- Step 9: Cross-contamination check
\echo 'Step 9: Cross-contamination check...'
SELECT set_tenant_context('11111111-1111-1111-1111-111111111111');

SELECT 
  CASE 
    WHEN COUNT(*) = 1 THEN '✅ PASS: Tenant A still sees only their project'
    ELSE '❌ FAIL: Tenant A should see 1 project, saw ' || COUNT(*) || ' projects'
  END AS test_result
FROM pcos_projects;

\echo ''

-- Step 10: Summary
\echo '========================================'
\echo 'RLS Verification Complete'
\echo '========================================'
\echo ''
\echo 'If all tests show ✅ PASS, tenant isolation is working correctly!'
\echo ''
\echo 'Cleanup (optional):'
\echo '  DELETE FROM pcos_projects WHERE id IN ('
\echo '    ''aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'','
\echo '    ''bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'''
\echo '  );'
\echo ''

-- Reset to default tenant
SELECT set_tenant_context('00000000-0000-0000-0000-000000000001');
