# Security Boundaries

RegEngine handles tenant-scoped food traceability data. The security model is built around preventing cross-tenant data access, rejecting invalid writes before persistence, and retaining audit evidence for operational and regulatory review.

## Tenant Boundary

- All customer data is tenant-scoped.
- Cross-tenant reads are forbidden.
- Cross-tenant writes are forbidden.
- Tenant context must come from authenticated request context, trusted service context, or validated server-side mappings.
- Client-supplied tenant identifiers must not override authenticated tenant context.

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

## Administrative Boundary

- Tenant, user, role, API-key, and audit-log operations are administrative surfaces.
- Administrative writes must be audit logged.
- Privileged routes must require explicit permissions or trusted internal service credentials.

## Integration Boundary

- Integrations may submit data only through validated ingestion paths.
- Integrations must not bypass tenant isolation.
- Prototype or non-FSMA integrations must remain outside the production surface until promoted.

## Operational Boundary

- Health and readiness probes may be public only when they expose no tenant data or secrets.
- Metrics and observability must not emit secrets.
- Logs must not contain API keys, passwords, raw tokens, or cross-tenant data leakage.

