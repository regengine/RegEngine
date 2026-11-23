# Security Boundaries

RegEngine handles tenant-scoped food traceability data. The security model is built around preventing cross-tenant data access, rejecting invalid writes before persistence, and retaining audit evidence for operational and regulatory review.

## Tenant Boundary

- All customer data is tenant-scoped.
- Cross-tenant reads are forbidden.
- Cross-tenant writes are forbidden.
- Tenant context must come from authenticated request context, trusted service context, or validated server-side mappings.
- Client-supplied tenant identifiers must not override authenticated tenant context.
- Anonymous database roles must not read `public.tenants` or `public.product_catalog`. Authenticated client reads of those tables are limited to the caller's own memberships (v144, revision `d8f3a1c6b902`). The revision is in source and is not authorization to apply it in production. See `docs/operations/rls_deployment_runbook.md`.

## Persistence Boundary

- Writes must pass schema validation before persistence.
- FSMA CTE/KDE evidence must flow through canonical persistence.
- Evidence and administrative audit surfaces must preserve tamper-evident hash or audit chains where implemented.
- FDA export must be generated from stored tenant-scoped evidence, not from untrusted request payloads.

## Authentication Boundary

- External access requires explicit authentication.
- API-key and JWT validation must fail closed outside explicitly configured development or test environments.
- Development auth fallbacks are not production controls.
- Supabase session state and internal RegEngine JWT handling are under consolidation; route behavior must be verified by tests, not assumed from client state.
- `POST /v1/auth/accept-invite` is the pre-auth onboarding exception. It resolves a still-usable invite by token hash, binds that invite's tenant, and arms global identity context only for user lookup/create and passwordless identity provisioning (two `auth-bootstrap` arms, each disarmed in `finally`). New users are not sysadmins. Every unusable invite state returns HTTP 400 `Invite is not usable`.

## Administrative Boundary

- Tenant, user, role, API-key, and audit-log operations are administrative surfaces.
- Administrative writes must be audit logged.
- Privileged routes must require explicit permissions or trusted internal service credentials.

## Integration Boundary

- Integrations may submit data only through validated ingestion paths.
- Integrations must not bypass tenant isolation.
- Prototype or non-FSMA integrations must remain outside the production surface until promoted.

### B2B exchange (downstream KDE sharing)

- `POST /api/v1/exchange/send` shares a sender's **own** shipping KDE evidence with a sender-chosen destination tenant. A sender can never read or transmit another tenant's data; `/exchange/receive` is scoped to the caller's own tenant.
- The destination (`receiver_tenant_id`) is **format-validated** (1–64 alphanumeric/hyphen/underscore) but is intentionally **not consent-gated** and **not existence-checked**. An existence check is deliberately avoided because it would expose a tenant-enumeration oracle.
- **Accepted risk:** a sender may stage a package addressed to a tenant that has not opted in; that tenant only ever observes it by polling `/exchange/receive`, and no cross-tenant *read* is possible. A receiver consent/opt-in model is a future product decision, not a current control.

## Operational Boundary

- Health and readiness probes may be public only when they expose no tenant data or secrets.
- Metrics and observability must not emit secrets.
- Logs must not contain API keys, passwords, raw tokens, or cross-tenant data leakage.
