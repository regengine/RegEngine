# RegEngine Security Remediation and Release Gate

## TaskIntentDraft

- Requested outcome: implement the approved security remediation plan and make its CI/runtime gates executable.
- Scope: production database/RLS posture, router allowlisting and inventory, shared-admin-key removal, human/workload authorization, review authorization, token revocation, CSRF/SSRF guards, public contracts, and release evidence.
- Non-goals: enabling graph/NLP/sandbox/other optional routers; adopting Vercel Workflow or Vercel Sandbox; migrating `vercel.json` to `vercel.ts`; using customer data; treating a compatibility mode as releasable.
- Success evidence: focused negative-path tests, repository checks, route-manifest completeness, fail-closed configuration tests, and deployment-bound evidence where credentials and staging infrastructure are available.
- Stop states: `done`, `blocked`, `needs-verification`, or `scope-exceeded`.

## BaselineReadSetHint

Required and acknowledged before implementation:

- `AGENTS.md`
- `README.md`
- `REPO_PURPOSE.md`
- `ARCHITECTURE.md`
- `CANONICAL_OWNERSHIP.md`
- `docs/specs/FSMA_204_MVP_SPEC.md`
- `docs/engineering/SCHEMA_CHANGE_POLICY.md`
- `.github/agents/regengine-implementer.agent.md`
- `.github/CODEOWNERS`
- `frontend/package.json`
- `.github/copilot-instructions.md`

## BaselineUsageDraft

- Baseline lock: the task branch was first created at
  `ec6421c70becc0cf937bae49f8a32d94f160cf35`. While implementation was in
  progress, `origin/main` advanced to
  `d9c1d17fc5fcbf233d2362f885f370509aa635ce`. After confirming the intervening
  three-path delta (`requirements.in`, `requirements.lock`, and
  `scripts/workflow_inventory.txt`) was byte-identical to the working tree and
  that no files were staged, the branch base was moved with a mixed reset to
  the actual `origin/main` commit. Task changes and user state were preserved.
- Preserved user state: untracked `frontend/COPY_REMEDIATION_PLAN.md`.
- Canonical production shape: one Railway FastAPI monolith in `server/main.py` plus the Vercel Next.js frontend.
- Canonical data boundary: PostgreSQL tenant RLS and authenticated principal-derived tenant context.
- Runtime evidence boundary: the active Vercel and Railway deployment
  identities and environment-variable names were inspected read-only. They do
  not contain this source candidate and fail the proposed environment/public
  contract. Actual staging runtime roles, Redis replica behavior, and
  disposable two-tenant execution remain unverified.

## ImpactStatementDraft

This task intentionally changes authentication, authorization, runtime database requirements, environment contracts, and deployment gates. It must not change customer data or enable experimental route surfaces. Existing public response models should remain stable unless the approved plan explicitly excludes a route from public OpenAPI.

## Execution Readiness View

- Intent lock: close the confirmed shared-admin-key boundary and make tenant isolation/revocation release-verifiable.
- Scope fence: only approved FSMA routers and always-mounted core/status/webhook routes; optional routers remain 404.
- Owner constraints: `services/admin` owns human/workload admin authorization; `services/shared` owns RLS/revocation primitives; `server/main.py` owns composition only.
- Compatibility boundary: a temporary legacy-key migration path may exist only behind an explicit disabled-by-default flag and is never release-approved.
- Retirement boundary: remove the flag, key configuration, cookie/header forwarding, and callers before final approval.
- Test obligations: negative authorization paths, route classification, two-role RLS probes, replica revocation behavior, docs/OpenAPI contracts, CSRF/SSRF guards.
- Review gates: spec compliance, code quality, focused tests, owning suites, then deployment checks.
- Rewind rule: any inert RLS, permissive revocation, unclassified enabled route, or surviving active master-key path returns the slice to implementation.
- Evidence boundary: source tests can prove code contracts; only authenticated staging/deployment checks can prove release readiness.
