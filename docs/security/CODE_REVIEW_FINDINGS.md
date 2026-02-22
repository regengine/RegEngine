# Security Code Review Findings Log

This document tracks critical security findings and their remediation status for the RegEngine platform.

## Audit: "Triple Threat" Tenant Isolation Review
**Date:** 2026-02-21
**Auditor:** Bot-Security
**Status:** ✅ RESOLVED

### Finding 1: Header Spoofing Vulnerability (Confused Deputy)
- **Severity:** CRITICAL
- **Location:** `services/shared/middleware/tenant_context.py`
- **Description:** Middleware accepted `X-RegEngine-Tenant-ID` without authentication, allowing unauthenticated attackers to spoof tenant context.
- **Remediation:** 
  1. Modified `_extract_tenant_id` to ignore the header unless a valid `X-RegEngine-Internal-Secret` is present.
  2. Configured Nginx gateway to strip `X-RegEngine-Tenant-ID` from all external ingress traffic.
- **Verification:** Unit test `tests/security/test_header_remediation.py` verified that unauthenticated headers return 401/None, while authenticated internal headers are accepted.
- **Status:** RESOLVED (Commit: `ff624db`)

### Finding 2: Insecure RLS Fallback Design (Fail-Open)
- **Severity:** CRITICAL
- **Location:** `services/admin/migrations/V27__rls_core_security_tables.sql`
- **Description:** RLS policies used `COALESCE` with a fallback sandbox UUID, which could lead to data leakage if application context was lost.
- **Remediation:** 
  1. Deployed migration `V28__fix_rls_fail_closed.sql` to remove all `COALESCE` fallbacks.
  2. Policies now explicitly evaluate to `FALSE` if `app.tenant_id` is missing.
- **Verification:** Manual SQL audit confirmed removal of fallbacks and enforcement of `FORCE ROW LEVEL SECURITY` across 15 tables.
- **Status:** RESOLVED (Commit: `ff624db`)

---

## Future Directives
- **SAST:** Continuous Semgrep scanning is integrated into `scripts/security/sast_semgrep.sh`.
- **DAST:** ZAP baseline scans are scheduled daily.
- **Regression:** `tests/security/test_header_remediation.py` is now a permanent part of the security test suite.
