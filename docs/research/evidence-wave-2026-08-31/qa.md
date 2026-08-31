# Independent QA evidence — 2026-08-31

Role: planner, QA lane. Scope: offline inspection and controlled experiments against the existing canonical persistence and FDA export code. Product source was not changed by this lane. The prior InFlow commit-gate patch is a separate, unintegrated worktree and was not retested or duplicated here.

## Decision-relevant results

| Claim | Evidence and result | Reality Level | Boundary |
|---|---|---|---|
| The focused regression suite is green. | **Falsified:** 231 passed, 5 failed, 0 skipped in 4.20 s across eight existing files. All five failures search for obsolete `SET LOCAL app.tenant_id` SQL text. | **5 — controlled experiment** | This is neither the full suite nor a deployment test. |
| Canonical writer calls currently bind tenant context before other SQL. | Independently recorded `SELECT set_config('app.tenant_id', :tid, true)` as first SQL in single persistence, batch persistence, ingestion-run creation, and completion. Invalid UUID and mixed-tenant batch rejected before SQL. | **5 — controlled experiment** | Fake sessions prove emitted SQL and ordering, **not actual PostgreSQL RLS enforcement, connection pooling, race safety, commit durability, or tenant isolation in deployment**. |
| Public SDK verifies the valid-chain package emitted by the current FDA package helper. | **Confirmed after integration:** actual `_build_fda_package` output returns status `0`; all four declared hashes and the Merkle root match. The preserved baseline returned status `1` because the generator lacked `path` and Merkle metadata. | **5 — controlled experiment** | Helper output is real application code; event data and chain-verification object are synthetic. HTTP auth, DB reads, persistence and real evidence were not exercised. Passing proves internal consistency for the supported package contract, not authenticity or source truth. Separate security tests confirm invalid-chain rejection. |
| Public SDK detects changed data against an unchanged manifest. | Synthetic bundle passes intact; changing CSV quantity without changing manifest fails. Missing declared file and inconsistent Merkle leaves fail. | **5 — controlled experiment** | Proves integrity relative to a supplied manifest, not authenticity or provenance. The integrated generator now emits this supported manifest shape, but the negative cases remain synthetic. |
| Public SDK proves publisher identity or detects every modification to a ZIP. | **Falsified:** changed CSV plus recomputed manifest passes. The preserved baseline also accepted an undeclared member; integrated hardening now rejects it as `bundle INVALID`. | **5 — controlled experiment** | These findings do not break SHA-256. The verifier still trusts the manifest supplied inside the same archive, so it establishes internal consistency rather than publisher identity or source truth. |
| Public SDK handles every malformed manifest as a clean verification failure. | **Falsified:** valid JSON with top-level `[]` raises `AttributeError`. | **5 — controlled experiment** | One bounded malformed-input case; no archive bombs or resource exhaustion attempted. |
| All export routes share a 10,000-row hard output cap. | **Not established:** v2/recall over-limit tests pass; legacy `/export/all` limits its initial query then expands selected TLCs without a final row cap. | **5** for v2/recall mocked route behavior; **1 — logical** for legacy output-cap risk from source | SQL execution, actual data distribution and external endpoint behavior remain unverified. |

The core source-of-truth nuance: `CANONICAL_OWNERSHIP.md:15` identifies `fsma.traceability_events`; `services/ingestion/app/fda_export/queries.py:374` confirms v2 reads it. Other export routes and chain verification still use `CTEPersistence` / legacy events. Do not infer that all exports are canonical simply because the v2 route is. The generic helper's legacy attestation is overridden with canonical provenance by the v2 route (`router.py:1110` onward).

## Reproduction and environment

Commands run from the repository root:

```sh
env -i PATH=/usr/bin:/bin .venv/bin/python docs/research/evidence-wave-2026-08-31/qa_probe.py pytest > docs/research/evidence-wave-2026-08-31/qa-pytest-results.txt 2>&1
env -i PATH=/usr/bin:/bin .venv/bin/python docs/research/evidence-wave-2026-08-31/qa_probe.py artifacts > docs/research/evidence-wave-2026-08-31/qa-artifact-results.json 2> docs/research/evidence-wave-2026-08-31/qa-artifact-stderr.txt
```

The second command above produced the preserved baseline artifact. The same
artifact mode was rerun after package integration, and its sanitized output is
[`qa-artifact-results-integrated.json`](qa-artifact-results-integrated.json).
The tracked copy replaces the local executable path and synthetic package digest
with explicit placeholders; rerun the probe to recover ephemeral raw values.

