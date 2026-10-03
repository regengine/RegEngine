# Frontend QA pass

PR: opened by orchestrator

CI status: pending at time of writing

## Scope and outcome

Verified checkout, branch `qa/2026-10-02-sweep`, origin and worktree before edits. Resumed prior inventory on 2026-10-03 at 00:35:41 UTC. No product behavior, dependencies, lockfiles or configuration were changed. Frontend test changes are the new `frontend/src/__tests__/lib/qa-sweep-gs1.test.ts` and one appended expected-failure case in existing `frontend/src/__tests__/hooks/useSync.test.tsx`.

The locked install, lint, production build/TypeScript check and complete Vitest unit/component suite pass locally. Two new GS1 parser defects are reproduced with six strict expected-failure cases. An additional expected-failure hook case demonstrates an ownerless offline photo being dispatched after an account switch. Local HTTP confirms the camera policy denies camera access on the scanner page.

Counts: Critical=0 High=1 Medium=3 Low=0

The review-pr skill was applied to prioritize executable correctness and data-integrity evidence. FE-C1 covered build/dependency reproducibility; FE-C2 focused on traceability input boundaries and the existing auth/session/API contract suites. FE-C3 browser execution is shared with the UX group, which owns isolated local server, browser/network control, screenshots and performance artifacts. See [UX-REPORT.md](UX-REPORT.md).

## Executed checks

| Check | Outcome | Evidence |
| --- | --- | --- |
| Locked `npm ci --ignore-scripts --no-audit --no-fund` | Pass; 793 packages, 6.95s; package files unchanged | [Install](artifacts/frontend/20261003T003557.257409Z-locked-install.txt) |
| `npm run lint` | Pass; 0 errors, 41 existing warnings; design-lint clean across 676 files | [Lint](artifacts/frontend/20261003T003655.183617Z-frontend-lint.txt) |
| `npm run build` on local Node 26.7.0 | Pass; optimized build, TypeScript and all 187 static pages generated | [Build](artifacts/frontend/20261003T003655.185291Z-frontend-build.txt) |
| CI-family Node 20.20.2 production build | Pass; same package lock and product sources; Node 20 matches `.nvmrc` major version | [Node 20 build](artifacts/frontend/20261003T003946.746162Z-node20-build.txt) |
| Baseline full Vitest/coverage, Node 20 | 136 files passed; **1027 passed, 2 skipped**; configured coverage thresholds passed | [Before](artifacts/frontend/20261003T003945.430584Z-node20-baseline-coverage.txt) |
| Added traceability boundary tests | **6 passed, 6 expected fail**; includes 1,000 generated GTIN check-digit checks | [New tests](artifacts/frontend/20261003T003816.353936Z-fe-c2-gs1-regressions.txt) |
| Offline account-switch regression | **3 existing passed, 1 new expected fail**; unwrapped temporary copy fails at the intended assertion and shows exactly one upload call | [Expected-failure run](artifacts/frontend/20261003T004333.208567Z-fe-c2-offline-tenant-regression.txt), [raw assertion evidence](artifacts/frontend/20261003T004541.557371Z-fe004-unwrapped-negative-control-local-setup.txt) |
| Final full Vitest/coverage, Node 20 | 137 files passed; **1033 passed, 7 expected fail, 2 skipped**; configured coverage thresholds passed | [Final after](artifacts/frontend/20261003T004435.934209Z-node20-final-coverage.txt) |
| ESLint on both changed test files | Pass | [Focused lint](artifacts/frontend/20261003T004437.368428Z-final-added-tests-lint.txt) |

The test pyramid is appropriate here: the existing suite exercises the client/server proxy contracts and form state cheaply, while browser checks cover browser-only headers, keyboard behavior and rendering. Added bounded generation avoids an extra dependency: 100 independent GTIN bodies each test all ten candidate check digits; equivalence classes cover encoded lot delimiters and invalid calendar dates. Expected failures assert the intended behavior and will fail on an unexpected pass, prompting their conversion into ordinary regression tests after a product fix.

Existing passing security/contract suites include `enforce-tenant-match.test.ts` (13), `compliance-proxy-auth-boundary.test.ts` (11), `review-id-validation.test.ts` (18), `inflow-workbench-read-proxy.test.ts` (9), `public-openapi.test.ts` (4), RBAC tests (10), and the CSRF/session/auth suites. These isolated tests do not establish live backend authorization or database isolation.

## Findings

