# Production-risk remediation — 2026-09-10

Candidate base: `22fc9a6b07186f5bae544f9ce7fb383495a57295`, branch `codex/production-risk-remediation-20260910`. Seven agents worked in separate lanes with independent QA. This is local remediation evidence, not production acceptance.

## Implemented

- Regenerated the hash lock to satisfy 18 updated direct dependency floors and two transitive pins; no requirement floors or gates weakened.
- Browser/session and authentication routes bypass middleware replay; webhook replay also binds its signature and current signing key. Bound API-key idempotency responses to the operation, request body and credential context and fresh API-key scopes/jurisdictions; conflicting/legacy entries return 409. Atomic reservations and ownership-checked publication prevent concurrent duplicate execution and stale-owner overwrite.
- Fixed canonical batch duplicate keys advancing a discarded chain predecessor; A,A,B now returns the same receipt for A and stores two contiguous chain rows.
- Moved readiness drivers off the event loop, bounded admission to two probes per process, bounded driver calls and the HTTP deadline, required Redis in strict deployed runtimes, and sanitized dependency errors. This changes deployed readiness behavior to 503 when required Redis fails.
- Removed optional Inflow Lab from production application outage monitoring; frontend ingestion health uses readiness.
- Made tenant/auth CI run on PR/push with disposable database roles and explicit direct-role URLs. Scheduled/requested audit checks fail visibly when configuration is absent; PRs do not call deployed audit APIs.
- Audit CLI now requires explicit complete non-empty verification, bounds HTTP calls, and does not print private error bodies. It verifies the returned segment, not full historical coverage.
- Supplier CSV preview uses a shared quote-aware parser and honest validation/commit states; frontend dependency alert repair is limited to the affected lock entry.

## Validation evidence

Counts below overlap and must not be summed as unique coverage.

- Fresh Python 3.11 environment installed the updated lock with required hashes; pip check passed; 15 updated packages imported. Dependency-sensitive ingestion/auth/guard suites: 191 passed.
- Final parent combined middleware/readiness/batch/CLI/workflow regression run: 150 passed on the updated lock, including fresh API-key scope/jurisdiction binding. An intermediate stale alternate-key fixture failed and was corrected to use a valid second credential; expected 409 was preserved.
- Parent CLI/security-workflow/uptime/inventory/Alembic/RLS static regression run: 63 passed on the updated lock.
- Independent QA combined backend regression selection: 161 passed on the updated lock before the final scope-snapshot addition; final security owner selection: 111 passed. Real disposable Redis verified concurrency across two app instances. Independent QA reviewed the final scope-snapshot helper and found no concrete blocker; authorization-table regressions use mocked database rows.
- Evidence lane: 97 focused tests passed. A disposable native PostgreSQL synthetic-schema probe executed the production batch writer with SELECT/INSERT-only permissions, verified A,A,B yields two valid chain rows, and verified rollback preserves counts. Cluster stopped and removed. This was not full Alembic/RLS/HTTP-export acceptance.
- Scoring review: 129 tests passed. Supported webhook/EPCIS/remediation writers preserve legacy scoring inputs; no demonstrated omission justified rewriting the scorer.
- Frontend: clean npm ci installed 793 packages; 30 focused regressions passed with the updated dependency tree. TypeScript passed; full lint reported zero errors and 35 existing warnings. Temporary workspace dependency symlink removed. Local npm policy withheld five install scripts; browser E2E remains unrun.
- Workflow actionlint and diff whitespace checks passed. Commit hooks also normalized Python formatting and the existing server import order.

## External blockers and remaining risk

- Railway production deployment `172152d1-6787-4ce9-9504-8470a0253134` and staging `af902cd7-98ba-44b8-aa0c-576effc80047` failed for the base SHA. Staging logs require MIGRATIONS_DATABASE_URL. Production failure cause was unavailable from returned logs. Do not substitute a privileged runtime URL.
- GitHub security run `34307820114` reports 322 historical secret findings across 2730 commits. Credential validity/revocation is not established by the count. Owner-backed classification and revocation evidence remain required; nothing was suppressed or rotated.
- Approved restore evidence, serving backend SHA, deployed restricted roles and migration convergence remain unverified. Branch-protection API returned 403; enforced contexts remain unverified.
- Hosted Linux lock freshness and the disposable migration/security job passed for initial PR commit 852cbe91: 199 tenant/security tests, fresh and repeated restricted migration-runner paths. Follow-up commits require their own checks. Manifest-bound deployed two-tenant authenticated ingest/replay/export acceptance remains unrun.
- API-key scope changes invalidate prior receipts, browser/session/auth requests always execute canonical authentication, and webhook proof changes invalidate cached receipts. Billing/rate-limit changes can still permit retrieval of a previously authorized receipt without new handler execution; broader dynamic policy remains a documented boundary. Uncertain execution can retain a reservation until expiry; default degraded Redis mode does not guarantee exactly-once behavior.
- Readiness admission now caps submitted/running probes at two per process even after timeout or cancellation. HTTP timeout cannot terminate a native driver; two permanently stuck calls keep readiness at 503 until recovery or restart. Timeout/cancellation floods and subsequent slot recovery pass regression tests.
- Initial validation performed no deployment, live migration or credential mutation. The user subsequently authorized committing and opening a PR; hosted validation is the next gate.

