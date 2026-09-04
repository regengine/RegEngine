# Account-Erasure Authority Boundary Repair

## Goal

Close the unclassified global-RLS authority used by `POST /v1/account/erasure`,
make the route-security manifest describe its identity-global effects, prove on
real PostgreSQL that one authenticated identity cannot affect another, and make
those checks blocking CI evidence before the security candidate is integrated
or deployed.

## Architecture

The authenticated identity remains `current_user.id`; no request field may
select an erasure target. The existing admin runtime role may arm
`regengine.is_sysadmin` only for this reviewed transaction so it can erase the
same identity across every tenant where that identity has membership or audit
history. Route classification continues to describe the tenant-bound session
actor, while an exact operation policy and adapter describe the broader
identity-global storage effect. PostgreSQL, not a mock, proves that all writes
remain filtered to the authenticated user ID.

## Tech Stack

- Python 3.11/3.12, FastAPI, SQLAlchemy, PostgreSQL 16, Alembic
- Pytest and GitHub Actions
- Generated JSON route-security manifest and staging release-gate runner

## Baseline / Authority Refs

- `AGENTS.md`
- `README.md`
- `REPO_PURPOSE.md`
- `ARCHITECTURE.md`
- `CANONICAL_OWNERSHIP.md`
- `docs/specs/FSMA_204_MVP_SPEC.md`
- `docs/engineering/SCHEMA_CHANGE_POLICY.md`
- `docs/architecture/decisions/ADR-004-security-release-boundary.md`
- `docs/aegis/work/2026-08-03-regengine-security-release-gate/10-intent.md`
- `docs/aegis/work/2026-08-03-regengine-security-release-gate/20-checkpoint.md`
- `docs/security/STAGING_RELEASE_GATE.md`

## Compatibility Boundary

- Keep the endpoint, request/response models, status behavior, and
  authenticated user's cross-tenant self-erasure semantics unchanged.
- Do not add a caller-selectable user or tenant target.
- Do not add or change a database schema, public API, auth credential type, or
  production router count.
- Preserve 246 enabled operations and 177 omitted operations returning exact
  404.
- Keep release evidence `not_approved`; this slice is source evidence only.
- Preserve the user-owned untracked file
  `frontend/COPY_REMEDIATION_PLAN.md` byte-for-byte.

## TDD Route

- Mode: off
- Decision: skipped
- Strict authority: not applicable
- Test posture: diagnostic reproduction plus post-change negative regression
- Reason: the user did not request strict/test-first TDD; the deterministic
  allowlist failure is already reproduced.
- Verification: focused authority, manifest, erasure, live-PostgreSQL, and CI
  contract tests, followed by the broader security slice.

### P2 review-repair addendum — 2026-08-26

- Mode: off
- Decision: strict
- Strict authority: explicit delegated test-first request
- RED: the route regression failed at the post-commit disarm and showed no
  immediate rollback on a pre-commit SQL failure; the destructive-DB admission
  matrix failed because no four-URL scratch-target guard existed.
- GREEN boundary: commit flows directly to runtime credential cleanup,
  pre-commit failures roll back the armed transaction, and the live proof
  admits only the genuine GitHub Actions `localhost/live_suite` target or an
  explicitly acknowledged target that exactly matches
  `REGENGINE_MIGRATION_TEST_DB`.
- Remaining verification: current-main integration. Independent staging-spec
  and P2 code-quality/security re-reviews both returned `APPROVED` with no
  remaining findings.

## TaskStartSnapshot

- Branch: `codex/regengine-security-release-gate`
- HEAD: `d9c1d17fc5fcbf233d2362f885f370509aa635ce`
- Observed `origin/main`: `675278cedc9d28f0b9c391e20f45a2e423a5964e`
- Status digest: `95eb91ec83deec4fa495d357579e26ed24fb1d7939335784e1e4dcb5f0a01aaf`
- Tracked-diff digest: `ddfffbb623eb4822075490d9ee7093cfd56848060a39518790654fad72aa27f9`
- Untracked-path digest: `8d4193918635df1bb86f8ec29eec3441cce5ceb4fe71adf2ee091a03f2bcdec1`
- Preserved user-file SHA-256: `18da71fc0fab0009e5e239f87aea10d600e3a79ee858d355e74f46fb861a0a0e`

## Requirement Ready Check

- Requirement source: the active security-release intent and the deterministic
  failing global-admin authority inventory.
- Scenario: authenticated user A requests self-erasure from a valid tenant
  membership while user B has independent users, memberships, audit rows, and
  graph state.
- Acceptance: A is erased across A's own tenant history; every B record and B
  outbox/audit effect is unchanged; manifest and CI make the proof mandatory.
- Open blocker questions: none for this bounded repair.
- Decision: ready.

## Change Necessity

