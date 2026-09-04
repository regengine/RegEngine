# RegEngine Sandbox Provisioning Guide

Each design partner receives a disposable tenant, a tenant-bound API key, an
explicit expiry, and an agreed data-retention window. Do not use customer data
in a sandbox or release test.

## Required roles

- A WebAuthn/SSO-authenticated staff sysadmin creates and revokes tenant API
  keys through the browser admin console.
- The launch orchestrator may create a tenant only when it holds a tenantless
  database-backed key with exactly `internal.tenants.create`, an expiry of at
  most 90 days, and a rate limit of at most 10 requests per minute.
- The partner's API key is tenant-bound and cannot create tenants or keys.

## Provisioning sequence

1. Confirm the agreement, primary contact, use case, expiry, quota, and data
   deletion date.
2. Create the disposable tenant. When automation is used:

   ```bash
   curl -X POST "$REGENGINE_ADMIN_URL/v1/internal/tenants" \
     -H "X-RegEngine-API-Key: $REGENGINE_TENANT_PROVISIONER_KEY" \
     -H "Content-Type: application/json" \
     -d '{"name":"Acme design-partner sandbox"}'
   ```

3. A staff sysadmin signs in with WebAuthn/SSO and creates a tenant-bound key
   with only the required sandbox permissions. Set an expiry and a descriptive
   actor name.
4. Deliver the raw key once through the approved secret-sharing system. Record
   only its key ID in the partner tracker.
5. Seed synthetic fixtures using the partner key and its matching tenant
   assertion:

   ```bash
   curl -X POST "$REGENGINE_API_URL/v1/ingest/csv" \
     -H "X-RegEngine-API-Key: $PARTNER_API_KEY" \
     -H "X-Tenant-ID: $PARTNER_TENANT_ID" \
     -F "file=@synthetic-fsma-events.csv"
   ```

6. Run the two-tenant isolation gate before handoff. The partner tenant must
   never see identifiers or bytes from the control tenant.

## Rotation and closure

- Rotate tenant API keys before expiry through the high-assurance staff flow.
- Revoke the old key after the partner confirms migration.
- At program end, revoke every partner key, delete sandbox data under the
  approved retention procedure, and preserve only secret-free audit evidence.
- Rotate `REGENGINE_TENANT_PROVISIONER_KEY` within 90 days and verify it still
  has only `internal.tenants.create`.

## Troubleshooting

- `401`: credential missing, revoked, expired, or tenant-bound where a
  tenantless workload key is required.
- `403`: wrong permission, non-sysadmin staff session, or insufficient
  authentication assurance.
- `409`: tenant assertion conflicts with the credential-bound tenant.
- `429`: provisioning failure budget or request rate exceeded.
- `503`: Redis/authentication state could not be verified; retry only after the
  dependency is healthy. Never bypass the fail-closed control.
