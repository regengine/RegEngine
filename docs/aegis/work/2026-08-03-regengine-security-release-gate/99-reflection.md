# Reflection

## Outcome

The confirmed shared administrative credential was removed from the active
source contract, and tenant isolation became a measurable database-role,
policy, route, and test boundary. The work closes as `needs-verification`, not
as a production security approval.

## What materially changed the design

- The original router proposal included `supplier_validation`, but its IDs do
  not map through a migrated tenant-scoped key to canonical supplier/CTE data.
  Disabling it was safer than pretending route-level authentication supplied a
  storage boundary.
- Merely making runtime roles NOBYPASSRLS was insufficient. Adversarial
  mutations exposed owner, `SET ROLE`, incoming membership, exact-policy, and
  checkout rollback-resurrection false-greens; the final canary checks all of
  them.
- The production Python path could load both `shared.tenant_context` and
  `services.shared.tenant_context`, creating two ContextVars and listeners.
  Canonical imports plus an isolated import-identity test closed that gap.
- Raw psycopg autocommit made transaction-local tenant context ineffective.
  Each operation now binds its tenant and executes inside one transaction.

## Evidence discipline

Source tests prove contracts, not deployment. Existing Vercel/Railway state was
inspected read-only and intentionally recorded as failing/old. Candidate SHAs
and deployment IDs remain null, and the sanitized record remains
`not_approved`.

## Remaining work

Provision the dedicated staging roles and callers, deploy the candidate, then
run the generated route inventory through the real pooler, Redis replicas,
WebAuthn/SSO provider, two disposable tenants, enumeration timing, CSRF/SSRF
canary, and deployment-bound public-document checks. Only that evidence can
change the release verdict.
