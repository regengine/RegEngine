# TodoCheckpoint

## Resume Amendment — 2026-08-26

- The account-erasure identity-global authority repair described in
  `docs/aegis/plans/2026-08-26-account-erasure-authority-boundary.md` is
  implemented and locally re-verified after spec/security review returned
  `CHANGES_REQUIRED`. `request_erasure()` is classified as
  reviewed `identity-global-self-service`, and its exact manifest adapter
  proves `_apply_account_erasure(..., user_id=...)` is bound through a
  normalized `current_user.id`.
- Fresh PostgreSQL 16 evidence now uses an actual ASGI POST with a locally
  signed bearer token and real `get_current_user`; JTI, Redis revocation
  verdict, session-bound token, token-version, authenticated-user context, and
  membership resolution all execute before the route. Both A and B are
  members of both disposable membership tenants, and A also has a third
  audit-history-only tenant. A receives exactly three audit markers/outbox
  rows; B's user, `user_emails`, membership, organization-membership, session,
  audit, and graph-outbox snapshots remain exact.
- The live proof exposed one existing functional gap: `audit_logs` has a
  tenant-only read/write policy. Under the reviewed global arm the route now
  enumerates tenant IDs, transaction-locally binds each, queries an explicit
  `(tenant_id, authenticated user_id)` predicate, and writes each A-derived
  marker/outbox row under that tenant. No migration, caller-selected identity,
  or caller-selected tenant was added.
- The staging adapter now requires a successful `identity-isolation-write`,
  not a vacuous denied cross-tenant mutation. Actor A must differ from the
  already-erased contract actor. Before mutation, exact canonical
  `admin:GET:/auth/me` preflights must prove A and B have distinct runtime user
  IDs, both resolve to the protected tenant fixture, and neither is sysadmin.
  After A's exact configured 2xx self-erasure, A's same session must receive
  exactly 401 from `/auth/me` and B's required identity-field bytes must remain
  unchanged. A 2xx no-op, relabeled session, tenant drift, or changed B blocks
  the gate.
- Current todo: anchor the reviewed source candidate without touching the
  dirty source index, then integrate it with current main and reconcile the
  Alembic topology before any deployment or release-gate execution.
- Active slice: corrected gates are locally green, and the independent
  staging-proof spec re-review returned `APPROVED` with no findings. A later
  code-quality/security review identified two P2 defects: a post-commit
  transaction-local disarm could block runtime revocation after durable
  erasure, and the live proof did not prove its four credentials targeted one
  designated disposable database. Both repairs are implemented, locally
  green, and independently re-reviewed `APPROVED` with no findings. The
  bounded account-erasure repair is source-complete; the overall release
  candidate is not source-complete until current-main integration passes.
- TaskStartSnapshot: branch `codex/regengine-security-release-gate`, HEAD
  `d9c1d17fc5fcbf233d2362f885f370509aa635ce`, observed `origin/main`
  `675278cedc9d28f0b9c391e20f45a2e423a5964e`, with the preserved user file
  still matching SHA-256
  `18da71fc0fab0009e5e239f87aea10d600e3a79ee858d355e74f46fb861a0a0e`.
- Current integration drift (coordinator readback): refreshed `origin/main` is
  `bd2ef979457966685440b8bc49b171f60a290e18`, 47 commits ahead with 41
  overlapping changed paths. The overlap includes a FastAPI 0.141
  effective-route integration blocker. Main now owns linear v110/v111/v112
  revisions. The paused integration worktree now linearizes the unpublished
  candidate migrations as v113/v114 after main's v112, preserves the v112
  function file byte-for-byte, and fails closed on the old draft revision,
  trigger, and seed-policy artifacts. The rebase has not been continued and
  the current v114 chain has not yet completed its PostgreSQL rehearsal. The
  TaskStartSnapshot above remains historical. No deployment is permitted
  before current-main integration, migration rehearsal, and effective-route
  verification.
- Integration surface decision: keep `remediation` release-deferred instead of
  granting 15 unreviewed HTTP operations; gate its scheduler/UI/runtime grants
  and require product/compliance signoff before release approval. Keep graph
  and overlay release-disabled across every frontend alias: graph-backed
  `/api/fsma/*` and all `/api/controls/*` must return exact 404 before
  authentication or upstream fetch. Main's corrected non-graph FSMA mapping
  remains in scope. Main's `/health/live`, `/health/deep`, and duplicate
  `/metrics` corrections are real operation-table changes and must be
  classified and regenerated rather than hidden behind the old manifest
  counts.
