# Evidence Bundle

## Evidence Receipt (L1)

- Goal: implement the RegEngine security remediation and make its source and
  runtime release gates executable.
- Stop state: `needs-verification`.
- Source verdict: review-driven repairs are locally green; both the corrected
  staging-proof spec re-review and the repaired P2 code-quality/security
  re-review are approved with no remaining findings. The bounded
  account-erasure slice is source-complete, but current-main integration
  remains open, so no integrated source-complete claim is made.
- Release verdict: not approved; staging and immutable deployment evidence are
  absent and the inspected production deployments fail the proposed contract.
- Evidence record:
  `docs/security/release-evidence/2026-08-03-security-remediation-candidate.json`.

## Baseline and workspace integrity

- Initial checkout: `d0e0f23656ec4ccc681b739fc4c4763697813a6b`, eight commits behind.
- Task branch: `codex/regengine-security-release-gate`.
- Task-start branch base and then-observed `origin/main`:
  `d9c1d17fc5fcbf233d2362f885f370509aa635ce`.
- Current coordinator drift readback: refreshed `origin/main`
  `bd2ef979457966685440b8bc49b171f60a290e18`, 47 commits ahead with 41
  overlapping paths, including a FastAPI 0.141 effective-route integration
  blocker and a linear mainline Alembic head through v112.
- User-owned untracked file preserved:
  `frontend/COPY_REMEDIATION_PLAN.md`, SHA-256
  `18da71fc0fab0009e5e239f87aea10d600e3a79ee858d355e74f46fb861a0a0e`.
- This candidate is anchored only by a local alternate-index checkpoint; the
  dirty source checkout and its real index remain untouched. No push,
  deployment, staging-environment mutation, or production mutation was
  performed.

## Verification ledger

- Account-erasure authority repair (2026-08-26): 55 focused global-arm,
  route-manifest, and staging-runner tests passed. The generated manifest
  retained 246 enabled operations and 177 omitted operations returning exact
  404, and now records
  `admin-postgres+graph-outbox:authenticated-user-global-identity` through the
  dedicated `tenant_identity_global_self_erasure` adapter.
- Account-erasure negative proof (2026-08-26): seven fast erasure
  hardening/integration tests passed, including an in-memory A-vs-B
  non-mutation regression. One live PostgreSQL 16 test passed with zero skips
  through an actual ASGI POST, locally signed bearer token, real
  `get_current_user`, and direct migration, runtime, `regengine_sysadmin`, and
  provider credentials. Both identities were members of both membership
  tenants, A had a third audit-history-only tenant, and exactly three A
  markers/outbox rows were written. B's user, `user_emails`, membership,
  organization-membership, session, audit, and outbox rows were unchanged.
- Account-erasure P2 safety repair (2026-08-26): the route no longer issues a
  transaction-local disarm after durable commit; successful commit proceeds
  directly to Redis/elevation cleanup, while pre-commit failures roll back the
  armed transaction. The live proof now parses all four PostgreSQL role URLs
  before engine construction, requires one exact target, always rejects the
  ordinary dev-stack databases, limits the automatic `live_suite` exception
  to genuine GitHub Actions (`CI` plus `GITHUB_ACTIONS`), and otherwise
  requires explicit destructive-test acknowledgement plus an exact
  `REGENGINE_MIGRATION_TEST_DB` match. Twenty-one focused tests passed, and the
  actual ASGI PostgreSQL 16 proof was rerun on a fresh explicitly designated
  disposable database with one pass and zero skips. Independent P2 re-review
  reproduced 21 focused passes and returned `APPROVED` with no findings.
- Account-erasure staging semantics (2026-08-26): the dedicated adapter now
  preflights A and B through exact `admin:GET:/auth/me`, runtime-asserts
  distinct user IDs, the resolved protected tenant, and non-sysadmin posture,
  then requires one exact configured 2xx self-erasure, A's exact post-erasure
  401, and byte-stable B identity fields. The five-request proof is fully
  pre-rendered and its four observation statuses are emitted as sanitized
  results. Adversarial tests reject actor reuse, same runtime identity,
  wrong-tenant or sysadmin identities, denied mutation evidence, a 2xx no-op,
  missing or unrelated observations, and changed B identity values.
- CI contract (2026-08-26): the closed global-arm inventory is part of the
  blocking in-process security step; the destructive-DB admission matrix and
  staging-runner adversarial suite are explicitly in that same blocking step.
  The live A-vs-B proof is part of the four-credential dedicated-role step with
  its existing skip-as-failure backstop.
- PostgreSQL role/RLS gate: 67 passed, zero skips. It covered the dedicated
  migration owner, both runtime roles, provider and `SET ROLE` negatives,
  bidirectional membership, exact policy/ACL fingerprints, checkout reuse,
  and startup posture.