| ID | Severity | Group | Title | Exact reproduction | Expected vs actual | Evidence | Suggested fix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| FE-001 | High | Frontend | Scanning valid lot codes silently truncates the lot identifier | Execute `qa-sweep-gs1.test.ts`, cases named `FE-001`; pass `010950600013435210LOT-10-ABC\x1d17260930` to `parseGS1`, where `\x1d` is the ASCII group separator. Repeat with `LOT-21-ABC` and `LOT-17260930`. | Expected lot preserved through its explicit group separator. Actual `tlc` is `LOT-`; `LOT-21-ABC` also invents serial `-ABC`. Field capture copies the truncated identifier into the ingest payload. Persistence was not exercised. | `frontend/src/lib/gs1-parser.ts:75` and `:179`; `frontend/src/components/mobile/FieldCaptureClient.tsx:192` and `:224`; test `frontend/src/__tests__/lib/qa-sweep-gs1.test.ts:33`; [actual results](artifacts/frontend/20261003T003912.837095Z-fe-c2-gs1-defect-evidence.txt) | Respect variable-length AI boundaries: explicit FNC1/group separator, preserved parenthesized AI delimiters, end-of-input and the field's maximum length; do not treat ordinary AI-like digits within lot text as delimiters. |
| FE-002 | Medium | Frontend | Malformed Digital Link encoding throws out of scan handlers | Execute the three `FE-002` cases; parse `/01/09506000134352/10/%`, then `%ZZ` and `%E0%A4`. These can be pasted into the public scanner or supplied to receiving/field capture handlers. | Expected rejected input with recoverable feedback. Actual uncaught `URIError: URI malformed` from `decodeURIComponent`; the callers invoke the parser without a catch. | `frontend/src/lib/gs1-parser.ts:107`; `frontend/src/app/tools/scan/page.tsx:30`; `frontend/src/app/dashboard/receiving/page.tsx:158`; test `frontend/src/__tests__/lib/qa-sweep-gs1.test.ts:42`; [actual results](artifacts/frontend/20261003T003912.837095Z-fe-c2-gs1-defect-evidence.txt) | Catch malformed URI decoding at the parser boundary and return an explicit invalid-scan result; display a recoverable validation error in callers. |
| FE-003 | Medium | Frontend | Global Permissions-Policy disables the camera scanner | Evaluate exported `next.config.js.headers()` or GET local `http://127.0.0.1:3104/tools/scan`; HTTP 200 emits `camera=()`. The scanner calls `Html5Qrcode.start` with `facingMode: environment`. | Expected scanner pages can request same-origin camera permission. Actual site policy denies camera regardless of a user's permission choice. Physical camera capture is not tested. | `frontend/next.config.js:52`; `frontend/src/app/tools/scan/page.tsx:42`; [configuration execution](artifacts/frontend/20261003T004007.254000Z-fe-c2-camera-policy-evidence.txt); [local response header](artifacts/meta/20261003T004328.548570Z-local-camera-policy.txt) | Permit `camera=(self)` on the narrow set of camera-scanner routes, while retaining denial elsewhere and keeping microphone/geolocation restrictions. |
| FE-004 | Medium | Frontend | Offline photos lose tenant ownership and are replayed after an account switch | Execute `useSync.test.tsx` case `FE-004`: queue a synthetic ownerless photo while tenant A is offline, unmount A, mount authenticated B with the same queue, bring online and invoke manual sync. | Expected queued A data remains isolated from B; legacy ownerless data is quarantined. Actual mocked upload mutation is called once in B's hook. Source shows shared IndexedDB without owner fields and current-session cookie requests. This proves client dispatch only, not actual IndexedDB/login/server roundtrip or persisted cross-tenant disclosure. | `frontend/src/lib/db.ts:23`, `:65`, `:86`, `:95`; `frontend/src/hooks/use-sync.ts:108`; `frontend/src/lib/auth-context.tsx:445`; `frontend/src/lib/api-client.ts:282`; `frontend/src/__tests__/hooks/useSync.test.tsx:166`; [unwrapped assertion evidence](artifacts/frontend/20261003T004541.557371Z-fe004-unwrapped-negative-control-local-setup.txt) | Store user/tenant ownership on offline entries, scope every read/replay to the current session, quarantine unowned legacy entries, and invalidate active replay on logout/account switch. Preserve unsynced evidence rather than silently deleting it. |

