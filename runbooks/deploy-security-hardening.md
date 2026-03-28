# Security Hardening Release Deployment Runbook

## Service Information
- **Services:** ingestion, admin, compliance, graph, frontend
- **Criticality:** Tier 1 (Security)
- **Scope:** 11 PRs (#320–#330) - Auth, SQL injection, RLS, K8s, JWT rotation
- **Database changes:** Yes (RLS policies, audit logs)
- **Infrastructure changes:** Yes (NetworkPolicies, security headers, resource limits)
- **Breaking changes:** AUTH_TEST_BYPASS_TOKEN blocked in production

---

## Prerequisites

- [ ] All 11 PRs merged to main and CI green
- [ ] Gitleaks scan passes (no secrets in diff)
- [ ] Semgrep SAST passes (OWASP rules)
- [ ] Database backup taken (production)
- [ ] K8s rollback commands prepared
- [ ] Feature flag for cookie migration ready

---

## Deployment Steps

### Phase 1: Infrastructure (Zero-Downtime)

1. **Apply NetworkPolicies**
   ```bash
   kubectl apply -f infra/k8s/base/network-policies.yaml
   ```

2. **Verify service communication**
   ```bash
   kubectl exec -it ingestion-0 -- curl http://admin-service:8400/health
   ```

3. **Apply ingress security headers**
   ```bash
   kubectl apply -f infra/k8s/base/ingress-security-headers.yaml
   ```

4. **Verify headers**
   ```bash
   curl -sI https://api.regengine.co | grep -E "X-Frame|CSP|Strict-Transport"
   ```

### Phase 2: Database Migrations

5. **Apply RLS migration (PR #324)**
   ```bash
   psql -f migrations/rls_sysadmin_audit.sql
   ```

6. **Verify RLS policies exist**
   ```bash
   kubectl exec -it postgres-0 -- psql -c \
     "SELECT policyname FROM pg_policies WHERE schemaname = 'fsma'"
   ```

### Phase 3: Backend Services (Rolling Update)

7. **Deploy ingestion (auth + SQL injection fixes)**
   ```bash
   kubectl set image deployment/ingestion \
     ingestion=ghcr.io/regengine/ingestion:v2.4.0
   kubectl rollout status deployment/ingestion --timeout=5m
   ```

8. **Monitor for 5 minutes** — error rate should stay < 0.1%
   ```bash
   kubectl logs -l app=ingestion --tail=50 -f
   ```

9. **Deploy admin, compliance, graph services**
   ```bash
   kubectl set image deployment/admin admin=ghcr.io/regengine/admin:v2.4.0
   kubectl rollout status deployment/admin
   # Repeat for compliance and graph
   ```

### Phase 4: Frontend Deployment

10. **Deploy frontend (cookies + CSRF + bundle optimization)**
    ```bash
    vercel deploy --prod
    ```

11. **Verify login flow end-to-end**
    - Navigate to https://regengine.co/login
    - Login with test account
    - Open DevTools → Application → Cookies
    - Confirm no localStorage tokens remain

### Phase 5: Verification

12. **Run QA security test suite**
    ```bash
    pytest tests/security/test_security_audit_fixes.py -v
    npx playwright test security-audit-fixes.spec.ts
    ```

13. **Verify unauthenticated endpoints return 401**
    ```bash
    curl -X GET https://api.regengine.co/v1/documents
    # Expected: 401 Unauthorized
    ```

14. **Test SQL injection protection** (safe payloads only)
    ```bash
    curl -X GET "https://api.regengine.co/v1/documents?filter=%27%20OR%20%271%27%3D%271"
    # Expected: 400 Bad Request (not 500)
    ```

15. **Confirm AUTH_TEST_BYPASS_TOKEN is blocked**
    ```bash
    curl -H "X-AUTH-BYPASS: test-token" https://api.regengine.co/health
    # Expected: 401 Unauthorized
    ```

16. **Monitor Prometheus for 15 minutes**
    - Error rate: < 0.1%
    - p95 latency: < 2000ms
    - Ingestion throughput: > 10k events/min

---

## Rollback

### Immediate Rollback (if 5xx > 1% or login broken)

```bash
# Frontend
vercel rollback

# Backend services
kubectl rollout undo deployment/ingestion -n regengine
kubectl rollout undo deployment/admin -n regengine
kubectl rollout undo deployment/compliance -n regengine
kubectl rollout undo deployment/graph -n regengine

# Database (RLS migration)
psql -f migrations/rls_sysadmin_audit_revert.sql

# NetworkPolicies
kubectl delete networkpolicy --all -n regengine
```

---

## Escalation

- **Issue occurs during deploy:** Stop deployment, assess impact, notify Christopher
- **5xx errors or timeouts:** Rollback immediately (see above)
- **Database migration fails:** Contact Christopher for manual recovery
- **Production unavailable > 5 min:** Activate full incident response

---

## Post-Deploy

- [ ] Error rate nominal (< 0.1% 5xx)
- [ ] p95 latency within SLO (< 2000ms)
- [ ] Ingestion throughput stable (10k+ events/min)
- [ ] Update CHANGELOG.md
- [ ] Close related GitHub issues
- [ ] Schedule 24-hour review checkpoint
