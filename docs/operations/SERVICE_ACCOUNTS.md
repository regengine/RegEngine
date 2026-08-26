# Service Accounts Guide

Service accounts provide attributable, least-privilege access for automated
integrations. RegEngine does not use a shared administrative credential.

## Creating tenant API keys

A staff user creates, lists, and revokes live tenant keys through the browser
admin console. The user must have an active opaque session, `is_sysadmin=true`,
and a WebAuthn or SSO authentication method. Each action records the user,
session, target tenant, request, and source address.

The raw key is returned once. Store it in the caller's secret manager and send
it only in the `X-RegEngine-API-Key` header:

```bash
curl https://api.regengine.co/v1/labels/search \
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID"
```

`X-Tenant-ID` is an optional assertion. It must match the tenant bound to the
credential and is never an authentication mechanism.

## Tenant-provisioning workload key

Stripe onboarding is the only workload permitted to create a tenant without a
human browser session. Provision a tenantless database-backed key with exactly
the `internal.tenants.create` permission, an expiry of at most 90 days, and a
rate limit of at most 10 requests per minute. Store it as
`REGENGINE_TENANT_PROVISIONER_KEY` in the ingestion service.

```bash
curl -X POST https://admin.internal.regengine.co/v1/internal/tenants \
  -H "X-RegEngine-API-Key: $REGENGINE_TENANT_PROVISIONER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"Provisioned customer"}'
```

The internal route is excluded from public OpenAPI. Tenant-bound, expired,
revoked, or wrong-scope keys are rejected.

## Operational requirements

- Grant only the permissions the workload executes.
- Use a descriptive actor name tied to one workload and environment.
- Set an expiry and rotate before it lapses.
- Revoke the old credential after callers migrate.
- Monitor attributable success and denial audit records.
- Never place workload or tenant keys in browser-readable configuration.