FE-001 is prioritized over UI polish because it can produce an incorrect traceability identifier before submission. For FE-004, the present upload client sends photos to the CSV endpoint; backend source review identifies unhandled UTF-8 decoding before normal event persistence (BE-004; see the backend report for its route-test outcome). That limits the demonstrated consequence; it does not establish a successful upload into B. No bug fix was applied.

## Coverage and gaps

The authoritative comparison uses **Node 20.20.2 for both runs**, the identical 196 instrumented product files, the existing coverage exclusions, and unchanged coverage thresholds. Before was captured before FE-004 was appended and excluded the new GS1 QA test; final after includes all thirteen added cases. Summary JSON includes per-file denominators, so the measurement is auditable.

| Metric | Before covered/total | Before | After covered/total | After |
| --- | ---: | ---: | ---: | ---: |
| Statements | 6215/9184 | 67.67% | 6219/9184 | 67.71% |
| Branches | 4664/7755 | 60.14% | 4668/7755 | 60.19% |
| Functions | 1285/2142 | 59.99% | 1285/2142 | 59.99% |
| Lines | 5825/8327 | 69.95% | 5827/8327 | 69.97% |

GS1 parser lines improve **92/96 → 94/96** (95.83% → 97.91%), statements **108/120 → 112/120**, and branches **82/99 → 86/99**. This is the only per-file coverage change in the final comparison. An intermediate run varied by one statement/branch in the unchanged developer-key route; its original artifact is retained, but it is not the final comparison. The ownership test exercises already-covered lines while asserting a new security invariant. See [comparison](artifacts/frontend/coverage-comparison.json), [changed files](artifacts/frontend/coverage-changed-files.json), [before per-file summary](artifacts/frontend/coverage-node20-before-summary.json), and [after per-file summary](artifacts/frontend/coverage-node20-after-summary.json).

These percentages describe Vitest's collected files, **not the entire frontend**. The source inventory found 672 TS/TSX files excluding test files and declarations, including type-only files; many public routes, loading/error boundaries, camera components, auth-provider integrations and helper modules are absent from this coverage report. Weak measured areas include dashboard heartbeat (2% lines), alerts (10.76%), hooks `use-api` (25.97%), `use-fsma` (32.35%), and API-client lines (52.73%). Those are residual risks, not newly proven defects.

Full HTML coverage reports created by this pass were moved to `/private/tmp`; compact totals/per-file summaries and complete redacted console reports are retained in the QA artifact directory. Earlier interrupted artifacts were preserved.

## Execution limitations and dead ends

- All service and provider effects were stubbed/disabled. No deployed app, production database, credentials, billing or actual provider was exercised. Advisory-network calls are outside this task's allowed network use, so no claim of a clean dependency vulnerability audit is made here; the backend security report documents audit limits.
- Browser flows and screenshots are recorded by UX; native camera devices, actual assistive-technology speech, authenticated backend persistence and production performance remain outside this frontend pass.
- Initial lint/build/coverage used local Node 26.7.0; build and full before/after coverage were repeated on the CI-family Node 20.20.2 with the corrected Node isolation guard. CI itself remains pending. Node 20 build prints an upstream Supabase deprecation warning; it still passes.
- Gate review found a normalized-argument-array gap in the first QA-only socket guard. It was fixed immediately and six call shapes were validated using a fake socket spy, without making a network request. The authoritative Node 20 runs use the fixed guard. [Guard evidence](artifacts/frontend/20261003T003858.351825Z-network-guard-safe-spy.txt).
- The first public dependency install used scrubbed environment variables but inherited `HOME`; ordinary npm user-config discovery was not independently excluded for that initial install. No credentials were directly read or displayed. The shared logger was subsequently hardened to disable user/global npm config discovery for future installs.
- One focused ESLint invocation was nested inside a source-index command run from the repository root. ESLint could not locate the frontend config; the wrapper's outer command exited zero, but this inner lint check failed. The correction runs from `frontend/` and passes. Both outputs are retained.
- The first temporary unwrapped FE-004 witness failed during setup because Vitest could not load a setup file outside its temporary root; that failure is not defect proof. Copying the unchanged hook and setup locally fixed the harness, and the second run failed at the intended `not.toHaveBeenCalled` assertion, with exactly one upload call. The committed repository test retains its expected-failure marker.
- Next builds regenerate `frontend/next-env.d.ts`; both generated changes were inspected and restored to the exact baseline bytes. No product diff remains from build execution.