- User-visible need: account erasure must remain functional without granting a
  session authority over any other identity.
- No-change / non-code option: documenting the current behavior would leave a
  failing authority inventory and inaccurate executable manifest.
- Why code change is necessary: the canonical security policy, negative proof,
  and CI invocation are code-owned contracts.
- Minimum change boundary: authority allowlist, exact route policy/adapter,
  tests, CI wiring, generated manifest, and evidence records. Production
  erasure logic changes only if the negative test exposes a real leak.
- Decision: code-change.

## Architecture Integrity / Patch Shape

- Invariant: only the immutable authenticated user ID may cross tenant RLS for
  account erasure.
- Canonical identity owner: `request_erasure()` and `get_current_user`.
- Canonical route-contract owner: `server/route_security_policy.py`.
- Canonical global-arm inventory: `tests/security/test_global_admin_context_allowlist.py`.
- PatchShape: contract and producer/consumer seam; a local allowlist-only patch
  is insufficient.
- UpwardDrillSignal: the generic dual-session manifest fallback hid an
  operation whose storage effect is identity-global.
- Decision: fix the existing owners; add no fallback or alternate erasure path.

## Complexity Budget

- Artifact class: security policy and test adapter.
- Target pressure: `server/route_security_policy.py` is moderately large but is
  the existing canonical owner; `erasure_routes.py` is below the large-module
  threshold and should not gain a new responsibility.
- Projected pressure: one exact operation contract and one focused adapter.
- Budget result: at-risk but bounded.
- Planned governance: reuse existing classification and adapter patterns; put
  live proof in a new focused test file; avoid adding a new auth framework or
  database policy.

## Task 1 — Classify the identity-global self-erasure contract

Files:

- Modify `tests/security/test_global_admin_context_allowlist.py`.
- Modify `server/route_security_policy.py`.
- Modify `tests/security/test_route_security_manifest.py`.
- Modify `scripts/security/staging_release_gate.py`.
- Modify `tests/security/test_staging_release_gate_runner.py`.
- Modify `docs/security/STAGING_RELEASE_GATE.md`.
- Regenerate `docs/security/route-security-manifest.json`.

Steps:

1. Add `request_erasure` with one call to the reviewed
   `identity-global-self-service` global-arm authority class, and add that class
   to the closed set of accepted classes.
2. Add one exact-operation contract for
   `admin:POST:/v1/account/erasure`. Keep classification `tenant-scoped` because
   the actor is a tenant-bound session, retain bearer-or-opaque-session auth,
   set storage boundary to
   `admin-postgres+graph-outbox:authenticated-user-global-identity`, and use a
   dedicated `tenant_identity_global_self_erasure` adapter.
3. Make the adapter reuse dual-session/CSRF validation and fail manifest
   generation unless the endpoint is `request_erasure` and binds
   `_apply_account_erasure(..., user_id=...)` to `current_user.id` through the
   normalized UUID.
4. Teach the staging runner that the new `tenant_` adapter uses a session actor
   and requires unauthenticated, CSRF, and dedicated
   `identity-isolation-write` probes. Before mutation, the isolation probe must
   observe both active non-sysadmin session actors A and B through the exact
   canonical `admin:GET:/auth/me` operation and runtime-assert distinct
   `user_id` values plus `tenant_id` equal to the resolved protected-tenant
   fixture. It must then accept one exact configured 2xx from A's self-erasure,
   require A's same `/auth/me` session to return exactly 401, and prove B's
   required identity-field bytes are unchanged through a second 200
   observation. It must reject denied mutation evidence, same-identity or
   wrong-tenant fixtures, sysadmin sessions, a 2xx no-op that leaves A
   authenticated, changed B identity, and reuse of the already-erased
   operation contract actor. Update request counts, sanitized result statuses,
   the adapter-obligation tests and staging documentation, and include the
   staging-runner adversarial suite in blocking backend CI.
5. Add manifest tests for the exact storage/auth/adapter contract and for
   rejecting an endpoint that no longer derives the erasure target from the
   authenticated user.
6. Regenerate the checked-in manifest and assert operation counts remain
   unchanged.

Verification:

```bash
./venv/bin/python -m pytest tests/security/test_global_admin_context_allowlist.py \
  tests/security/test_route_security_manifest.py \
  tests/security/test_staging_release_gate_runner.py -q --no-cov
./venv/bin/python scripts/generate_route_security_manifest.py --check
```

## Task 2 — Prove cross-identity isolation on the exact admin role

Files:

- Create `tests/security/test_account_erasure_identity_isolation_pg.py`.
- Modify `services/admin/tests/test_erasure_hardening.py` for a fast in-memory
  user-B regression if it improves failure localization.
- Modify `.github/workflows/backend-ci.yml`.

Steps:

