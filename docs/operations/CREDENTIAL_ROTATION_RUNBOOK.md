# Credential Rotation Runbook

## Current authentication model

Human key management and tenant creation require an opaque browser session,
`is_sysadmin=true`, and WebAuthn or SSO high assurance. The former shared
administrative credential is retired and must be absent from Railway, Vercel,
local runtime configuration, and callers.

Automated tenant creation uses one tenantless database-backed workload key with
exactly `internal.tenants.create`. Tenant workloads use individually
attributable, tenant-bound API keys.

## Rotation order

1. Inventory the credential by key ID, actor name, scope, environment, expiry,
   and last use. Do not copy the raw value into a ticket or log.
2. Create the replacement through the high-assurance staff admin flow.
3. Store it in the target workload's secret manager.
4. Deploy the caller and confirm attributable successful use of the new key.
5. Revoke the old key and verify replay is denied.
6. Record deployment IDs, key IDs, commands, results, and verification time in
   the release evidence. Never record secret values.

For Stripe onboarding, rotate `REGENGINE_TENANT_PROVISIONER_KEY` at least every
90 days and verify that the replacement can call only
`POST /v1/internal/tenants`.

## JWT and session-key rotation

Rotate JWT signing material through the Redis-backed key registry. Confirm
both backend replicas observe the new active key and emergency revocation.
Logout, session revoke, and logout-all replay must fail on the next request.
A Redis or key-registry outage must return 503 rather than accepting an
unverified credential.

During the CAS-registry rollout, drain every replica running a pre-CAS build
before rotating or revoking signing keys. Older writers replace the Redis
snapshot with an unconditional `SET` and can race a current replica's CAS
mutation. Record the all-replicas-upgraded check in release evidence; only then
resume registry mutations.

## Retired-credential closeout

- Confirm the retired shared credential is absent from Railway and Vercel.
- Revoke its value wherever it was accepted historically.
- Confirm both correct and incorrect legacy header attempts are denied and
  rate-limited without logging the supplied value.
- Search active source, configuration, workflows, scripts, and documentation
  with the retired-credential guard in CI.
- Preserve historical incident material only under `docs/archive/` with an
  explicit historical warning.
