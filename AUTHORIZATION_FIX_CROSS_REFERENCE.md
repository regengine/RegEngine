# Authorization Findings Fix Cross-Reference

Source report: `AUTHORIZATION_BOUNDARY_TEST_REPORT.md`

| Boundary ID | Current Result | Fix Required | Fix Summary | Primary Files | Exact Curl | Tests | Reviewer |
|---|---|---|---|---|---|---|---|
| `AUTHZ-001` | Pass | Yes | Implemented full-destination login redirects: protected route redirects now encode pathname plus query inside `next`, while the login page keeps safe-next validation. | `frontend/src/proxy.ts`, `frontend/src/__tests__/proxy-auth-boundary.test.ts`, `frontend/src/__tests__/api/proxy-authz.test.ts`, `frontend/src/__tests__/auth/login.test.tsx` | `curl -si 'http://127.0.0.1:3100/dashboard/settings?tab=team&mode=edit' \| sed -n '1,15p'` | `npm --prefix frontend test -- --run src/__tests__/proxy-auth-boundary.test.ts src/__tests__/api/proxy-authz.test.ts src/__tests__/auth/login.test.tsx src/__tests__/api/proxy-sanitization.test.ts --reporter=dot` | Frontend Auth Agent |
| `AUTHZ-002` | Pass | Yes | Implemented fresh frontend authorization: `/sysadmin` no longer trusts stale JWT/user metadata and revalidates tenant/sysadmin state through 60s DB-backed checks; proxy admin capability now checks fresh backend role state instead of client-readable `re_user`. | `frontend/src/proxy.ts`, `frontend/src/lib/api-proxy.ts`, `frontend/src/app/api/review/items/route.ts`, `services/admin/app/auth_routes.py`, `services/admin/app/auth/schemas.py` | `curl -si "$FRONTEND/sysadmin" -H "Cookie: re_access_token=$STALE_SYSADMIN_TOKEN; sb-auth-token=present" \| sed -n '1,25p'` | `npm --prefix frontend test -- --run src/__tests__/proxy-auth-boundary.test.ts src/__tests__/api/proxy-authz.test.ts src/__tests__/api/proxy-sanitization.test.ts --reporter=dot` | Frontend Auth Agent |
| `1` | Pass | Yes | Same remediation as `AUTHZ-001`; direct logged-out access preserves the full destination in `?next=` for dashboard and request URLs. | `frontend/src/proxy.ts`, `frontend/src/__tests__/proxy-auth-boundary.test.ts` | `curl -si 'http://127.0.0.1:3100/requests/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?view=timeline' \| sed -n '1,15p'` | `npm --prefix frontend test -- --run src/__tests__/proxy-auth-boundary.test.ts --reporter=dot` | Frontend Auth Agent |
| `2` | Pass | Yes | Existing admin/FDA/EPCIS paths were tenant-bound; legacy ingestion team routes now reject path tenant IDs that differ from the authenticated API-key tenant. | `services/ingestion/app/team_mgmt.py`, `services/ingestion/app/webhook_compat.py`, `services/ingestion/tests/test_team_mgmt_authz.py` | `curl -si "$INGESTION_API/api/v1/team/$TENANT_B" -H "X-RegEngine-API-Key: $USER_A_API_KEY" -H "X-Tenant-ID: $TENANT_A" \| sed -n '1,25p'` | `pytest services/ingestion/tests/test_team_mgmt_authz.py services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant_via_header services/ingestion/tests/test_epcis_tenant_isolation.py -q` | Backend Auth/RBAC Agent |
| `3` | Pass | Yes | Existing UUID-swapping checks remain; admin user role assignment now rejects target roles owned by another tenant. | `services/admin/app/user_routes.py`, `services/admin/tests/test_user_routes.py` | `curl -si -X PATCH "$API/v1/admin/users/$USER_A_PEER_ID/role" -H "Authorization: Bearer $ADMIN_A_TOKEN" -H 'Content-Type: application/json' --data "{\"role_id\":\"$TENANT_B_ROLE_ID\"}" \| sed -n '1,25p'` | `pytest services/admin/tests/test_user_routes.py::TestUpdateUserRole_Issue1341::test_returns_400_when_role_belongs_to_another_tenant -q` | Backend Auth/RBAC Agent |
| `4` | Pass | Regression test only | Compliance alert actions continue to ignore body `user_id` and stamp the actor from the authenticated session. | `services/admin/app/compliance_routes.py`, `services/admin/app/compliance_service_sync.py`, `services/admin/tests/test_compliance_alert_actor_binding.py` | `curl -si -X POST "$API/v1/compliance/alerts/$TENANT_A/$ALERT_A_ID/acknowledge" -H "Authorization: Bearer $USER_A_TOKEN" -H 'Content-Type: application/json' --data '{"user_id":"00000000-0000-0000-0000-0000000000b2","notes":"attempted forged actor"}' \| sed -n '1,40p'` | `pytest services/admin/tests/test_compliance_alert_actor_binding.py -q` | Backend Auth/RBAC Agent |
| `5` | Pass | Yes | Reported admin endpoints were already gated; legacy team role mutation now requires admin API-key scope and a known role. | `services/ingestion/app/team_mgmt.py`, `services/ingestion/tests/test_team_mgmt_authz.py` | `curl -si -X PUT "$INGESTION_API/api/v1/team/$TENANT_A/$USER_A_ID/role?role=owner" -H "X-RegEngine-API-Key: $USER_A_READONLY_API_KEY" -H "X-Tenant-ID: $TENANT_A" \| sed -n '1,25p'` | `pytest services/ingestion/tests/test_team_mgmt_authz.py -q` | Backend Auth/RBAC Agent |
| `6` | Pass | Regression test only | No mutating `/users/me` endpoint exists; typed tenant settings mutations still allowlist accepted fields and reject privilege fields. | `services/admin/app/auth_routes.py`, `services/admin/app/tenant_settings_routes.py`, `services/admin/tests/test_tenant_settings_routes.py` | `curl -si -X POST "$API/users/me" -H "Authorization: Bearer $USER_A_TOKEN" -H 'Content-Type: application/json' --data '{"role":"admin","is_sysadmin":true}' \| sed -n '1,25p'` | `pytest services/admin/tests/test_tenant_settings_routes.py -q` | Backend Auth/RBAC Agent |
| `7` | Pass | Yes | Admin user email listing was already tenant-scoped; legacy team email listing now rejects cross-tenant API-key access. | `services/ingestion/app/team_mgmt.py`, `services/admin/app/user_routes.py`, `services/ingestion/tests/test_team_mgmt_authz.py` | `curl -si "$INGESTION_API/api/v1/team/$TENANT_B" -H "X-RegEngine-API-Key: $USER_A_API_KEY" -H "X-Tenant-ID: $TENANT_A" \| sed -n '1,25p'` | `pytest services/ingestion/tests/test_team_mgmt_authz.py services/admin/tests/test_user_routes.py::TestListUsers_Issue1341::test_returns_400_when_no_tenant_context -q` | Backend Auth/RBAC Agent |
| `8` | Pass | No | No public signed-download endpoint was found; FDA exports remain authenticated streaming responses and tenant conflicts reject. | `services/ingestion/app/fda_export/router.py`, `services/nlp/app/s3_loader.py`, `services/ingestion/tests/test_fda_export_router.py` | `curl -sS -D - -o /tmp/fda-a.csv "$INGESTION_API/api/v1/fda/export?tenant_id=$TENANT_A&tlc=TLC-2026-001&format=csv&allow_incomplete=true" -H "X-RegEngine-API-Key: $USER_A_API_KEY" -H "X-Tenant-ID: $TENANT_A" \| sed -n '1,40p'` | `pytest services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant_via_header -q` | Token/Reset/File Agent |
| `9` | Pass | Yes | Backend access tokens already checked live DB/token version; refresh sessions now also reject older session generations after reset/logout-all. | `services/admin/app/auth/refresh_router.py`, `services/admin/app/session_store.py`, `services/admin/tests/test_auth_cluster_hardening.py` | `read USER_A_TOKEN USER_A_REFRESH < <(curl -s -X POST "$API/auth/login" -H 'Content-Type: application/json' --data '{"email":"user-a+authz@example.test","password":"Trace204!UserA-2026"}' \| jq -r '.access_token, .refresh_token'); curl -si -X POST "$API/auth/logout-all" -H "Authorization: Bearer $USER_A_TOKEN" \| sed -n '1,30p'; curl -si -X POST "$API/auth/refresh" -H 'Content-Type: application/json' -H "Authorization: Bearer $USER_A_TOKEN" --data "{\"refresh_token\":\"$USER_A_REFRESH\"}" \| sed -n '1,30p'` | `pytest services/admin/tests/test_check_revoked_async.py services/admin/tests/test_auth_cluster_hardening.py::test_refresh_rejects_stale_session_token_version -q` | Token/Reset/File Agent |
| `10` | Pass | No | Password reset continues to derive the target account from the recovery-scoped Supabase token and rejects normal password-session tokens. | `services/admin/app/auth/reset_password_router.py`, `services/admin/tests/test_reset_password_token_scope.py` | `curl -si -X POST "$API/auth/reset-password" -H "Authorization: Bearer $USER_A_RECOVERY_TOKEN" -H 'Content-Type: application/json' --data '{"new_password":"Trace204!UserA-Reset-2026","user_id":"00000000-0000-0000-0000-0000000000b2","email":"user-b+authz@example.test"}' \| sed -n '1,40p'` | `pytest services/admin/tests/test_reset_password_token_scope.py -q` | Token/Reset/File Agent |