1. Seed two overlapping disposable membership tenants plus one A-only
   audit-history tenant through the provider fixture credential in an
   Alembic-head PostgreSQL 16 database. Put A and B in both membership tenants
   so tenant-only filtering cannot pass vacuously.
2. Execute an actual ASGI `POST /v1/account/erasure` with a locally signed
   bearer token for A and a dependency-overridden Session using the exact
   `ADMIN_DATABASE_URL`. Keep real `get_current_user` JWT/JTI, session,
   token-version, user-context, and membership resolution. Stub only external
   token/session verdicts and cleanup plus immediate Neo4j delivery; exercise
   the real route, SQL transaction, global arm, commit, audit marker writer,
   and graph outbox.
3. Assert A is erased and exactly the retained A membership rows are inactive.
   Require exactly one marker and outbox row for each of A's three derived
   tenants. Assert B's user, `user_emails`, memberships, organization
   memberships, sessions, audit rows, and graph-outbox state are byte/value
   unchanged and no new marker or outbox payload contains B's user ID.
4. Add the global-arm allowlist test to the blocking in-process security step.
   Add the live identity-isolation test to the existing dedicated-role step
   that supplies migration, runtime, admin, and provider credentials. Preserve
   skip-as-failure behavior.
5. Do not issue a transaction-local disarm after the durable commit. PostgreSQL
   commit clears `SET LOCAL`; route failures before commit roll back, while a
   successful commit proceeds immediately to Redis/elevation cleanup without
   opening another database transaction.
6. Before constructing either live-test engine, require all four direct role
   URLs to be valid PostgreSQL URLs for the same target. Admit
   `localhost/live_suite` only when both `CI` and `GITHUB_ACTIONS` are true;
   otherwise require `REGENGINE_ALLOW_DESTRUCTIVE_DB_TESTS=1` and an exact
   target match with `REGENGINE_MIGRATION_TEST_DB`. Always reject the ordinary
   `regengine` and `regengine_admin` dev databases.

Verification:

```bash
./venv/bin/python -m pytest services/admin/tests/test_erasure_hardening.py \
  services/admin/tests/test_erasure_route_integration.py \
  tests/security/test_account_erasure_live_db_guard.py -q --no-cov
MIGRATIONS_DATABASE_URL=... DATABASE_URL=... ADMIN_DATABASE_URL=... \
ROLE_ADMIN_DATABASE_URL=... REGENGINE_REQUIRE_RLS_ENFORCEMENT=1 \
  ./venv/bin/python -m pytest tests/security/test_account_erasure_identity_isolation_pg.py \
  -q --no-cov -rs
```

The live command uses named local/CI test credentials only; credential values
must never be written to the plan, logs, or release evidence.

## Task 3 — Refresh source evidence without approving release

Files:

- Modify `docs/security/release-evidence/2026-08-03-security-remediation-candidate.json`.
- Modify `docs/aegis/work/2026-08-03-regengine-security-release-gate/20-checkpoint.md`.
- Modify `docs/aegis/work/2026-08-03-regengine-security-release-gate/90-evidence.md`.

Steps:

1. Update the route-manifest SHA-256 and record the new focused source checks;
   keep deployment SHAs/IDs null and status `not_approved`.
2. Replace the stale `source complete` checkpoint claim with fresh evidence for
   this repair and set the next slice to current-main integration plus Alembic
   topology reconciliation.
3. Run release-evidence validation and `git diff --check`.

Verification:

```bash
./venv/bin/python scripts/validate_release_evidence.py
./venv/bin/python -m pytest tests/security/test_release_evidence.py -q --no-cov
git diff --check
```

## Review Gates

1. Spec review: exact authenticated-identity binding, B-side non-mutation,
   accurate manifest/storage semantics, unchanged public contract and counts.
2. Code-quality/security review: SQL transaction and cleanup safety, adapter
   non-vacuity, CI skip behavior, generated-artifact consistency.
3. Coordinator verification: rerun all commands above plus the focused security
   suite that originally produced one failure and 141 passes.

## Repair and Retirement Tracks

- Repair: classify the existing global arm and prove its user-bound effect at
  the policy, route, PostgreSQL, and CI layers.
- Retirement: retire the generic dual-session manifest description for this
  exact operation. Keep the generic adapter for ordinary tenant-scoped routes.
  Add no legacy mode or compatibility flag.

## Stop / Rewind Rules

Stop and return to design if the live test changes any B-owned record, if the
route requires caller-selected identity authority, if a new migration/public
API is needed, or if operation counts change unexpectedly. Any such signal
blocks commit, integration, and deployment.

## Execution Route

- Decision: subagent-driven
- Evidence: implementation and review roles are available; the slice has one
  bounded writer followed by independent spec and quality reviews.
- Fallback: coordinator executes inline only if the writer becomes blocked.
- User confirmation required: no; all work remains inside the requested source
  build and no deployment occurs.