The supplied interpreter resolves to the project's `.venv/bin/python`; Python 3.12.2, Darwin arm64. Installed versions actually observed: pytest 9.0.3, pytest-asyncio 1.3.0, FastAPI 0.136.0, Pydantic 2.13.2, SQLAlchemy 2.0.49, HTTPX 0.28.1, fpdf2 2.8.7. No dependencies were installed.

The launcher clears environment variables, disables dotenv and plugin autoload, disables bytecode/cache writes, and installs a Python audit hook denying internet-socket creation, DNS, socket connects/binds, SQLite connections and subprocesses. Local Unix sockets used by asyncio remain allowed; connect/bind are denied. Persistence is mocked. No live service, database, credentials or user data is used. This is a guard against accidental I/O in trusted repository tests, not a security sandbox for hostile native code. Selected tests may supply their own static test-only auth defaults.

The first artifact invocation completed the probes but failed while formatting platform metadata because `platform.platform()` attempted a subprocess, correctly denied by the hook. The reporter was changed to `os.uname()` and the whole artifact experiment reran successfully, exit 0. No product code or safety guard was changed to make it pass.

Exact pytest invocation inside the launcher:

```text
-p pytest_asyncio.plugin -p no:cacheprovider -o addopts= --import-mode=importlib --asyncio-mode=auto -q -ra
tests/shared/test_canonical_event_idempotency_key.py
tests/shared/test_canonical_persistence_hardening.py
tests/shared/test_canonical_persistence_tenant_context.py
services/ingestion/tests/test_webhook_router_v2_enforcement.py
services/ingestion/tests/test_fda_export_service_1342.py
services/ingestion/tests/test_fda_export_queries_1342.py
services/ingestion/tests/test_fda_export_audit_logging.py
services/ingestion/tests/test_fda_export_router_1342.py
```

Five failures preserved in `qa-pytest-results.txt`:

1. `TestCompleteIngestionRunTenantScope_Issue1263::test_update_sets_rls_tenant_context_for_defence_in_depth`
2. `TestTenantContext_Issue1265_PersistEvent::test_persist_event_sets_tenant_context_before_advisory_lock`
3. `TestTenantContext_Issue1265_PersistEvent::test_persist_event_binds_tenant_id_from_event`
4. `TestTenantContext_Issue1265_PersistEventsBatch::test_batch_sets_tenant_context_before_advisory_lock`
5. `TestTenantContext_Issue1265_CreateIngestionRun::test_create_ingestion_run_sets_tenant_context_before_insert`

The current shared helper is `services/shared/tenant_context.py:344` (SQL at line 421). Assertions are stale at `tests/shared/test_canonical_persistence_tenant_context.py:48` and `tests/shared/test_canonical_persistence_hardening.py:443`. The separate probe asserts the emitted current SQL plus the exact synthetic tenant binding; it does not rewrite, suppress, or relabel failing existing tests.

## Scale and phase transitions

These are **Level 5 controlled local observations**, one run per scale, repeated synthetic event dictionaries, no DB/auth/network, warm interpreter. `_generate_csv_v2` generates the bytes; a synthetic one-file SDK-compatible ZIP wraps them. Packaging below is not the application's FDA package schema. Repetition compresses extremely well and is **not a representative storage/compression ratio**. This is component timing, **not production throughput or latency**.

| Rows | CSV bytes | CSV formatting | Synthetic ZIP creation | Public SDK verification |
|---:|---:|---:|---:|---:|
| 1 | 1,022 | 0.037 ms | 0.165 ms | 0.087 ms |
| 10 | 4,127 | 0.199 ms | 0.244 ms | 0.092 ms |
| 100 | 35,177 | 0.862 ms | 0.213 ms | 0.080 ms |
| 1,000 | 345,677 | 9.421 ms | 1.530 ms | 0.352 ms |
| 10,000 | 3,450,677 | 97.052 ms | 8.562 ms | 2.100 ms |

Meaningful transitions found in code and focused tests:

