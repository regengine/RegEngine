# Authorization Findings Fix Cross-Reference

This document consolidates the multi-agent review of `AUTHORIZATION_BOUNDARY_TEST_REPORT.md`, the frontend auth middleware fixes, backend boundary evidence, and the authenticated screen-state guardrail.

Status values:

- `Fixed`: code changed and focused tests added.
- `Verified-Pass`: existing implementation and tests support the report outcome.
- `Needs Evidence`: implementation may be acceptable, but direct runnable evidence is missing or incomplete.
- `Blocked`: cannot be verified in this environment.

## Findings

| ID | Status | Severity | Owner | Fix / evidence | Tests / verification | Residual risk |
|---|---|---:|---|---|---|---|
| AUTHZ-001 | Fixed | Medium | Redirect/session agent | `frontend/src/proxy.ts` now builds `/login` redirects from a clean URL and sets `next` to `pathname + search`, so original query parameters are preserved inside `next` instead of leaking as top-level login params. `frontend/src/app/login/LoginClient.tsx` canonicalizes `next` with same-origin checks, rejects `/login` loops, backslashes, control chars, `https://...`, and `//...`. `frontend/src/app/auth/callback/route.ts` applies the same safe-next pattern to OAuth callbacks. | `npm --prefix frontend run test:run -- src/__tests__/proxy-auth-boundary.test.ts src/__tests__/api/proxy-authz.test.ts src/__tests__/auth/login.test.tsx src/__tests__/auth/callback-route.test.ts` -> 4 files / 43 tests passed. Full frontend suite -> 78 files / 503 passed / 4 skipped. | None known for the covered redirect paths. |
| AUTHZ-002 | Fixed for Supabase-backed production path | High frontend admin / Medium backend SoT | Revocation freshness agent | `frontend/src/proxy.ts` no longer treats JWT `tenant_status`, JWT `is_sysadmin`, or Supabase `user_metadata` as authoritative when Supabase is configured. Tenant status is read from `tenants.status`; sysadmin is read from `users.is_sysadmin` with `developer_profiles.is_sysadmin` fallback for Supabase-auth IDs. Both use in-memory LRU caches capped at 60 seconds and expire on `Date.now() >= expiresAt`. Lookup errors or missing tenant rows fail closed through login/config handling or dashboard redirect. | `src/__tests__/api/proxy-authz.test.ts` covers stale JWT sysadmin, stale JWT tenant status, stale Supabase tenant metadata, and stale Supabase sysadmin metadata. `src/__tests__/proxy-auth-boundary.test.ts` asserts the same Supabase freshness contract. Full frontend suite -> 78 files / 503 passed / 4 skipped. | JWT-only/no-Supabase deployments still fall back to token claims. The production assumption is that Supabase config is present; absence should be treated as deployment misconfiguration. |

## Boundary Matrix

| ID | Status | Cross-reference | Evidence |
|---|---|---|---|
| BM-01 Logged-out direct URL | Fixed | AUTHZ-001 | `src/__tests__/api/proxy-authz.test.ts` asserts `/dashboard/settings?tab=team&mode=edit` redirects to `/login?next=/dashboard/settings?...` with no top-level `tab` / `mode`. |
| BM-02 Wrong-tenant direct URL | Verified-Pass | Backend tenant path guards | `services/admin/tests/test_compliance_routes_idor.py`, `services/admin/tests/test_compliance_service_sync_tenant_isolation.py`, ingestion authz tests, and FSMA tenant trust tests cover tenant mismatch rejection. |
| BM-03 IDOR UUID swaps | Verified-Pass | Tenant-scoped lookups | User role and compliance alert tests reject cross-tenant IDs. Numeric increment/decrement is not applicable to the covered UUID-shaped resources. |
| BM-04 Forged body `user_id` | Verified-Pass | Authenticated actor stamping | `services/admin/tests/test_compliance_alert_actor_binding.py` proves alert action requests do not accept client-supplied `user_id` and stamp the session user. |
| BM-05 Role escalation | Verified-Pass | Admin-only endpoints | `services/admin/tests/test_p0_security_hardening.py` now collects and passes, proving hardcoded `X-Admin-Key: admin` is rejected and an admin key is required. `services/admin/tests/test_tenant_settings_routes.py` covers tenant role-gated settings and sysadmin-only partner status, and `services/admin/tests/test_user_routes.py` rejects cross-tenant role assignment. |
| BM-06 Mass assignment `/users/me` | Verified-Pass | Route absent / settings allowlists | `services/admin/tests/test_authz_boundary_surface.py` asserts no mutating `/users/me` surface is mounted. `services/admin/tests/test_tenant_settings_routes.py` covers allowlisted tenant settings updates and blocked-key stripping. |
| BM-07 GraphQL / REST field auth | Verified-Pass | REST-only field allowlists | `services/admin/tests/test_authz_boundary_surface.py` asserts no GraphQL route is mounted. `services/admin/tests/test_user_routes.py` locks the tenant user-list response fields and excludes password/MFA/session/token material. |
| BM-08 Download / signed URL tampering | Verified-Pass | Authenticated exports/downloads | FDA export and invoice PDF tests reject cross-tenant access. `services/admin/tests/test_data_export_1094.py` asserts account export does not inline presigned, signed, S3, or download URL material. |
| BM-09 Stale permissions after revocation | Fixed frontend / Verified backend primitives | AUTHZ-002 | Frontend middleware has direct stale-claim tests. Backend JTI, token-version, tenant refresh, and DB-backed permission checks remain covered by existing auth hardening tests. |
| BM-10 Password reset token A vs B | Verified-Pass | Recovery-token ownership | `services/admin/tests/test_reset_password_token_scope.py` covers recovery-token scope, freshness, replay rejection, and token-derived target user. |

