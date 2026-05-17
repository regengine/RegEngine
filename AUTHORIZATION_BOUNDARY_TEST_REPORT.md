# Authorization Boundary Test Report

Scope: RegEngine admin API, ingestion API tenant gates, and Next.js authenticated app middleware.

Remediation status: all findings from this original test report have been worked and now pass in the current working tree. See `AUTHORIZATION_FIX_CROSS_REFERENCE.md` for the finding-to-fix matrix, exact curl reproductions, and verification commands.

Test principals used in the curl examples:

```bash
export API='http://127.0.0.1:8000'
export INGESTION_API='http://127.0.0.1:8001'
export FRONTEND='http://127.0.0.1:3100'

export USER_A_EMAIL='user-a+authz@example.test'
export USER_A_PASSWORD='Trace204!UserA-2026'
export USER_B_EMAIL='user-b+authz@example.test'
export USER_B_PASSWORD='Trace204!UserB-2026'
export ADMIN_EMAIL='admin+authz@example.test'
export ADMIN_PASSWORD='Trace204!Admin-2026'

export TENANT_A='11111111-1111-1111-1111-111111111111'
export TENANT_B='22222222-2222-2222-2222-222222222222'
export USER_A_ID='00000000-0000-0000-0000-0000000000a1'
export USER_B_ID='00000000-0000-0000-0000-0000000000b2'
export ALERT_A_ID='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
export ALERT_B_ID='bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
```

Create the test accounts in a fresh or seeded environment:

```bash
curl -si -X POST "$API/auth/signup" \
  -H 'Content-Type: application/json' \
  --data '{"email":"user-a+authz@example.test","password":"Trace204!UserA-2026","tenant_name":"Tenant A Authz"}'

curl -si -X POST "$API/auth/signup" \
  -H 'Content-Type: application/json' \
  --data '{"email":"user-b+authz@example.test","password":"Trace204!UserB-2026","tenant_name":"Tenant B Authz"}'

# Only works when bootstrapping an empty environment. In a populated
# environment, create the sysadmin through the seed/admin fixture path.
curl -si -X POST "$API/auth/register" \
  -H 'Content-Type: application/json' \
  --data '{"email":"admin+authz@example.test","password":"Trace204!Admin-2026","tenant_name":"Admin Tenant Authz"}'
```

Capture tokens:

```bash
export USER_A_TOKEN="$(curl -s -X POST "$API/auth/login" -H 'Content-Type: application/json' --data '{"email":"user-a+authz@example.test","password":"Trace204!UserA-2026"}' | jq -r '.access_token')"
export USER_B_TOKEN="$(curl -s -X POST "$API/auth/login" -H 'Content-Type: application/json' --data '{"email":"user-b+authz@example.test","password":"Trace204!UserB-2026"}' | jq -r '.access_token')"
export ADMIN_TOKEN="$(curl -s -X POST "$API/auth/login" -H 'Content-Type: application/json' --data '{"email":"admin+authz@example.test","password":"Trace204!Admin-2026"}' | jq -r '.access_token')"
```

## Findings

### AUTHZ-001: Login redirect does not preserve the full destination query string

Severity: Medium

Logged-out access redirects to `/login`, but middleware writes only the pathname into `next`. The original query string remains as top-level login parameters and is not used by `LoginClient`, which reads only `next` before routing after login. The final post-login destination loses the original query string.

Exact reproduction:

```bash
curl -si 'http://127.0.0.1:3100/dashboard/settings?tab=team&mode=edit' | sed -n '1,15p'
```

Observed:

```http
HTTP/1.1 307 Temporary Redirect
location: /login?tab=team&mode=edit&next=%2Fdashboard%2Fsettings
```

Expected:

```http
location: /login?next=%2Fdashboard%2Fsettings%3Ftab%3Dteam%26mode%3Dedit
```

Second reproduction:

```bash
curl -si 'http://127.0.0.1:3100/requests/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?view=timeline' | sed -n '1,15p'
```

Observed:

