# Security Hardening Deploy Checklist

**Purpose**: Step-by-step deploy procedure for the security hardening sprint (PRs #320–#330)
**Audience**: Platform operator (Christopher Sellers)
**Estimated Time**: 2–3 hours with monitoring windows
**Date**: 2026-03-27

---

## Prerequisites

- [ ] All 11 PRs (#320–#330) merged to `main`
- [ ] CI pipeline green on `main` (QA Pipeline, Frontend CI/CD, Security workflow)
- [ ] Database backup completed and verified
- [ ] Access to K8s cluster (`kubectl` authenticated)
- [ ] Vercel dashboard access for frontend deploys
- [ ] Monitoring dashboards open (Grafana, Sentry, Vercel Analytics)

## Environment Variables

Verify these are set correctly **before** deploying:

| Variable | Requirement | Check Command |
|---|---|---|
| `REGENGINE_ENV` | Must be `production` | `kubectl get secret regengine-secrets -o jsonpath='{.data.REGENGINE_ENV}' \| base64 -d` |
| `AUTH_TEST_BYPASS_TOKEN` | Must **NOT** be set in production | `kubectl get secret regengine-secrets -o jsonpath='{.data.AUTH_TEST_BYPASS_TOKEN}'` (should be empty) |
| `REGENGINE_JWT_SECRET` | Must differ from staging | Compare against staging secret |
| `CSRF_SECRET` | Must be set (PR #329) | `kubectl get secret regengine-secrets -o jsonpath='{.data.CSRF_SECRET}' \| base64 -d` |
| `NEXT_PUBLIC_*` | Must contain only public/anon keys | Audit all `NEXT_PUBLIC_` vars in Vercel project settings |

---

## Phase 1: Infrastructure (Zero Downtime)

**Scope**: NetworkPolicies, K8s resource limits, ingress security headers
**PRs**: #321, #325

### Steps

- [ ] **1.1** Apply namespace if not present
  ```bash
  kubectl apply -f infra/k8s/base/namespace.yaml
  ```

- [ ] **1.2** Apply NetworkPolicies
  ```bash
  kubectl apply -f infra/k8s/base/admin/networkpolicy.yaml
  kubectl apply -f infra/k8s/base/ingestion/networkpolicy.yaml
  ```

- [ ] **1.3** Verify NetworkPolicies are active
  ```bash
  kubectl get networkpolicies -n regengine
  ```
  Expected: `admin-network-policy` and `ingestion-network-policy` listed

- [ ] **1.4** Apply resource limits via deployments
  ```bash
  kubectl apply -f infra/k8s/base/admin/deployment.yaml
  kubectl apply -f infra/k8s/base/ingestion/deployment.yaml
  kubectl apply -f infra/k8s/base/compliance/deployment.yaml
  kubectl apply -f infra/k8s/base/scheduler/deployment.yaml
  ```

- [ ] **1.5** Apply ingress with security headers
  ```bash
  kubectl apply -f infra/k8s/base/ingress.yaml
  ```

- [ ] **1.6** Verify pods are running with new limits
  ```bash
  kubectl get pods -n regengine
  kubectl top pods -n regengine
  ```

### Verification
- [ ] All pods in `Running` state
- [ ] No `OOMKilled` or `CrashLoopBackOff` events
- [ ] Inter-service communication still works (health endpoints respond)
- [ ] Ingress returns security headers (`X-Frame-Options`, `X-Content-Type-Options`, `Strict-Transport-Security`)

### Rollback
```bash
# If NetworkPolicies block legitimate traffic:
kubectl delete networkpolicies --all -n regengine

# If resource limits cause OOM:
kubectl rollout undo deployment/<service-name> -n regengine
```

---

## Phase 2: Database (Requires Backup)

**Scope**: RLS defense-in-depth, sysadmin audit triggers
**PRs**: #324

### Pre-Flight
- [ ] **2.0** Confirm database backup is complete and restorable

### Steps

- [ ] **2.1** Apply RLS hardening migration via Supabase dashboard or CLI
  - Adds audit logging for sysadmin RLS bypass
  - Adds role-gated trigger validation

- [ ] **2.2** Verify RLS policies are active
  ```sql
  SELECT schemaname, tablename, policyname, permissive, roles, cmd
  FROM pg_policies
  WHERE schemaname = 'public'
  ORDER BY tablename;
  ```

- [ ] **2.3** Test tenant isolation
  ```sql
  -- As a regular user, verify cross-tenant access is blocked
  SET app.current_tenant_id = 'tenant-a';
  SELECT count(*) FROM kte WHERE tenant_id = 'tenant-b';
  -- Expected: 0 rows
  ```

- [ ] **2.4** Verify sysadmin audit trigger fires
  ```sql
  -- As sysadmin, perform a cross-tenant query
  -- Check audit_logs for the bypass entry
  SELECT * FROM audit_logs
  WHERE action = 'rls_sysadmin_bypass'
  ORDER BY created_at DESC
  LIMIT 5;
  ```

### Verification
- [ ] Regular tenant queries return only own-tenant data
- [ ] Sysadmin bypass is logged to audit_logs
- [ ] No existing queries broken (check application logs for SQL errors)

### Rollback
```sql
-- Revert RLS migration (use specific migration rollback from Supabase CLI)
-- Keep backup restoration as last resort
```

---

## Phase 3: Backend Services (Rolling Update)

**Scope**: Auth guards, SQL injection allowlisting, race condition fixes, JWT rotation
**PRs**: #322, #323, #326, #328
**Strategy**: Rolling update, one service at a time, 5-minute monitoring window between each

### Deploy Order

- [ ] **3.1** Deploy **ingestion** service
  ```bash
  kubectl rollout restart deployment/ingestion -n regengine
  kubectl rollout status deployment/ingestion -n regengine --timeout=120s
  ```
  **Wait 5 minutes.** Monitor:
  - [ ] Health endpoint responds 200
  - [ ] Ingestion throughput within 20% of baseline
  - [ ] No 5xx errors in logs

- [ ] **3.2** Deploy **admin** service
  ```bash
  kubectl rollout restart deployment/admin -n regengine
  kubectl rollout status deployment/admin -n regengine --timeout=120s
  ```
  **Wait 5 minutes.** Monitor:
  - [ ] Health endpoint responds 200
  - [ ] Auth-guarded endpoints return 401 for unauthenticated requests
  - [ ] No SQL errors in logs

- [ ] **3.3** Deploy **compliance** service
  ```bash
  kubectl rollout restart deployment/compliance -n regengine
  kubectl rollout status deployment/compliance -n regengine --timeout=120s
  ```
  **Wait 5 minutes.** Monitor:
  - [ ] Health endpoint responds 200
  - [ ] Compliance checks return results
  - [ ] No 5xx errors

- [ ] **3.4** Deploy **scheduler** service
  ```bash
  kubectl rollout restart deployment/scheduler -n regengine
  kubectl rollout status deployment/scheduler -n regengine --timeout=120s
  ```
  **Wait 5 minutes.** Monitor:
  - [ ] Health endpoint responds 200
  - [ ] Scheduled jobs executing on time

### Verification
- [ ] All 4 services healthy
- [ ] `GET /health` returns 200 on all services
- [ ] Auth guards active: unauthenticated `POST /api/ingest` returns 401
- [ ] SQL injection blocked: column injection attempt returns 400
- [ ] JWT `kid` header present in new tokens

### Rollback
```bash
# Rollback a specific service:
kubectl rollout undo deployment/<service-name> -n regengine

# Verify rollback:
kubectl rollout status deployment/<service-name> -n regengine
```

---

## Phase 4: Frontend (Cookie Migration + CSRF + Bundle)

**Scope**: localStorage to HTTP-only cookies, CSRF double-submit, lazy loading
**PRs**: #327, #329, #330
**Platform**: Vercel (auto-deploys from main)

### Steps

- [ ] **4.1** Verify Vercel deployment completed successfully
  - Check Vercel dashboard for latest deployment status
  - Confirm deployment is promoted to production

- [ ] **4.2** Test login flow end-to-end
  - [ ] Login sets `re_access_token` as HTTP-only cookie
  - [ ] Login sets `re_csrf` (readable) and `re_csrf_sig` (HTTP-only) cookies
  - [ ] Session persists across page refresh
  - [ ] Logout clears all cookies

- [ ] **4.3** Test CSRF protection
  - [ ] Mutating API request without `X-CSRF-Token` header returns 403
  - [ ] Mutating API request with valid CSRF header succeeds
  - [ ] GET requests are unaffected
  - [ ] Webhook endpoints (`/api/webhooks/*`) are exempt
  - [ ] Bearer token requests bypass CSRF check

- [ ] **4.4** Test dual-write cookie migration
  - [ ] Users with existing localStorage sessions can still access the app
  - [ ] New sessions use HTTP-only cookies exclusively
  - [ ] No force-logout during transition

- [ ] **4.5** Verify bundle optimization
  - [ ] PDF export works (jspdf lazy-loaded)
  - [ ] Excel export works (exceljs lazy-loaded)
  - [ ] Label page renders PDF preview (react-pdf lazy-loaded)
  - [ ] Dashboard anomaly simulator loads (recharts lazy-loaded)
  - [ ] Mobile barcode scanner loads (html5-qrcode lazy-loaded)
  - [ ] No flash of unstyled/missing content

### Verification
- [ ] Login/logout flow works in Chrome, Firefox, Safari
- [ ] No console errors related to CSRF or cookies
- [ ] Vercel Analytics shows reduced bundle size (~1.6MB savings)
- [ ] Lighthouse performance score stable or improved

### Rollback
```bash
# Revert to previous Vercel deployment:
# Vercel Dashboard → Deployments → select previous → Promote to Production

# If cookie migration breaks login:
# 1. Revert frontend deployment
# 2. Users fall back to localStorage auth (still present in dual-write phase)
```

---

## Phase 5: Post-Deploy Verification

### Automated Checks
- [ ] **5.1** Run full QA pipeline against production
  ```bash
  # Stage 1: Fast Gate
  node qa/fsma-lite-check.js --env=production
  node qa/tenant-test.js --env=production

  # Stage 2: System Simulation
  node qa/full-flow.js --env=production
  node qa/bad-data.js --env=production
  node qa/export-validate.js --env=production

  # Stage 3: AI Analysis
  node qa/ai-analysis.js --env=production
  ```
  Expected: All 164 checks passing

- [ ] **5.2** Run security test suite
  ```bash
  pytest tests/security/test_security_audit_fixes.py -v
  pytest tests/security/test_tenant_isolation.py -v
  ```
  Expected: All 48 tests passing

### Manual Smoke Tests
- [ ] **5.3** Create a new tenant, ingest sample data, verify isolation
- [ ] **5.4** Run a compliance check end-to-end
- [ ] **5.5** Export a PDF report and Excel file
- [ ] **5.6** Verify audit log entries for the session
- [ ] **5.7** Check Sentry for any new error spikes

### Security Spot Checks
- [ ] **5.8** Verify security headers on production domain
  ```bash
  curl -I https://app.regengine.com | grep -E '(X-Frame|X-Content-Type|Strict-Transport|X-XSS)'
  ```
- [ ] **5.9** Confirm `AUTH_TEST_BYPASS_TOKEN` is not accessible
- [ ] **5.10** Verify HTTPS-only (HTTP redirects to HTTPS)

---

## Rollback Triggers

| Condition | Threshold | Action |
|---|---|---|
| 5xx error rate | > 1% for 5 minutes | Rollback backend services |
| p95 latency | > 3000ms for 5 minutes | Rollback backend services |
| Login flow broken | Any user report | Rollback frontend, revert cookie migration |
| RLS blocking legitimate queries | Any occurrence | Revert RLS migration SQL |
| NetworkPolicy blocking services | Any occurrence | Delete all network policies |
| Ingestion throughput drop | > 20% sustained | Rollback ingestion service |

---

## Success Criteria

All phases complete when:
- [ ] All 164 QA checks passing against production
- [ ] All 48 security tests passing
- [ ] No new Sentry errors in 24-hour window
- [ ] p95 latency within baseline (< 2000ms per FSMA SLOs)
- [ ] Ingestion throughput at 10k events/min SLO
- [ ] Zero unauthorized cross-tenant data access