- **501 submitted events:** webhook request model caps batches at 500 (`services/ingestion/app/webhook_models.py:236`). The model limit was inspected, not separately load tested here. **Level 1**.
- **5,001 exported PDF rows:** PDF helper renders at most 5,000 with a warning (`fda_export_service.py:403`); focused existing truncation tests passed. PDF is not the full dataset at this scale. **Level 5**, synthetic formatter test.
- **10,001 matching v2/recall rows:** synchronous endpoints return HTTP 413 with narrow-filter/offline-export guidance (`router.py:1026`, `recall.py:130`); focused route tests passed with persistence faked. `queries.py:385` fetches at most 10,001 rows for that check. **Level 5**, controlled route test.
- **100,000 or 1,000,000 total events:** deliberately not materialized. A hypothetical complete workflow using <=10,000-record pieces needs at least 10 or 100 pieces respectively (**Level 2 arithmetic**); this does **not** establish that the available filters can partition every dataset, that an offline worker exists, or that pieces constitute one consistent snapshot. A single hot lot/date range is a useful adversarial dataset for the next test.
- **Windows over 90 days:** broad v2 export requests require bounded dates; exact TLC queries have different validation behavior (`router.py:984`). This is a workflow transition as well as a row-count transition. **Level 1 source observation**.
- **Concurrency and failure:** per-tenant advisory locks and transactional graph publication affect scaling; fake-session passes do not measure contention, lock duration or real rollback behavior. No millionth-event economics claim follows from these timings.

## Next experiments, ranked by decision value / cost

| Question | Method / success condition | Cost and dependencies | Next decision |
|---|---|---|---|
| Can a recipient verify an actual FDA export with the advertised tool? | The integrated valid-chain generator → verifier path passes locally; changed content, invalid chain, manifest/chain disagreement, and undeclared/duplicate/unsafe members fail. Add explicit unsupported-version, malformed-manifest and deployed HTTP cases. | Small follow-up plus optional disposable service environment; no customer data needed. | Keep the supported contract explicit; do not extend the result into authenticity or source-truth claims. |
| Are green unit tests compatible with actual tenant enforcement? | Update stale SQL-shape assertions while preserving ordering/UUID checks, then run two-tenant PostgreSQL transaction/pool-reuse tests on disposable infrastructure. Success: unauthorized read/write denied; rollback/connection reuse does not leak tenant context. | Small test repair plus approved disposable PostgreSQL; no production credentials. | Only real DB experiment moves tenant-enforcement confidence beyond fake SQL calls. |
| Does a high-volume recall produce a complete, consistent export? | Load a deliberately skewed synthetic tenant into disposable PostgreSQL, >10k same-TLC rows plus other TLCs; compare canonical eligible count, downloadable count and artifact identities under concurrent ingestion. | Moderate; disposable DB and clearly scoped local dataset. | Decide whether bounded MVP manual partitioning suffices or queued snapshot export is required. |

## Independent frontend repair review

**Verdict: CSV repair is suitable for local integration at Level 5 for the exercised mocked UI/client behavior. It is not a real-file persistence or pilot-readiness result.** The frontend implementer, not this QA lane, changed the application files. This review examined the seven-file CSV patch against the actual `csv_templates.py` response path (rows 603–632), then reran the focused tests independently.

The patch corrects the TypeScript return contract of `ingestFile` from a document job to accepted/rejected CSV counts; the HTTP endpoint, auth headers, CSRF handling and tenant selection remain the existing ones. Both upload views now expose accepted/rejected totals, row errors and KDE warnings without inventing a document job. Zero acceptance is displayed as no rows imported; partial acceptance is distinct from completion. The file selector now promises CSV/5 MB, matching the existing endpoint's format and size limit. Error detail objects/arrays become displayable strings while retaining the original response for callers.

Independent review found that the first success-response guard did not validate event/error and warning shapes used by `.filter`/`.map`. The implementer added narrow checks. My first run collected the three new tests before the fix, independently reproducing **3 failed / 32 passed** (1.42 s). Raw output is preserved in `qa-frontend-red-results.txt`. After the source was marked stable, the identical six-file command produced **35 passed / 0 failed / 0 skipped in 1.40 s**, recorded in `qa-frontend-results.txt`. This red-to-green claim is about malformed-response guards, not the implementer's earlier broader CSV baseline.

Environment independently observed: Node v26.7.0, npm 11.19.0, Vitest 4.1.7, existing node_modules symlink to the original workspace. No dependencies installed. Commands ran from `frontend/`, with environment cleared and `qa_no_network.cjs` preloaded. It denies unmocked sockets, DNS and fetch in trusted tests; it is not a hardened sandbox for hostile native code.