```http
HTTP/1.1 307 Temporary Redirect
location: /login?view=timeline&next=%2Frequests%2Faaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa
```

Evidence:

- `frontend/src/proxy.ts` sets `next` to `pathname` only.
- `frontend/src/app/login/LoginClient.tsx` reads `searchParams.get('next')` and routes to that value only.

### AUTHZ-002: Frontend sysadmin and tenant-status revocation can remain stale for more than 60 seconds

Severity: High for frontend admin surfaces, Medium if backend remains the source of truth for mutations

The frontend `/sysadmin` middleware trusts `is_sysadmin` embedded in the custom JWT. A user whose sysadmin role is revoked mid-session can continue to load `/sysadmin` until the JWT expires. Comments in the middleware describe a default token freshness bound of 60 minutes, which does not meet the requested 60-second stale-permission requirement. The Supabase fallback path also caches sysadmin and tenant-status checks for 10 minutes.

Exact local reproduction against the dev frontend started with `JWT_SIGNING_KEY=test-secret`:

```bash
read SYSADMIN_TOKEN USER_TOKEN < <(python3 - <<'PY'
import base64, hashlib, hmac, json, time

secret = b'test-secret'

def enc(obj):
    return base64.urlsafe_b64encode(
        json.dumps(obj, separators=(',', ':')).encode()
    ).rstrip(b'=').decode()

def mint(is_sysadmin):
    header = {'alg': 'HS256', 'typ': 'JWT'}
    payload = {
        'sub': '00000000-0000-0000-0000-0000000000a1',
        'email': 'user-a@example.test',
        'tenant_id': '11111111-1111-1111-1111-111111111111',
        'tid': '11111111-1111-1111-1111-111111111111',
        'tenant_status': 'active',
        'aud': 'regengine-api',
        'iss': 'regengine-admin',
        'exp': int(time.time()) + 3600,
        'jti': 'stale-sysadmin-demo-' + str(is_sysadmin),
        'is_sysadmin': is_sysadmin,
    }
    msg = f'{enc(header)}.{enc(payload)}'
    sig = base64.urlsafe_b64encode(
        hmac.new(secret, msg.encode(), hashlib.sha256).digest()
    ).rstrip(b'=').decode()
    return msg + '.' + sig

print(mint(True), mint(False))
PY
)

curl -si --cookie "re_access_token=$SYSADMIN_TOKEN" \
  'http://127.0.0.1:3100/sysadmin' | sed -n '1,16p'

curl -si --cookie "re_access_token=$USER_TOKEN" \
  'http://127.0.0.1:3100/sysadmin' | sed -n '1,16p'
```

Observed:

```http
# is_sysadmin=true token
HTTP/1.1 200 OK

# is_sysadmin=false token
HTTP/1.1 307 Temporary Redirect
location: /dashboard
```

Production-style stale-permission reproduction:

```bash
# 1. Login while the account is sysadmin.
export ADMIN_TOKEN="$(curl -s -X POST "$API/auth/login" \
  -H 'Content-Type: application/json' \
  --data '{"email":"admin+authz@example.test","password":"Trace204!Admin-2026"}' | jq -r '.access_token')"

# 2. Revoke sysadmin in the database or admin fixture while keeping the session.
psql "$ADMIN_DATABASE_URL" \
  -c "update users set is_sysadmin = false where email = 'admin+authz@example.test';"

# 3. Retry within 60 seconds with the original cookie/token.
curl -si --cookie "re_access_token=$ADMIN_TOKEN" "$FRONTEND/sysadmin" | sed -n '1,16p'
```

Expected: redirect or 403 within 60 seconds.

Current behavior implied by the middleware: access can remain allowed until JWT expiry, or for 10 minutes on the cached Supabase fallback path.

Evidence:

- `frontend/src/proxy.ts` reads `payload.is_sysadmin === true` for `/sysadmin`.
- `frontend/src/proxy.ts` comments state tenant status from JWT is stale for up to one token lifetime.
- `frontend/src/proxy.ts` sets sysadmin and tenant-status fallback caches to 10 minutes.