## Screen-State Cross-Reference

| State | Current evidence | Status |
|---|---|---|
| 401 expired session | Middleware redirects to login with preserved `next` and `error=session_expired`; login shows the expired-session message. | Fixed for middleware/login path. |
| 403 permission revoked | `/sysadmin` revocation freshness now redirects away from the admin surface; backend role gates use DB-backed permission checks. | Covered for authz finding; page-level 403 UI coverage remains feature-specific. |
| 429 rate limited | Documentation requires Retry-After/backoff feedback. Existing guardrail does not simulate rate limits. | Needs Evidence. |
| Validation errors | Matrix records required behavior, but page-specific inline validation tests must own actual payload rendering. | Needs Evidence per feature. |
| Partial failure | Matrix records required behavior, but page/widget tests must prove partial data remains visible when one collection fails. | Needs Evidence per feature. |
| Optimistic rollback | Only applicable where a screen has a true optimistic mutation. Matrix rows without optimistic writes should stay `N/A`. | Needs Evidence per optimistic feature. |

## Fresh Verification

```bash
npm --prefix frontend run test:run -- \
  src/__tests__/proxy-auth-boundary.test.ts \
  src/__tests__/api/proxy-authz.test.ts \
  src/__tests__/auth/login.test.tsx \
  src/__tests__/auth/callback-route.test.ts
```

Result: 4 test files passed, 43 tests passed.

```bash
npm --prefix frontend run test:run -- \
  src/__tests__/api/proxy-sanitization.test.ts \
  src/__tests__/pages/authenticated-screen-states.test.ts
```

Result: 2 test files passed, 44 tests passed.

```bash
npm --prefix frontend run test:run
```

Result: 78 test files passed, 503 tests passed, 4 skipped.

```bash
npm --prefix frontend run lint
```

Result: exit 0, with 59 existing warnings and no errors.

```bash
pytest services/admin/tests/test_compliance_routes_idor.py \
  services/admin/tests/test_reset_password_token_scope.py \
  services/admin/tests/test_compliance_alert_actor_binding.py \
  services/admin/tests/test_tenant_settings_routes.py \
  services/admin/tests/test_get_current_user_tenant_source.py \
  services/admin/tests/test_check_revoked_async.py -q
```

Result: 91 passed.

```bash
pytest services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant \
  services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant_via_header \
  services/ingestion/tests/test_epcis_tenant_isolation.py -q
```

Result: 9 passed.

```bash
pytest services/ingestion/tests/test_stripe_billing_router.py::test_create_checkout_reuses_existing_customer_id_and_records_session \
  services/ingestion/tests/test_stripe_billing_router.py::test_invoice_pdf_rejects_cross_tenant_invoice -q
```

Result: 2 passed.

```bash
pytest services/ingestion/tests/test_authz_1342.py::TestRequirePermission::test_cross_tenant_403 \
  services/ingestion/tests/test_authz_1342.py::TestRequirePermission::test_cross_tenant_header_403 \
  services/ingestion/tests/test_authz_1342.py::TestRequirePermission::test_conflicting_query_and_header_400 -q
```

Result: 3 passed.

```bash
pytest services/admin/tests/test_permission_checker_sysadmin_tenant_context_1065.py \
  services/shared/tests/test_permissions.py \
  services/admin/tests/test_user_routes.py::TestListUsers_Issue1341::test_returns_400_when_no_tenant_context \
  services/admin/tests/test_user_routes.py::TestUpdateUserRole_Issue1341::test_returns_404_when_user_not_in_tenant -q
```

Result: 8 passed.

```bash
pytest services/admin/tests/test_p0_security_hardening.py -q
```

Result: 3 passed.

```bash
pytest services/admin/tests/test_authz_boundary_surface.py \
  services/admin/tests/test_p0_security_hardening.py \
  services/admin/tests/test_user_routes.py::TestListUsers_Issue1341::test_user_response_model_exposes_only_tenant_admin_fields \
  services/admin/tests/test_data_export_1094.py::TestExportPersonalData::test_export_does_not_include_presigned_download_urls -q
```

Result: 7 passed.

```bash
pytest services/admin/tests/test_tenant_settings_routes.py \
  services/admin/tests/test_user_routes.py::TestUpdateUserRole_Issue1341::test_returns_400_when_role_belongs_to_another_tenant \
  services/ingestion/tests/test_stripe_billing_router.py::test_invoice_pdf_rejects_cross_tenant_invoice -q
```

Result: 31 passed.

The authenticated screen-state guardrail remains useful for route documentation and loading/error fallback wiring, but it is intentionally not counted as proof of every simulated API failure mode. See `docs/engineering/AUTHENTICATED_SCREEN_STATES.md`.