## P0 Suite Collection

The previous `test_p0_security_hardening.py` collection blocker is resolved in this working tree. OpenTelemetry packages are pinned to aligned versions in the repo lockfiles and the observability exporter imports now fail closed when optional exporter packages are unavailable or mismatched.

```bash
pytest services/admin/tests/test_p0_security_hardening.py --collect-only -q
```

Result: collected `3` tests.

```bash
pytest services/admin/tests/test_p0_security_hardening.py -q
```

Result: `3 passed`.

## Verification Run

Passed locally:

```bash
npm --prefix frontend test -- --run \
  src/__tests__/proxy-auth-boundary.test.ts \
  src/__tests__/api/proxy-authz.test.ts \
  src/__tests__/auth/login.test.tsx \
  src/__tests__/api/proxy-sanitization.test.ts \
  --reporter=dot
```

Result: `90 passed`.

```bash
pytest services/admin/tests/test_compliance_routes_idor.py \
  services/admin/tests/test_reset_password_token_scope.py \
  services/admin/tests/test_compliance_alert_actor_binding.py \
  services/admin/tests/test_tenant_settings_routes.py \
  services/admin/tests/test_get_current_user_tenant_source.py \
  services/admin/tests/test_check_revoked_async.py \
  services/admin/tests/test_auth_cluster_hardening.py::test_refresh_rejects_stale_session_token_version \
  services/admin/tests/test_user_routes.py::TestUpdateUserRole_Issue1341::test_returns_400_when_role_belongs_to_another_tenant -q
```

Result: passed.

```bash
pytest services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant \
  services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant_via_header \
  services/ingestion/tests/test_epcis_tenant_isolation.py \
  services/ingestion/tests/test_team_mgmt_authz.py -q
```

Result: `14 passed`.

```bash
pytest services/ingestion/tests/test_authz_1342.py::TestRequirePermission::test_cross_tenant_403 \
  services/ingestion/tests/test_authz_1342.py::TestRequirePermission::test_cross_tenant_header_403 \
  services/ingestion/tests/test_authz_1342.py::TestRequirePermission::test_conflicting_query_and_header_400 \
  services/ingestion/tests/test_stripe_billing_router.py::test_invoice_pdf_rejects_cross_tenant_invoice -q
```

Result: `4 passed`.