## Boundary Matrix

### 1. Logged-out direct URL access

Outcome: Finding AUTHZ-001 for query-string preservation. Path-only URLs do redirect to login with `next`.

Exact curl:

```bash
curl -si 'http://127.0.0.1:3100/dashboard/settings?tab=team&mode=edit' | sed -n '1,15p'
```

### 2. Wrong-tenant direct URL access

Outcome: Pass for covered backend tenant-path routes. Cross-tenant URL tenant IDs are rejected by `verify_path_tenant_matches` or tenant-aware lookups.

Exact curl:

```bash
curl -si "$API/v1/compliance/alerts/$TENANT_B/$ALERT_B_ID" \
  -H "Authorization: Bearer $USER_A_TOKEN" | sed -n '1,25p'
```

Expected: `403` or `404`, never `200`.

### 3. IDOR by incrementing or swapping IDs

Outcome: Pass for covered UUID resources and tenant-bound APIs. UUID swapping to another tenant produced `403` or `404`; numeric increment/decrement was not applicable to the covered UUID-shaped resources.

Exact curls:

```bash
curl -si "$API/v1/compliance/alerts/$TENANT_A/$ALERT_B_ID" \
  -H "Authorization: Bearer $USER_A_TOKEN" | sed -n '1,25p'

curl -si -X PATCH "$API/v1/admin/users/$USER_B_ID/role" \
  -H "Authorization: Bearer $USER_A_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"role_id":"00000000-0000-0000-0000-000000000099"}' | sed -n '1,25p'
```

Expected: `403` or `404`, never cross-tenant data.

### 4. Body claims another user's user_id

Outcome: Pass for compliance alert actions. The request model no longer accepts `user_id`, and the server stamps actions from the authenticated session user.

Exact curl:

```bash
curl -si -X POST "$API/v1/compliance/alerts/$TENANT_A/$ALERT_A_ID/acknowledge" \
  -H "Authorization: Bearer $USER_A_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"user_id":"00000000-0000-0000-0000-0000000000b2","notes":"attempted forged actor"}' \
  | sed -n '1,40p'
```

Expected: if the alert exists, the response actor is User A; otherwise `404`. It must never stamp User B.

### 5. Role escalation to admin-only endpoint

Outcome: Pass on covered backend endpoints. Tenant partner-status requires sysadmin, and admin-key management requires the admin master key rather than a user bearer token.

Exact curls:

```bash
curl -si -X PATCH "$API/v1/tenants/$TENANT_A/partner-status" \
  -H "Authorization: Bearer $USER_A_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"tier":"founding"}' | sed -n '1,25p'

curl -si "$API/v1/admin/keys" \
  -H "Authorization: Bearer $USER_A_TOKEN" | sed -n '1,25p'
```

Expected: `403` for partner-status; `401` or `403` for admin-key management.

### 6. Mass assignment to /users/me with role: admin

Outcome: No `/users/me` mutation endpoint was found. The closest tenant settings update path allowlists accepted keys and strips security/billing fields. This specific attack path is not exposed by the current route table.

Exact curl:

```bash
curl -si -X POST "$API/users/me" \
  -H "Authorization: Bearer $USER_A_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"role":"admin","is_sysadmin":true}' | sed -n '1,25p'
```

Expected: `404` or `405`; no role mutation.

### 7. GraphQL or REST field-level auth for another user's email

Outcome: No GraphQL endpoint was found. REST user email listing is tenant-scoped and guarded by `users.read`.

Exact curls:

```bash
curl -si "$API/v1/admin/users" \
  -H "Authorization: Bearer $USER_A_TOKEN" | sed -n '1,30p'

curl -si "$API/v1/admin/users" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | sed -n '1,60p'
```

Expected: normal User A receives `403` unless explicitly granted `users.read`; admin responses include only users in the active tenant context.

### 8. File downloads and signed URL tampering

Outcome: No public signed-download endpoint was found in the covered route surface. FDA exports are authenticated streaming responses; internal S3 presigned URLs are not exposed as a user-facing download API in the tested paths.