```sh
env -i PATH=/opt/homebrew/bin:/usr/bin:/bin NODE_OPTIONS=--require=../docs/research/evidence-wave-2026-08-31/qa_no_network.cjs npm run test:run -- src/__tests__/pages/ingest-csv.test.tsx src/__tests__/pages/data-import.test.tsx src/__tests__/lib/api-client-review.test.ts src/__tests__/pages/ingest-handoff.test.tsx src/__tests__/components/FieldCaptureClient.test.tsx src/__tests__/hooks/useSync.test.tsx --reporter=dot
env -i PATH=/opt/homebrew/bin:/usr/bin:/bin NODE_OPTIONS=--require=../docs/research/evidence-wave-2026-08-31/qa_no_network.cjs npm exec -- eslint src/lib/api-client.ts src/types/api.ts src/app/ingest/page.tsx src/app/tools/data-import/components/DataImportClient.tsx src/__tests__/pages/ingest-csv.test.tsx src/__tests__/pages/data-import.test.tsx src/__tests__/lib/api-client-review.test.ts
env -i PATH=/opt/homebrew/bin:/usr/bin:/bin NODE_OPTIONS=--require=../docs/research/evidence-wave-2026-08-31/qa_no_network.cjs npm exec -- tsc --noEmit --project ../docs/research/evidence-wave-2026-08-31/qa_frontend_tsconfig.json
```

The preserved baseline scoped ESLint artifact has **exit 0**, zero errors and one `react-hooks/set-state-in-effect` warning at the then-current `ingest/page.tsx:98`; raw output remains in `qa-frontend-lint.txt`. After integration, the current changed-file ESLint selection exits 0 without findings. Scoped TypeScript, using the checked-in experimental config plus Next/test setup and transitive imports, exits 0 with no diagnostics; the original raw output remains in `qa-frontend-typecheck.txt`, and the final root rerun includes the added auth/Admin files. `git diff --check` passed. Broad frontend build/typecheck, deployed browser rendering, network authentication and live uploads were not independently run by this lane.

### Post-integration frontend security review

A later integration review found adjacent boundaries outside the original CSV
response repair. The auth provider now refuses to publish cookie-managed state
when the server cookie write fails. The upload page awaits that write before
starting an upload, keeps the submit control pending, and uses a synchronous
guard against duplicate submissions. The client accepts an `accepted` event
only when it has a nonempty `event_id`, two 64-hex evidence hashes, and no event
errors. Three malformed accepted-event responses are rejected. The two focused
CSV files pass **31 tests**; the auth/CSV/Admin selection passes **63**, and the
final ten-file frontend security selection passes **145**. Scoped TypeScript
and changed-file ESLint pass. These mocked tests establish client ordering,
failure handling and response validation, not live cookie, tenant, network, or
persistence behavior.

Remaining assessment: no blocking defect found in the final CSV diff. The passing mobile/offline tests mock `ingestFile`; they do not establish photo persistence. Existing `FieldCaptureClient.tsx:334` and `use-sync.ts:111` send JPG files to the same CSV endpoint; this predates the patch and remains a separate unsupported workflow. The UI displays server totals accurately but cannot prove every original source row was accounted for, persisted or exported. A real consented file must be reconciled end to end before upgrading those claims.

Files changed: this `qa.md`, experimental `qa_probe.py`, `qa_no_network.cjs`, `qa_frontend_tsconfig.json`, and recorded QA result files. What changed: reproducible evidence only; no production logic, API, schema, auth, billing or deployment configuration changed by this lane. Tests run: eight existing Python test files plus independent artifact/tenant probes, six original frontend test files, post-integration frontend security selections, and scoped frontend lint/typecheck. What passed: 231 existing Python tests at baseline; all expected outcomes in the controlled probes, including the integrated valid-chain generated-package success, undeclared-member rejection, and preserved content-change negatives; 35 original final frontend tests; 145 tests in the final ten-file frontend security selection; scoped lint/typecheck. Separate focused verifier tests cover `PARTIAL`, `UNVERIFIED`, manifest/chain disagreement, generic compatibility, duplicate and unsafe members. What was not tested: full suite, live services, PostgreSQL RLS, real concurrency/commits, upstream record truth, live customer export, external auditor acceptance, 100k/1m throughput. Remaining risks: untrusted manifest limitations, unsupported/legacy package behavior, malformed-manifest exception handling, incomplete high-volume export behavior, stale Python test expectations, real tenant isolation and photo persistence unverified. Recommended next step: add remaining package-version/malformed-manifest cases, then run the smallest disposable-PostgreSQL two-tenant and skewed-volume experiments.