- Evidence: 55 focused authority/manifest/staging-runner tests passed. After
  the P2 repair, 21 erasure hardening, route-ordering, and destructive-DB guard
  tests passed. The dedicated-role PostgreSQL 16 ASGI A-vs-B test was rerun on
  a fresh explicitly designated disposable database and passed with zero
  skips. Manifest generation retained 246 enabled and 177 omitted operations
  returning exact 404.
- Decision: `needs-verification` for current-main integration and migration
  reconciliation. Release remains `not_approved`.

## Superseded pre-repair checkpoint

- Completed todos:
  - created `codex/regengine-security-release-gate` at
    `ec6421c70becc0cf937bae49f8a32d94f160cf35`, then safely moved its base to
    the actual current `origin/main`,
    `d9c1d17fc5fcbf233d2362f885f370509aa635ce`, after verifying the intervening
    three-file delta and the absence of staged changes;
  - preserved user-owned `frontend/COPY_REMEDIATION_PLAN.md`;
  - preserved the byte-identical `origin/main` three-file delta while retaining
    all task edits across that baseline move;
  - implemented separate runtime/admin/migration credentials and production
    posture probes;
  - made a 25-router allowlist and generated route-security manifest a
    blocking contract; `supplier_validation` was removed from the original
    26-router proposal because no migrated tenant-scoped identity mapping
    safely connects its dashboard IDs to canonical supplier/CTE records;
  - rejected the retired administrative header and introduced high-assurance
    human plus exact-scope workload authorization;
  - migrated frontend admin/review paths to caller-owned opaque sessions;
  - implemented five-minute access-token defaults and strict Redis/JTI/session/
    token-version revocation;
  - preserved indistinguishable passwordless challenge contracts;
  - extended CSRF and safe outbound HTTP gates over the enabled surface;
  - corrected public OpenAPI/security/docs contracts and created a sanitized,
    explicitly unapproved evidence candidate;
  - made account erasure match the real schema, cover every historical/member
    tenant with audit markers and graph outbox work, remove authentication
    factors, clear session PII, and fail closed on revocation cleanup;
  - enforced an exact dedicated migration owner, closed runtime/admin ACL and
    policy inventories, rejected role membership in both directions, and made
    startup canaries detect owner, provider `SET ROLE`, membership, ACL, and
    policy drift;
  - canonicalized `shared.*` imports and proved one tenant ContextVar/listener
    identity under the production Python path;
  - replaced raw-ingestion autocommit/session context with one explicit
    transaction containing both transaction-local tenant setup and the
    protected query;
  - upgraded the local Vercel CLI to 58.5.1 and inspected the existing Vercel
    and Railway deployments read-only.
- Historical pre-linearization evidence is green: 67 direct-role PostgreSQL
  tests, six migrated RLS/lockdown tests, 136 security tests without skips,
  full admin and ingestion source suites, the live raw-ingestion transaction
  proof, full
  frontend unit/type/lint/build gates, six blocking Playwright tests, and the
  regenerated route contract (246 enabled operations; 177 omitted operations
  returning exact 404). At that historical checkpoint, Alembic
  head/current/check agreed on unpublished draft `b71d9e4c2a60`; those results
  are not evidence for the current v114 integration target.
- External blockers to release approval: no candidate Vercel/Railway deployment,
  no staging role cutover, no route-complete two-tenant matrix, no two-replica
  revocation/outage run, and current production environment/public-contract
  checks fail.
- Next step: deploy this candidate to staging with the dedicated roles and
  real pooler/Redis configuration, then run the route-complete two-tenant,
  replica-revocation, enumeration, CSRF/SSRF, and deployment-bound public-doc
  gates. The current stop state is `needs-verification`, not release-approved.

## ResumeStateHint

Resume on `codex/regengine-security-release-gate`. Never clean or overwrite
`frontend/COPY_REMEDIATION_PLAN.md`. Read `10-intent.md`, this checkpoint, the
unapproved release-evidence JSON, ADR-004, `90-evidence.md`, and
`99-reflection.md`. Production source and database lanes are frozen.

## DriftCheckDraft

- Original intent served: yes.
- Scope fence held: yes; optional routers remain disabled and no Vercel config
  migration was introduced.
- Compatibility boundary held: yes; no release-approved legacy-key path exists.
- New owner/fallback/adapter: route manifest/gate, workload provisioner,
  high-assurance session boundary, database-role cutover, and release-evidence
  validator are documented and tested.
- Retirement track explicit: yes; deployed legacy variables/credentials remain
  an external release blocker.
- Evidence sufficient for bounded account-erasure source completion: yes.
- Evidence sufficient for integrated release-candidate source completion: no;
  current-main integration remains open.
- Evidence sufficient for release approval: no.
- Decision: `needs-verification`; promotion stays blocked until the staging and
  deployment-bound gates pass.