Exact curl for the authenticated streaming export path:

```bash
curl -si "$INGESTION_API/api/v1/fda/export?tenant_id=$TENANT_A&tlc=TLC-2026-001&format=csv" \
  -H "X-RegEngine-API-Key: $USER_A_API_KEY" | sed -n '1,40p'
```

Expected: authenticated tenant-scoped stream, not a reusable public signed URL. Cross-tenant `tenant_id=$TENANT_B` with User A credentials must return `403`.

### 9. Stale permissions after role revocation

Outcome: Finding AUTHZ-002 for frontend `/sysadmin` and cached frontend tenant-status/sysadmin checks. Backend permission checks use database role membership on each request for the covered API paths.

Exact curl: see AUTHZ-002.

### 10. Password reset token from User A against User B

Outcome: Pass in covered tests. `/auth/reset-password` derives the target user from the recovery-scoped Supabase token, requires a fresh recovery/OTP authentication method, and rejects normal password-session tokens.

Exact curls:

```bash
curl -si -X POST "$API/auth/reset-password" \
  -H "Authorization: Bearer $USER_A_RECOVERY_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"new_password":"NewPassw0rd!ForA","user_id":"00000000-0000-0000-0000-0000000000b2","email":"user-b+authz@example.test"}' \
  | sed -n '1,40p'

curl -si -X POST "$API/auth/reset-password" \
  -H "Authorization: Bearer $USER_A_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"new_password":"NewPassw0rd!ForA"}' | sed -n '1,40p'
```

Expected: the recovery token can only affect User A; normal password-session tokens return `401 Invalid or expired recovery token`.

## Verification Commands Run

```bash
pytest services/admin/tests/test_compliance_routes_idor.py \
  services/admin/tests/test_reset_password_token_scope.py \
  services/admin/tests/test_compliance_alert_actor_binding.py \
  services/admin/tests/test_tenant_settings_routes.py \
  services/admin/tests/test_get_current_user_tenant_source.py \
  services/admin/tests/test_check_revoked_async.py -q
```

Result: `91 passed`.

```bash
npm --prefix frontend test -- --run \
  src/__tests__/api/admin.test.ts \
  src/__tests__/api/proxy-sanitization.test.ts \
  src/__tests__/lib/permissions.test.ts \
  --reporter=dot
```

Result: `68 passed`.

```bash
pytest services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant \
  services/ingestion/tests/test_fda_export_router.py::test_export_denied_cross_tenant_via_header \
  services/ingestion/tests/test_epcis_tenant_isolation.py -q
```

Result: `9 passed`.

```bash
pytest services/ingestion/tests/test_stripe_billing_router.py::test_create_checkout_reuses_existing_customer_id_and_records_session \
  services/ingestion/tests/test_stripe_billing_router.py::test_invoice_pdf_rejects_cross_tenant_invoice -q
```

Result: `2 passed`.

```bash
pytest services/ingestion/tests/test_authz_1342.py::TestRequirePermission::test_cross_tenant_403 \
  services/ingestion/tests/test_authz_1342.py::TestRequirePermission::test_cross_tenant_header_403 \
  services/ingestion/tests/test_authz_1342.py::TestRequirePermission::test_conflicting_query_and_header_400 -q
```

Result: `3 passed`.

```bash
pytest services/admin/tests/test_permission_checker_sysadmin_tenant_context_1065.py \
  services/shared/tests/test_permissions.py \
  services/admin/tests/test_user_routes.py::TestListUsers_Issue1341::test_returns_400_when_no_tenant_context \
  services/admin/tests/test_user_routes.py::TestUpdateUserRole_Issue1341::test_returns_404_when_user_not_in_tenant -q
```

Result: `8 passed`.

One broader suite including `services/admin/tests/test_p0_security_hardening.py` did not collect in this local environment because the installed OpenTelemetry packages are incompatible:

```text
ImportError: cannot import name '_create_exp_backoff_generator' from opentelemetry.exporter.otlp.proto.common._internal
```
