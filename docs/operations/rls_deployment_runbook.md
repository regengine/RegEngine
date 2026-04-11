# RLS Deployment Runbook

**Purpose**: Step-by-step guide for deploying RLS security layer to Supabase  
**Audience**: DevOps / Deployment Team  
**Estimated Time**: 30 minutes (+ backup/restore time if needed)

---

## Prerequisites

✅ **Required**:
- [ ] PostgreSQL client (`psql`) installed
- [ ] Supabase database credentials
- [ ] Git branch `feature/tenant-isolation-infrastructure` merged/accessible
- [ ] Recent database backup (CRITICAL!)

✅ **Environment Variables**:
```bash
# For local testing
export LOCAL_SUPABASE_DB_URL='postgresql://postgres:postgres@localhost:54322/postgres'

# For staging
export STAGING_SUPABASE_DB_URL='postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres'

# For production  
export PROD_SUPABASE_DB_URL='postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres'
```

---

## Phase 1: Local Testing (REQUIRED)

### 1.1 Start Local Supabase
```bash
cd /path/to/RegEngine
supabase start
```

### 1.2 Run Deployment Script
```bash
./scripts/deploy_rls.sh local
```

**Expected Output**:
```
✅ Database connection successful
✅ All pre-flight checks passed
✅ V27__rls_core_security_tables.sql completed
✅ V28__rls_pcos_vertical_tables.sql completed
✅ RLS enabled on 60+ tables
```

### 1.3 Verify Tenant Isolation
```bash
psql $LOCAL_SUPABASE_DB_URL -f services/admin/migrations/verify_rls_isolation.sql
```

**Expected Output**: All tests show `✅ PASS`

### 1.4 Test PostgREST API
```bash
# Test with tenant header
curl http://localhost:54321/rest/v1/pcos_projects \
  -H "apikey: YOUR_ANON_KEY" \
  -H "Authorization: Bearer YOUR_JWT_WITH_TENANT_CLAIM"

# Should return only tenant's projects
```

**✋ STOP**: If any test fails, fix issues before proceeding to staging!

---

## Phase 2: Staging Deployment

### 2.1 Create Backup
1. Go to Supabase Dashboard → Database → Backups
2. Click "Create Backup"
3. Wait for completion (~5-10 min for typical DBs)
4. ✅ Verify backup shows "Completed"

### 2.2 Deploy to Staging
```bash
./scripts/deploy_rls.sh staging
```

**Monitor** deployment output for any errors.

### 2.3 Post-Deployment Verification
```bash
# Run verification script
psql $STAGING_SUPABASE_DB_URL -f services/admin/migrations/verify_rls_isolation.sql

# Check RLS status
psql $STAGING_SUPABASE_DB_URL -c "
  SELECT 
    schemaname,
    tablename,
    rowsecurity AS rls_enabled
  FROM pg_tables
  WHERE schemaname = 'public'
    AND tablename LIKE 'pcos_%'
  ORDER BY tablename
  LIMIT 10;
"
```

### 2.4 Integration Testing
- [ ] Test frontend login flows
- [ ] Test API endpoints with proper JWTs
- [ ] Verify dashboard shows only tenant data
- [ ] Test multi-tenant scenarios
- [ ] Check application logs for RLS errors

### 2.5 Rollback (if needed)
```bash
# Restore from backup via Supabase Dashboard
# OR manually:
psql $STAGING_SUPABASE_DB_URL -c "
  -- Disable RLS on all tables
  DO \$\$
  DECLARE
    table_name text;
  BEGIN
    FOR table_name IN 
      SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
      EXECUTE 'ALTER TABLE ' || table_name || ' DISABLE ROW LEVEL SECURITY';
    END LOOP;
  END \$\$;
"
```

**✋ STOP**: Only proceed to production if staging tests pass 100%

---

## Phase 3: Production Deployment

### 3.1 Pre-Deployment Checklist
- [ ] All staging tests passed
- [ ] Recent production backup exists (< 24 hours old)
- [ ] Maintenance window scheduled
- [ ] Team notified of deployment
- [ ] Rollback plan ready
- [ ] Monitoring dashboards open

### 3.2 Maintenance Window Starts
1. **Optional**: Enable maintenance mode in app
2. **Optional**: Stop non-critical background jobs

### 3.3 Create Production Backup
```bash
# Via Supabase Dashboard (recommended)
# OR
pg_dump $PROD_SUPABASE_DB_URL > backup_before_rls_$(date +%Y%m%d_%H%M%S).sql
```