## Next actions

1. Review the local diff and run hosted CI against the final candidate, including the disposable restricted-role security job.
2. Complete owner credential dispositions and approve an isolated restore rehearsal.
3. Provision the dedicated staging migration identity through the provider, then verify exact SHA/schema/roles and two-tenant ingest-to-independent-export acceptance before production rollout.

## PR follow-up

PR #3085: https://github.com/regengine/RegEngine/pull/3085. Initial commit852cbe91 passed hosted lock freshness and tenant/security199 tests. Historical Gitleaks remains322 findings across2731 commits; the staged patch scan was clean. These are different scopes. The source review adds bounded readiness admission and replay authorization exclusions as follow-ups. See production-release-owner-actions-2026-09-10.md for sanitized current provider evidence and exact owner actions.

Follow-up local validation: 27 readiness tests (bounded admission under cancellation/timeout floods), 122 idempotency/session/refresh/HMAC tests, and independent review pass. Simulator CI cannot read its private pinned repository until the owner configures the new read-only INFLOW_LAB_READ_TOKEN secret; no credential was supplied and no gate was disabled.

Automated-review follow-up: legacy D/d/depletion aliases now normalize directly to shipping in frontend and backend, matching distribution/distribute/di. Previously backend normalized to unsupported distribution and auto-filled receiving with a warning. Payload-level regressions verify shipping survives normalization without warnings; A subsequent fix below blocks unknown aliases rather than fabricating receiving events. Focused validation:44 backend tests,34 frontend tests, TypeScript and targeted ESLint passed.


## Continued acceptance and remediation

- At commit `3f1cdea048bf5f52cb822456f8422718460e2a11`, hosted checks completed: 90 passed, three failed, six skipped. Failures are the historical Gitleaks corpus and missing private simulator credential (including its aggregate gate). Hosted frontend build, unit/lint and Chromium authentication checks passed, as did migrated database, all four seeded migration rehearsals, and 199 tenant/security tests. These results apply to that commit; later changes need fresh checks.
- Supplier uploads now reject unknown, empty, or missing event types. Commit revalidates original parsed input so sessions validated by older code cannot commit fabricated receiving classifications. Sessions without original input require re-upload. Other field defaults remain unchanged. Implementation selection: 92 passed; independent QA selection: 80 passed. These counts overlap. Previously persisted classifications require an owner audit, not automatic rewriting.
- The complete sanitized historical inventory is in [security-findings-2026-09-10](security-findings-2026-09-10/README.md): 322 occurrences, 306 unique fingerprints; 151 demonstrably synthetic/noncredential, 87 test fixtures with issuance unverified, and 84 unresolved. Nothing was suppressed or rotated.
- Pinned Inflow Lab commit `78050ae78c72a348a518b6d48bdeae7424d772da` passed its unmodified signed live-trial script against the isolated local restricted-role service: contract version 2 on both sides, one mock delivery, one live delivery, zero failed deliveries. This does not supply the missing CI token or establish deployed acceptance.
- Full disposable Alembic/restricted-role acceptance now covers authenticated two-tenant ingestion, same-key replay, fresh-key durable deduplication, 409 body conflict, invalid-key and cross-tenant rejection, 500-event batches, export verification and tamper rejection. Loading the standard rule catalog exposed an untyped nullable PostgreSQL parameter; casting its NULL check to UUID fixes rule-enabled ingestion without changing tenant filters. Both nullable/non-null psycopg3 regressions fail before and pass after the fix. The seeded batch accepted 500 events, persisted 7,000 rule evaluations, and independently verified its export. See [local acceptance artifacts](local-acceptance-2026-09-10/README.md) for exact candidate provenance, counts, timing, reproduction, and limits. Local rule-catalog seeding does not establish hosted rule configuration.
