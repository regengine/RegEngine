# SOC 2 Type I Preparation — Evidence Collection Checklist

**Status:** Kickoff document · Q2 2026 target  
**Scope:** SOC 2 Type I (Security, Availability, Confidentiality)

---

## 1. Trust Service Criteria Mapping

### CC1 — Control Environment

| # | Control | RegEngine Status | Evidence |
|---|---------|-----------------|----------|
| 1.1 | Organizational structure documented | ✅ Exists | `README.md`, org chart |
| 1.2 | Code of conduct / ethics policy | ❌ Gap | Need formal policy document |
| 1.3 | Board / management oversight | ⚠️ Partial | Solo founder — document governance process |

### CC2 — Communication & Information

| # | Control | RegEngine Status | Evidence |
|---|---------|-----------------|----------|
| 2.1 | Security policies communicated to staff | ⚠️ Partial | Need formal security handbook |
| 2.2 | External communication of commitments | ✅ Exists | ToS, Privacy Policy at `/legal` |

### CC3 — Risk Assessment

| # | Control | RegEngine Status | Evidence |
|---|---------|-----------------|----------|
| 3.1 | Risk identification process | ✅ Exists | `tech_debt_register`, gap analysis docs |
| 3.2 | Fraud risk assessment | ❌ Gap | Need formal assessment |
| 3.3 | Change management risk evaluation | ⚠️ Partial | PR reviews exist, need formal process |

### CC5 — Control Activities

| # | Control | RegEngine Status | Evidence |
|---|---------|-----------------|----------|
| 5.1 | Logical access controls | ✅ Exists | RLS policies, API key auth, tenant isolation |
| 5.2 | Infrastructure security | ✅ Exists | Docker isolation, CORS, gateway config |
| 5.3 | Change management controls | ⚠️ Partial | GitHub PRs, CI/CD — need approval gates |
| 5.4 | Data classification | ❌ Gap | Need data classification policy |

### CC6 — Logical & Physical Access

| # | Control | RegEngine Status | Evidence |
|---|---------|-----------------|----------|
| 6.1 | User provisioning / deprovisioning | ✅ Exists | Tenant management, API key lifecycle |
| 6.2 | Authentication mechanisms | ✅ Exists | API keys, JWT, bypass tokens for test |
| 6.3 | Encryption at rest | ✅ Exists | Supabase managed encryption |
| 6.4 | Encryption in transit | ✅ Exists | TLS/HTTPS enforced |
| 6.5 | Physical access controls | ✅ N/A | Cloud-managed (Supabase, Vercel) |

### CC7 — System Operations

| # | Control | RegEngine Status | Evidence |
|---|---------|-----------------|----------|
| 7.1 | Monitoring & alerting | ⚠️ Partial | Sentry (frontend), health endpoints — need backend APM |
| 7.2 | Incident response plan | ❌ Gap | Need formal IR plan |
| 7.3 | Backup & recovery procedures | ⚠️ Partial | Supabase daily backups — need documented RTO/RPO |
| 7.4 | Vulnerability management | ✅ Exists | `npm audit`, dependency scanning, security tests |

### CC8 — Change Management

| # | Control | RegEngine Status | Evidence |
|---|---------|-----------------|----------|
| 8.1 | Change request process | ⚠️ Partial | GitHub Issues/PRs — need formal CAB |
| 8.2 | Testing before deployment | ✅ Exists | CI tests, boundary tests, build verification |
| 8.3 | Rollback procedures | ⚠️ Partial | Vercel instant rollback — need backend rollback docs |

### CC9 — Risk Mitigation

| # | Control | RegEngine Status | Evidence |
|---|---------|-----------------|----------|
| 9.1 | Vendor risk management | ⚠️ Partial | Need vendor assessment for Supabase, Vercel, Stripe |
| 9.2 | Business continuity plan | ❌ Gap | Need BCP document |

---

## 2. Gap Summary

| Priority | Gap | Q2 Action |
|----------|-----|-----------|
| **P0** | Incident Response Plan | Draft IR plan with escalation matrix |
| **P0** | Data Classification Policy | Define tiers (Public, Internal, Confidential, Restricted) |
| **P1** | Risk Assessment (formal) | Annual risk assessment process |
| **P1** | Business Continuity Plan | Document RTO/RPO, failover procedures |
| **P1** | Security Handbook | Consolidate existing security docs |
| **P2** | Vendor Risk Assessments | Assess Supabase, Vercel, Stripe, Redpanda |
| **P2** | Change Advisory Board | Formalize approval gates for production changes |
| **P2** | Code of Conduct | Draft organizational ethics policy |

---

## 3. Existing Evidence Inventory

These artifacts can be provided to auditors as-is:

- **RLS Policies:** 32-file framework verified via adversarial tests
- **API Authentication:** API key lifecycle management, tenant isolation
- **Encryption:** TLS in transit, Supabase-managed encryption at rest
- **CI/CD Pipeline:** GitHub Actions with build, test, security scanning
- **Monitoring:** Sentry frontend, `/health` endpoints (100% service coverage)
- **Security Testing:** Boundary tests (SSRF, rate limiting), dependency scanning
- **Legal:** Terms of Service, Privacy Policy
- **Technical Docs:** Cross-database dependencies, architecture docs

---

## 4. Next Steps

1. Engage SOC 2 readiness consultant (Q2 budget item)
2. Draft P0 gap documents (IR Plan, Data Classification)
3. Consolidate evidence into shared audit folder
4. Select audit firm for Type I examination