### 3.4 Deploy RLS Migrations
```bash
./scripts/deploy_rls.sh prod
```

**Watch** for any errors. Abort if deployment fails.

### 3.5 Immediate Verification
```bash
# Quick smoke test
psql $PROD_SUPABASE_DB_URL -f services/admin/migrations/verify_rls_isolation.sql

# Check table count
psql $PROD_SUPABASE_DB_URL -c "
  SELECT COUNT(*) as rls_enabled_tables
  FROM pg_tables t
  JOIN pg_class c ON c.relname = t.tablename
  WHERE t.schemaname = 'public' AND c.relrowsecurity = true;
"
```

**Expected**: ~60 tables with RLS enabled

### 3.6 Application Testing
- [ ] Frontend loads correctly
- [ ] Users can log in
- [ ] Dashboard shows correct tenant data
- [ ] API endpoints respond normally
- [ ] No RLS errors in logs

### 3.7 Monitoring (First Hour)
Watch for:
- ❌ 403 errors (RLS denying access)
- ❌ Slow query warnings (RLS overhead)
- ❌ Cross-tenant data leaks
- ✅ Normal application behavior

### 3.8 End Maintenance Window
- [ ] Disable maintenance mode
- [ ] Resume background jobs
- [ ] Notify team of successful deployment

---

## Phase 4: Post-Deployment

### 4.1 Performance Monitoring
```sql
-- Check for slow queries (daily for first week)
SELECT 
  query,
  calls,
  mean_exec_time,
  total_exec_time
FROM pg_stat_statements
WHERE query LIKE '%pcos_%' OR query LIKE '%tenants%'
ORDER BY mean_exec_time DESC
LIMIT 20;
```

### 4.2 Security Audit
```bash
# Weekly check: Verify RLS still enabled
psql $PROD_SUPABASE_DB_URL -c "
  SELECT 
    tablename,
    CASE WHEN rowsecurity THEN '✅ RLS ON' ELSE '❌ RLS OFF' END
  FROM pg_tables t
  JOIN pg_class c ON c.relname = t.tablename
  WHERE t.schemaname = 'public' AND t.tablename LIKE 'pcos_%';
"
```

### 4.3 Documentation Updates
- [ ] Update architecture diagrams
- [ ] Document JWT claim requirements
- [ ] Update API documentation
- [ ] Add RLS to onboarding docs

---

## Rollback Procedures

### If Caught Early (< 5 minutes)
```bash
# Restore from backup via Supabase Dashboard
# Dashboard → Database → Backups → Restore
```

### If Caught Late (> 5 minutes)
1. **Don't panic** - RLS is additive, doesn't delete data
2. Assess impact:
   - Are users blocked from their data?
   - Is there cross-tenant leakage?
3. Choose rollback strategy:
   - **Full restore**: From backup (loses recent data)
   - **Disable RLS**: Temporarily disable, fix, re-enable
   ```sql
   -- Emergency disable (if blocking users)
   ALTER TABLE problematic_table DISABLE ROW LEVEL SECURITY;
   ```

### Post-Rollback
- [ ] Identify root cause
- [ ] Fix migrations locally
- [ ] Re-test in staging
- [ ] Schedule new deployment

---

## Troubleshooting

### Issue: "Users can't see their data"
**Cause**: JWT missing `tenant_id` claim  
**Fix**: Update auth logic to include claim in JWT

### Issue: "Query too slow after RLS"
**Cause**: Missing index on `tenant_id`  
**Fix**: Already added in V002 migrations, verify:
```sql
SELECT tablename, indexname 
FROM pg_indexes 
WHERE indexname LIKE '%tenant%';
```

### Issue: "Admin can't see all tenants"
**Cause**: Admin queries need service role, not RLS  
**Fix**: Use service role key for admin operations

### Issue: "Migration failed halfway"
**Cause**: Table doesn't exist, syntax error, etc.  
**Fix**: Check migration output, fix SQL, rollback, retry

---

## Success Criteria

✅ All 60+ tables have RLS enabled  
✅ Tenant isolation verification passes  
✅ No cross-tenant data leaks  
✅ Application functions normally  
✅ Performance impact < 10% on queries  
✅ Zero RLS-related errors in logs

---

## Support Contacts

- **Database Issues**: DBA team
- **Application Issues**: Backend team
- **Security Questions**: Security team
- **Emergency Rollback**: On-call engineer

---

**Deployment Completed By**: __________  
**Date**: __________  
**Result**: ✅ Success / ❌ Rolled Back  
**Notes**: ___________________________