- Migrated RLS/lockdown coverage: six passed, zero skips.
- Historical pre-linearization fresh/upgrade evidence: full chain, managed
  rerun, seeded mid-chain rehearsal, unmanaged-schema refusal, `alembic
  current`, and `alembic check` passed against unpublished draft head
  `b71d9e4c2a60`. It does not verify the current v114 integration target;
  current-chain PostgreSQL rehearsal remains required.
- Security suite: 136 passed, zero skips.
- Admin suite: passed; one expected SQLite-only listener skip and three known
  rollback warnings. The PostgreSQL-specific listener behavior is covered by
  the live role suite.
- Ingestion suite: passed with integration-only scratch DB/service/Docker
  skips. Its security-critical raw transaction lane separately passed 24
  focused tests against the private PostgreSQL instance with zero skips; the
  wider related suite passed 125 tests.
- Frontend: 718 tests passed with two existing dashboard skips; TypeScript,
  security audit, production build (183 pages), npm audit, and the six-test
  blocking Playwright slice passed. ESLint passed with zero errors and 51
  existing warnings.
- Route/public contract: manifest check passed for 246 enabled operations and
  177 omitted operations (160 unique paths) returning exact 404. Manifest
  SHA-256 is
  `b2110f5646421aa4e611e2d6cc71dfccd7f930c8350dc0cbbe165f2ad44bb7b8`.
- Static checks: changed/new Python error-code lint, compilation, workflow YAML
  parsing, shell syntax, enabled outbound HTTP guard, sanitized evidence
  validation, and repository `git diff --check` passed.
- Spec/security review identified the injected-user live proof and vacuous
  staging cross-tenant probe. Those findings are corrected and locally green;
  independent re-review approved the corrected five-request staging proof with
  no findings. A subsequent code-quality/security review found the two P2
  transaction/admission defects recorded above; both are repaired, locally
  green, and independently re-reviewed `APPROVED` with no findings.

## Architecture and governance

- ADR-004 records the database-role, GUC, and deployment evidence boundary.
- No Vercel configuration-format migration was introduced.
- `supplier_validation` remains release-disabled because it lacks a migrated,
  tenant-scoped canonical identifier mapping and executable two-tenant adapter.
- `remediation` remains release-deferred for this candidate because its 15
  operations lack the required route adapters and live tenant/token matrix.
  Integration must also disable its scheduler/UI/runtime-grant paths; reduced
  core-release scope still requires product/compliance signoff.
- Graph and overlay remain release-disabled. Integration must enforce that
  disposition across graph-backed `/api/fsma/*` and every `/api/controls/*`
  frontend alias before any credential handling or upstream fetch.
- Historical system-context and shared-admin paths are retired from active
  source contracts; deployed legacy variables remain an explicit external
  retirement gate.
- The Aegis references `docs/adr/ADR-CREATION-GATE.md`,
  `docs/current/AEGIS_ADR_AUTO_BACKFILL.md`, and
  `docs/current/AEGIS_COMPLEXITY_GOVERNANCE_BASELINE.md` were absent, and no
  repository ADR helper was available. ADR-004 and this receipt provide the
  local fallback record.

## Readiness and confidence

- Intent lock: satisfied.
- Scope fence: satisfied; optional routers remain exact 404.
- Ownership boundary: satisfied in source and private PostgreSQL 16.
- Retirement boundary: satisfied in source, not in deployed environment.
- Complexity: increased at security boundaries through explicit role and route
  inventories; bounded by generated manifests, small helpers, negative tests,
  and runbooks rather than a new framework.
- Source confidence: B (multiple independent source and real-PostgreSQL proofs).
- Release confidence: C (deployment/pooler/replica gates not executed).

## Unverified release gates

- Current-main reconciliation of the FastAPI 0.141 effective-route overlap and
  the sibling Alembic topology.
- Candidate Vercel/Railway deployment and exact immutable bindings.
- Actual PgBouncer/Supavisor transaction-mode endpoint and staging catalog
  fingerprint.
- Route-complete disposable two-tenant matrix and exported-byte comparison.
- Real WebAuthn/SSO provider, shared Redis throttling, and revocation across two
  backend replicas including outage behavior.
- Thirty-pair enumeration timing and controlled CSRF/SSRF canary matrix.
- Candidate-bound `security.txt`, OpenAPI, docs, and security-page checks from
  both `vercel curl` and an unauthenticated external network.

## Goal closure

`needs-verification`: the corrected bounded account-erasure slice is locally
supported and both independent reviews are approved. Integrated source
completion and release approval remain blocked by the unverified current-main,
staging, and deployment gates.
