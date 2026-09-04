# ADR-004: Fail-Closed Security Release Boundary

**Status:** Accepted
**Date:** 2026-08-03
**Decision owner:** RegEngine engineering
**Supersedes:** The RLS-bypass decision in
[`docs/security/ADR-001-security-hardening-architecture.md`](../../security/ADR-001-security-hardening-architecture.md#decision-3-rls--defense-in-depth-with-sysadmin-bypass)

## Context

The public security review found one confirmed source-level control defect—a
shared administrative credential—and several controls whose source posture
could not establish deployed tenant isolation or revocation behavior. The
consolidated Railway process also mounted routers by default, used credentials
whose RLS posture could be inert, and had no immutable release-evidence record
covering the Vercel and Railway deployments together.

These boundaries are hard to reverse safely, surprising without an explicit
record, and carry a real availability-versus-security trade-off. The accepted
release plan therefore makes uncertainty a deployment failure for tenant
isolation, privileged authentication, revocation, and shared abuse throttles.

## Decision

### 1. Separate database duties without RLS bypass

The application uses three credentials:

- `DATABASE_URL` connects as the tenant runtime role `regengine`.
- `ADMIN_DATABASE_URL` connects as the audited control-plane runtime role
  `regengine_sysadmin`.
- `MIGRATIONS_DATABASE_URL` is the schema-owner credential and exists only in
  the migration runner.

Both runtime roles are `NOSUPERUSER NOBYPASSRLS`. Production startup verifies
both engines and aborts when enforcement is inert or unknown. This supersedes
ADR-001 Decision 3; a bypass-capable runtime role is not a supported rollback.

Runtime grants are a closed, caller-derived inventory rather than schema-wide
DML. The tenant role receives only the operations used by enabled data-plane
paths. The control-plane role receives only the tables, columns, sequences,
and functions used by attributable admin or worker callers. Disabled surfaces
receive no runtime or control-plane grants. Future tables and sequences do not
inherit runtime DML through default privileges.

`app.tenant_id` is a PostgreSQL custom GUC and can be set by a principal that
can issue arbitrary SQL. RLS therefore prevents accidental missing or
mismatched tenant context in trusted application flows; it does **not** contain
theft of `DATABASE_URL`, arbitrary SQL injection, or a compromised runtime
process that selects another tenant context. Per-tenant database principals or
a tenant-context primitive that ordinary callers cannot forge would be needed
for that stronger boundary and are outside this rollout. Release evidence and
security claims must preserve this limitation.

### 2. Make the HTTP surface allowlisted and executable as evidence

Production requires the exact `ENABLED_ROUTERS` set in
`server/router_policy.py`. Optional graph, NLP, scraping, discovery, sandbox,
simulation, and legacy export surfaces remain unmounted. Every mounted
operation must appear in the generated route-security manifest with one of four
classifications: public, tenant-scoped, global sysadmin, or workload-only. Each
entry names its auth method, permission, storage boundary, and executable test
adapter. An unclassified route is a CI and startup-contract failure.

The supplier-validation router is excluded from this release even though it
was in the initial candidate allowlist. Its dashboard-local supplier IDs have
no stable relationship to canonical portal or CTE event identities, and its
historical data path queried an unmigrated table. Re-enabling it requires an
explicit tenant-scoped identity mapping and route-complete isolation tests; an
empty compliance result is not an acceptable database-error fallback.

### 3. Split human and workload administration

Human key and tenant management requires an active opaque browser session,
`is_sysadmin=true`, and WebAuthn or SSO high assurance. The retired shared
administrative header is rejected.

Automation uses a database-backed, tenantless workload key only at the hidden
`POST /v1/internal/tenants` endpoint. The key requires exactly
`internal.tenants.create`, expires within 90 days, and is independently rate
limited. Generic tenant APIs reject workload keys. Review reads require
`review.read`; decisions require `review.decide` and high assurance.

Frontend BFF routes forward caller-owned credentials. They never substitute a
generic environment tenant key for an unverified caller. A scoped bridge is an
exception only when an exact route validates the opaque session against
`/auth/me`, binds the returned `tenant_id`, and uses a dedicated least-privilege
credential. The Inflow readiness summary is the sole current exception.

Email OTP establishes only low assurance. It cannot bootstrap a passkey and
then immediately exercise a privileged operation. Passkey registration and
privileged mutations require an already high-assurance WebAuthn/SSO session;
staff enrollment is provisioned through the controlled staging/operations
workflow.

### 4. Fail closed on shared authentication state

Production access tokens are 1–15 minutes, defaulting to five. JTI, session,
and `token_version` invalidation remain authoritative. Production rejects
legacy JTI-free tokens, in-memory session state, and unavailable Redis
revocation checks. A backend uncertainty returns 503, never authenticated
success. Privileged/workload failure throttles and public Stripe checkout abuse
limits also require a shared backend in production.

Cross-tenant queue claims, state transitions, and maintenance discovery are
control-plane operations and use the closed `ADMIN_DATABASE_URL` path. Handler
data work remains tenant-bound on `DATABASE_URL`. A scheduler job without a
proven least-privilege caller is disabled rather than granted ambient global
data access. Audit reconciliation may append tenant-bound rows, but global
chain discovery must use an explicitly guarded control-plane path.

### 5. Treat release evidence as a deployable artifact

Release approval requires a sanitized record binding frontend SHA and Vercel
deployment ID, backend SHA and Railway deployment ID, Alembic head, exact
router set, commands, results, and verification date. No secret values enter
the record. Source tests are necessary but cannot substitute for the two-tenant
database-role matrix, two-replica revocation test, enumeration timing sample,
CSRF/SSRF staging matrix, or deployment-bound public-contract checks.

## Consequences

### Positive

- Neither runtime role has PostgreSQL `BYPASSRLS` or superuser capability;
  within trusted application flows, missing tenant context fails closed.
- Ambient frontend configuration cannot turn a forged browser credential into
  tenant authority.
- Router growth is review-visible and blocked until it has an executable
  security contract.
- Revocation and abuse controls have one cross-replica source of truth.
- Security claims can be tied to immutable deploys instead of repository state.

### Negative

- Redis or RLS-posture uncertainty can make production unavailable.
- Cross-tenant staff operations must use audited application paths instead of a
  bypassing database login.
- Each new router and outbound-fetch path needs explicit classification and
  negative-path tests.
- Rollout requires coordinated Vercel, Railway, database-role, and workload-key
  configuration; mixed compatibility state is not release-approved.
- The shared tenant runtime credential remains a material trust boundary: a
  holder able to execute arbitrary SQL can select another `app.tenant_id` even
  though the role cannot disable RLS.

## Alternatives rejected

- **Retain a monitored RLS-bypass runtime role.** Monitoring detects misuse
  after the isolation boundary has already failed.
- **Claim RLS contains runtime-credential theft.** The caller-settable custom
  GUC makes that claim false; the stronger per-tenant-principal design is a
  separate architectural change.
- **Keep the shared admin key during normal operation.** It is not attributable
  to a human, cannot express assurance, and creates an unnecessarily broad
  credential.
- **Default-mount routers and maintain a denylist.** New routers would become
  reachable without a security adapter.
- **Degrade to process-local revocation or throttling.** Replica-local state
  multiplies the attack budget and permits inconsistent replay decisions.
- **Treat the repository SHA as deployment proof.** It does not prove the
  active Vercel/Railway configuration, database roles, or Redis behavior.

## Rollout and retirement

The compatibility backend may temporarily observe legacy-key use while callers
move to human sessions or workload keys, but compatibility is disabled for the
release gate. Retirement completes only after callers migrate, the retired
header is rejected, the old secret is removed and revoked, and the negative
matrix passes. A security rollback may revert application code, but may not
restore a bypass-capable runtime role or the shared administrative key.

## Verification

The source implementation is governed by:

- `docs/operations/DATABASE_ROLE_CUTOVER.md`
- `docs/security/ROUTE_SECURITY_MANIFEST.md`
- `docs/security/route-security-manifest.json`
- `docs/security/release-evidence/`
- `.github/workflows/backend-ci.yml`
- `.github/workflows/frontend-ci.yml`

The release remains unapproved until the candidate deployment passes every
staging and production gate recorded in its release-evidence file.
