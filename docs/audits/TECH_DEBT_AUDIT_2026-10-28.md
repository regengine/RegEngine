# Technical Debt Audit — 2026-10-28

Scope: the production repository at commit `af5beee` (branch
`claude/fervent-clarke-0aw2am`). Every count below was measured against the
working tree on this date with `wc`, `grep`, `find`, or by reading the file
named. Where an existing document already tracks an item, that document is
linked rather than restated.

Method: each item is scored on Impact (how much it slows work, 1–5), Risk
(what happens if it stays, 1–5) and Effort (1 = under a day, 5 = multi-week).
Priority = (Impact + Risk) × (6 − Effort). Effort is for one engineer working
with AI assistance alongside feature work.

Second opinion: TypeSafe Jev was asked which item to fix first and how likely
three of them are to cause an incident. Its answers are reported next to mine
in §2 and §3.

Open GitHub backlog at audit time: 3 issues, all feature follow-ups. Nothing
below is tracked there yet.

---

## 1. Summary

| # | Item | Category | Impact | Risk | Effort | Priority |
|--:|---|---|:-:|:-:|:-:|--:|
| 1 | Three schema-change channels and a stale production `alembic_version` row | Infrastructure | 4 | 5 | 3 | **27** |
| 2 | Six `app` packages collide; bare `from app.` imports; 347-line `sys.path` conftest | Architecture | 4 | 4 | 3 | **24** |
| 3 | Lint and type gates are near-empty (ruff selects 4 rule groups, mypy not a gate) | Code | 3 | 3 | 2 | **24** |
| 4 | 33 CI workflows, four of them over 850 lines, plus a workflow that exists to re-run flaky gates | Infrastructure | 4 | 3 | 3 | **21** |
| 5 | Legacy Kafka backbone still in tree and in the production image | Architecture | 2 | 3 | 2 | **20** |
| 6 | Production image carries test and optional AI dependencies | Infrastructure | 2 | 3 | 2 | **20** |
| 7 | Orientation docs disagree with the tree; duplicate doc directories; one-off reports at repo root | Documentation | 3 | 2 | 2 | **20** |
| 8 | 31 of 87 top-level scripts are referenced by nothing | Code | 2 | 2 | 1 | **20** |
| 9 | Retired six-service topology still has entrypoints, k8s manifests, a PR-time CI job, and legacy runbooks | Infrastructure | 2 | 2 | 1 | **20** |
| 10 | DB-dependent tests skip vacuously without a migrated Postgres | Test | 3 | 3 | 3 | **18** |
| 11 | Frontend API access split three ways; 8 hand-rolled proxy routes | Code | 3 | 2 | 3 | **15** |
| 12 | Legacy `cte_events` dual-write still live, with 12 non-legacy readers | Architecture | 3 | 4 | 4 | **14** |
| 13 | Blocked major upgrades and Node version drift across CI | Dependency | 2 | 2 | 3 | **12** |
| 14 | 24 source modules over 1,000 lines | Code | 3 | 2 | 4 | **10** |
| 15 | `graph_update` task type declared, never enqueued, never handled | Code | 1 | 1 | 1 | **10** |
| 16 | Frontend type looseness: 192 `any`, 14 eslint suppressions | Code | 1 | 1 | 2 | **8** |

What is **not** debt here, and should stay as is:

- Backend dependency management. `requirements.in` → hash-pinned
  `requirements.lock`, CVE floors documented inline, Dependabot with a
  7-day cooldown, `supply-chain.yml` on lock changes. This is better than
  most funded teams.
- Router gating. Production fails closed on an explicit allowlist
  (`server/router_policy.py`), and `ENABLE_EXPERIMENTAL_ROUTERS=true` is
  rejected in production.
- Frontend coverage gate. Floors were set 6 points under measured values in
  August and are enforced in CI.

---

## 2. Items in priority order

### 1. Three schema-change channels and a stale production version row — Priority 27

**Evidence**

- `alembic/versions/` holds 105 revisions; the newest is v137
  (`20261024_a3f7ce361b0e_v137_epcis_document_receipts.py`).
- `supabase/migrations/` holds 45 SQL files, the newest dated 2026-10-26.
  No document in `docs/`, `ARCHITECTURE.md`, or
  `docs/engineering/SCHEMA_CHANGE_POLICY.md` mentions this directory.
- `sql/prod-apply/` holds 8 hand-rendered apply, precheck and rollback
  scripts for v128, v131 and SEL-314.
- `DEVOPS_NOTES.md` (2026-10-20): "`public.alembic_version` on the Supabase
  project still reads `267d8053ced5` (v079) although v128 policies are
  present, so prod-apply SQL has been landing without a version bump.
  `alembic upgrade head` against this database would re-run v080–v133; do
  not run it until the version row is reconciled."
- `docs/MIGRATION_CONSOLIDATION.md` says Alembic has 10 migrations and
  describes porting Flyway files from a `migrations/` directory that no
  longer exists.
- The Docker `CMD` runs `scripts/run-migrations.sh` before Gunicorn starts.

**Why it matters**

The product promise is tamper-evident evidence. The schema that holds it has
three write paths and the recorded version is about 50 revisions behind what
is applied. Any new deploy that runs migrations is one mis-set variable from
replaying v080 to v137 on production. Jev: 0.77 confidence this is the item
to fix first; incident likelihood within six months scored 2.72 on a 0–3
scale (critical, confidence 0.73). I agree with both.

**Fix (3 days)**

1. Write a one-page ADR naming Alembic as the only channel and
   `supabase/migrations/` and `sql/prod-apply/` as rendered outputs of it,
   never hand-edited. Delete `docs/MIGRATION_CONSOLIDATION.md` or replace
   it with the ADR.
2. Reconcile the production `alembic_version` row to the revision whose
   effects are actually present, using the PRECHECK pattern already in
   `sql/prod-apply/`. Record the result in `DEVOPS_NOTES.md`.
3. Add a CI guard: fail if a file under `supabase/migrations/` or
   `sql/prod-apply/` changes without a matching Alembic revision in the
   same diff.

### 2. `app` package collision and bare imports — Priority 24

**Evidence**

- `services/{admin,compliance,graph,ingestion,nlp,scheduler}/app/` are six
  packages with the same import name.
- Root `conftest.py` (347 lines) rewrites `sys.path` before each service's
  tests collect so `from app.X` resolves to the right one.
- 20 non-test files still use bare `from app.` imports; 27 use
  `from services.<svc>.app`. Seven of the bare ones are live ingestion
  modules (`services/ingestion/app/sandbox/__init__.py`,
  `services/ingestion/app/stripe_billing/rate_limiting.py`,
  `services/ingestion/app/webhook_compat.py`,
  `services/ingestion/app/labels/gs1_128.py`,
  `services/ingestion/app/audit_export_log.py`,
  `services/ingestion/regengine_ingestion/parsers/edi_parser.py`,
  `services/ingestion/regengine_ingestion/utils/fetch_utils.py`); one is
  `services/admin/app/logging_config.py`.
- `Dockerfile` sets `PYTHONPATH=/app:/app/services:/app/services/ingestion:/app/services/admin:...`.
  In the container `app` always resolves to `services/ingestion/app`, so
  `services/admin/app/logging_config.py` would import ingestion's modules if its
  bare import path is ever exercised.
- `pyproject.toml` comments explain the hazard rather than remove it
  ("Listing multiple `services/<svc>` here would cause `app` to permanently
  resolve against whichever service sorted first").
- `pytest.ini_options.testpaths` lists `services/test_data/tests`, which
  does not exist.

**Why it matters**

Every new test file and every new module inherits a trap that already
required two CI guards (`test-suite-check.yml`, the testpaths comment for
#2923 and #3247). Jev scored wrong-module import likelihood in production
1.97 on 0–3 (high, confidence 0.60). My own read is lower for production,
because the live bare imports are in ingestion, which sorts first, but the
test-side cost is paid on every PR.

**Fix (3 days, mechanical)**

1. Rewrite the 20 bare imports to `services.<svc>.app` form.
2. Delete the seven legacy entrypoints (`services/*/main.py`,
   `services/graph/app/main.py`, 1,818 lines) or move them to
   scripts/legacy/ outside the import path. `ARCHITECTURE.md` already
   says they are not the deploy target.
3. Reduce `Dockerfile` `PYTHONPATH` to `/app:/app/services`.
4. Shrink `conftest.py` to the fixtures only; remove the `sys.path`
   switching once nothing depends on it.
5. Remove the dead `services/test_data/tests` entry from `testpaths`.

### 3. Lint and type gates are near-empty — Priority 24

**Evidence**

- `backend-ci.yml` runs `ruff check --select E9,F63,F7,F82` (syntax errors,
  invalid prints and comparisons, undefined names). `pyproject.toml`
  selects only `I` (import sorting).
- `[tool.mypy]` exists with the note "not yet a CI gate". No workflow runs
  mypy.
- 766 `noqa` markers and 223 `type: ignore` markers in non-test backend
  code.
- `BREAK-REPORT.md` records that a full `mypy .` still stops on a duplicate
  module (`tests/audit/verify_chain.py` vs
  `frontend/public/sdk/verify_chain.py`).

**Why it matters**

Three of the last five merged commits are security fixes found by external
code scanning (ReDoS, header sanitisation, shell exec, URL host checks).
`ruff`'s `B`, `S` and `PL` families catch several of those classes before
review. With one engineer, static gates are the cheapest reviewer available.

**Fix (2 days to start, then incremental)**

1. Add `F`, `E`, `B`, `S102`, `S105`–`S108`, `S113`, `S301`, `S324`,
   `S602`–`S607` to the ruff select for `services/shared/` only. Fix or
   explicitly `noqa` with a reason. Expand one service per week.
2. Add `mypy services/shared --strict-optional` as a non-blocking job,
   then make it blocking once clean. Resolve the `verify_chain.py`
   duplicate by excluding `frontend/public/sdk` from mypy.
3. Ratchet: a CI step that fails if the count of `noqa` without a reason
   rises above the committed baseline.

### 4. CI sprawl — Priority 21

**Evidence**

- 33 workflow files. `backend-ci.yml` 1,530 lines, `pr-guards.yml` 1,401,
  `pr-gate.yml` 1,123, `security.yml` 875.
- `pr-gate-frontend-rerun.yml` exists to re-run the frontend gate after a
  flaky failure. 29 lines across the three main workflows mention flake,
  retry or re-run. The e2e script in `frontend/package.json` hard-codes
  `--retries=2`.
- `infra-k8s-ci.yml` runs on PRs for manifests `docs/CODEBASE_MAP.md`
  calls retired.
- `docs/CODEBASE_MAP.md` §2 says 23 workflows.

**Why it matters**

Each PR waits on the union of these. The ingestion test leg alone has a
25-minute timeout. A founder paying per-PR wall-clock time cannot afford
duplicated jobs, and a rerun workflow institutionalises flakiness instead
of removing it.

**Fix (4 days)**

1. Measure: pull the last 30 PR runs and list job durations and failure
   causes. Decide from data which jobs are redundant with
   `pr-gate.yml`.
2. Move shared steps (checkout, Python setup, lock install) into one
   reusable workflow called by the rest.
3. Delete `pr-gate-frontend-rerun.yml` after fixing the top flaky spec it
   was created for. Drop `infra-k8s-ci.yml` with item 9.
4. Set `concurrency` groups so a new push cancels the previous run on the
   same PR, if not already universal.

### 5. Legacy Kafka backbone — Priority 20

**Evidence**

- 13 non-test modules import `confluent_kafka` or read
  `KAFKA_BOOTSTRAP_SERVERS`. The main ones total 3,505 lines:
  `services/shared/kafka_auth.py` (786), `services/shared/kafka_compat.py`,
  `services/shared/kafka_consumer_base.py`, `services/shared/observability/dlq_producer.py`,
  `services/admin/app/review_consumer.py`, `services/nlp/app/consumer/__init__.py` (1,118),
  `services/ingestion/app/kafka_utils.py`.
- `services/shared/event_backbone.py` defaults `EVENT_BACKBONE` to `pg`.
  `ASYNC_PROCESSES.md` states the backbone is the Postgres task queue "not
  Kafka".
- `confluent-kafka[schema-registry,avro]` and `fastavro` are in
  `requirements.in` and the production image.

**Fix (2 days)**

Delete the Kafka path and its dependencies. Keep `services/shared/observability/kafka_propagation.py`
only if the tracing header helpers are used by the PG path (check callers
first). `ARCHITECTURE.md` already calls this "remediation drift, not the
primary deploy contract".

### 6. Production image carries test and optional dependencies — Priority 20

**Evidence**

- `requirements.in` includes pytest, pytest-asyncio, pytest-cov,
  pytest-mock, pytest-xdist, hypothesis, aiosqlite and testcontainers with
  the comment "move to dev-requirements.txt if image size matters".
  `docker` (a testcontainers transitive) is in the lock.
- The `Dockerfile` compensates with `RUN find /app -name "test_*.py" -delete`.
- The image also ships langchain, langchain-community, langgraph,
  langsmith, openai, llama-cloud, pandas, numpy, pytesseract, pdf2image and
  pyzbar. The routers that use most of these (`nlp`, `agent_org`,
  `label_vision`, `qr_decoder`) are in `EXPERIMENTAL_ROUTERS` and never
  mount in production.

**Why it matters**

Attack surface and Trivy noise in `security.yml`, slower Railway builds,
and `--require-hashes` resolution work for packages production never
imports.

**Fix (2 days)**

1. Split `requirements.in` into `requirements.in` and
   requirements-dev.in; compile two locks; CI installs both, Docker
   installs one.
2. Move the experimental-only packages behind an extras file
   (requirements-experimental.in) that the image omits until a router
   graduates to the production allowlist.

### 7. Documentation drift and clutter — Priority 20

**Evidence**

- `docs/CODEBASE_MAP.md` claims every line was checked against the tree,
  and says: 23 workflows (there are 33), 81 `include_router` calls in
  `server/main.py` (there are 2; registration moved to
  `server/router_policy.py`), and 7 experimental routers (the frozenset
  has 15).
- `ARCHITECTURE.md` large-module table is dated 2026-07-31 and lists 13
  files; there are now 24 non-test modules over 1,000 lines.
- `docs/MIGRATION_CONSOLIDATION.md`: see item 1.
- 369 Markdown files under `docs/`; 34 carry an obsolete, superseded or
  historical banner; 53 sit in `docs/archive/` plus 2 in `docs/_archive/`.
- Duplicate directories: `docs/archive` and `docs/_archive`; `docs/schema`
  and `docs/schemas`; `nfr/` and `docs/nfr`; `runbooks/` and
  `docs/runbooks`.
- 20 Markdown files at the repo root, including one-off reports
  (`BREAK-REPORT.md`, `FIX-REPORT.md`) and `GEMINI.md`.

**Why it matters**

Agent sessions are told to read `ARCHITECTURE.md` and `CODEBASE_MAP.md`
first. Wrong counts there cost every session a verification pass, which is
exactly why `scripts/check_docs_links.py` was written for paths. Counts
need the same treatment.

**Fix (2 days)**

1. Extend `scripts/check_docs_links.py` to assert the three numeric claims
   above, or remove the numbers from the docs.
2. Merge the four duplicate directory pairs; move `BREAK-REPORT.md` and
   `FIX-REPORT.md` under `docs/engineering/` with dates in the filename.
3. Re-stamp `ARCHITECTURE.md` after items 2, 5 and 9 land, since they
   change its content.

### 8. Orphaned scripts — Priority 20

**Evidence**

31 of 87 top-level files in `scripts/` are not referenced by any workflow,
the `Dockerfile`, `railway.toml`, either runbooks directory, another
script, or the README. The largest: `scripts/verify_canonical_parity_live.py`
(1,702 lines), `scripts/backfill_canonical_from_legacy.py` (1,423),
`scripts/seed_demo_data.py` (680), `scripts/audit-issues.py` (665),
`scripts/e2e_brutal_scenario.py` (654), `scripts/jev_header_preview.py` (602).

**Fix (1 day)**

For each: delete, or add a one-line entry to a scripts/README.md naming
the runbook or workflow that uses it. The two canonical-parity scripts
belong to item 12 and should be deleted with it.

### 9. Retired topology still in tree — Priority 20

**Evidence**

- Seven legacy entrypoints (item 2), 1,818 lines.
- `infra/k8s/` with `base/` and `overlays/`, plus `infra-k8s-ci.yml` on
  every PR that touches it.
- `runbooks/` at the root: five files, each with a `LEGACY:` banner per
  `docs/CODEBASE_MAP.md`.
- `regengine/swarm/` (about 2,500 lines) gated by
  `REGENGINE_ENABLE_LEGACY_SWARM`.
- `infra/gateway/nginx.conf` is "reference-only" with its own test suite in
  the pytest `testpaths`.

**Fix (1 day)**

Move `infra/k8s`, root `runbooks/`, `regengine/swarm` and the legacy
entrypoints to docs/archive/retired-topology/ or delete them. Git history
keeps them. Remove `infra-k8s-ci.yml` and the gateway testpath.

### 10. DB-dependent tests skip vacuously — Priority 18

**Evidence**

- 170 `pytest.skip` / `skipif` sites. The most common reasons: "migrated
  Postgres with fsma schema not available" (8 sites), "Explicit disposable
  PostgreSQL required", "DATABASE_URL not set — live DB required".
- Skip sites by directory: `services/ingestion` 20 files,
  `tests/migrations` 16, `tests/shared` 14.
- CI does run `live-db-suite` against `postgres:17` and a
  `seeded-migration-rehearsal`, so production is covered. Locally, a bare
  `pytest` passes while exercising none of the RLS, migration or
  persistence paths.
- Backend coverage floors per service: compliance 80, admin 70,
  scheduler 65, graph 60, ingestion 48, shared 35 (ratcheted 2026-04-20;
  the comment in `pyproject.toml` explains the shared floor was set on an
  inflated denominator).

**Fix (3 days)**

1. Add a `pytest --require-db` option that turns the skip into a failure,
   and use it in the live-db CI job so a lost `DATABASE_URL` cannot turn
   the suite green.
2. Document the one-command local path: `docker compose -f
   docker-compose.dev.yml up -d` then `alembic upgrade head`, in
   `CONTRIBUTING.md`, and make the skip message print it.
3. Re-measure the `shared` and `ingestion` floors and ratchet them.

### 11. Frontend API access is split three ways — Priority 15

**Evidence**

- `frontend/src/lib/api-client.ts` is 1,163 lines and is imported by 15
  files under `app/`, `components/` and `hooks/`. 33 non-test files in
  those directories call `fetch(` directly.
- 30 route handlers under `frontend/src/app/api/`; 22 use `frontend/src/lib/proxy-factory.ts` (706
  lines); 8 are hand-rolled (`client-errors`, `inflow-lab/[...path]`,
  `openapi.json`, `session`, `health`, `contact`, `tools/check-access`,
  `tools/verify`).
- Largest page components: `frontend/src/app/tools/ftl-checker/components/FTLCheckerClient.tsx`
  1,299 lines, `frontend/src/app/ingest/page.tsx` 1,118, `frontend/src/app/dashboard/suppliers/page.tsx`
  1,097, `frontend/src/app/compliance/snapshots/page.tsx` 1,058.

**Fix (3 days, incremental)**

Route every backend call through `api-client.ts` or a typed hook. Convert
the 8 hand-rolled routes to `proxy-factory` where they proxy the backend
(`tools/*`, `inflow-lab`); leave `health`, `session`, `contact` and
`client-errors` as they are. Add an ESLint `no-restricted-syntax` rule
against bare `fetch(` in `src/app` and `src/components`.

### 12. Legacy `cte_events` dual-write — Priority 14

**Evidence**

- `services/shared/canonical_persistence/writer.py` calls
  `legacy_dual_write.dual_write_legacy` on both single and batch writes;
  since #1277 a failure raises and rolls back the canonical write.
- `services/shared/canonical_persistence/legacy_dual_write.py` (532 lines) is headed "TEMPORARY".
  `CANONICAL_OWNERSHIP.md` calls `cte_events` "a legacy derived copy
  (dual-write) that will be removed".
- 12 non-legacy modules still read `cte_events`, including
  `services/admin/app/supplier_onboarding_routes.py`, `services/admin/app/supplier_facilities_routes.py`,
  `services/admin/app/data_export_routes.py`, `services/admin/app/supplier_funnel_routes.py`,
  `services/shared/workflows/export_output.py` and `services/shared/supplier_data_quality.py`.

**Why it matters**

Every evidence write pays for two tables, and a legacy-table failure can
reject a valid canonical event. Jev scored six-month incident likelihood
1.98 on 0–3 (high, confidence 0.74). Effort is the limiter: the 12 readers
must be re-pointed and verified with parity checks first.

**Fix (2 weeks, in three PRs)**

1. Re-point the 12 readers to `fsma.traceability_events` one route at a
   time, each with a parity test against a seeded database.
2. Flip the dual-write to fail-open with a metric, run two weeks of
   parity via the existing `scripts/verify_canonical_parity_live.py`.
3. Remove `services/shared/canonical_persistence/legacy_dual_write.py`, the two parity/backfill scripts, and
   add a migration that drops or freezes `cte_events` and `cte_kdes`.

### 13. Blocked upgrades and Node drift — Priority 12

**Evidence**

- `dependabot.yml` ignores majors for eslint 10, typescript 7, jsdom 30,
  jest-dom 7, vitest coverage 5, next, react, react-dom, vite and vitest,
  each with a documented blocker. React stays at 18.3.
- Node: `.nvmrc` says 22; `copy-gate.yml` pins 20; one `frontend-ci.yml`
  job pins 24; `package.json` `engines` says 22 or 24. The jsdom 30
  blocker note says "CI runs Node 20".
- Python 3.11 base image; security support ends 2027-10.

**Fix (3 days)**

Pin every workflow to `node-version-file: .nvmrc`. That alone unblocks
jsdom 30 and jest-dom 7. Schedule the eslint 10 and typescript 7 pair for
when `eslint-config-next` catches up; check monthly. Plan a Python 3.12
image bump in Q1 2027.

### 14. Modules over 1,000 lines — Priority 10

24 non-test modules, up from 13 in the July table in `ARCHITECTURE.md`.
Top: `services/scheduler/service.py` 1,544, `services/shared/api_key_store.py`
1,488, `services/shared/canonical_event.py` 1,466, `services/ingestion/app/edi_ingestion/routes.py`
1,464, `services/shared/canonical_persistence/writer.py` 1,340,
`services/ingestion/app/fda_export/router.py` 1,323, `services/ingestion/app/inflow_workbench.py`
1,267, `server/main.py` 1,256, `services/graph/app/fsma_audit.py` 1,249,
`services/ingestion/app/compliance_score.py` 1,209.

Split only when a feature already touches the file, following the "likely
split direction" column already in `ARCHITECTURE.md`. `server/main.py` is
the exception worth doing on its own: the lifespan, startup checks and
worker boot are the first thing every reader meets.

### 15. `graph_update` dead task type — Priority 10

Declared in `services/shared/task_types.py` and given a 120-second
visibility timeout in `server/workers/task_processor.py`, but no production
code enqueues it and no handler is registered. `ASYNC_PROCESSES.md`
describes rows that "sit unclaimed"; today none are produced. Remove the
type and the timeout entry, or register the handler the day graph sync
moves to the queue. One hour.

### 16. Frontend type looseness — Priority 8

192 `any` usages, almost all in `frontend/src/__tests__/` (top file
`frontend/src/__tests__/pages/dashboard.test.tsx` with 18). 8 `react-hooks/set-state-in-effect` and 4
`exhaustive-deps` suppressions in product code. `tsconfig.json` has
`strict: true`. Leave the tests; fix the 12 hook suppressions when the
page is next touched.

---

## 3. Jev second opinion

Asked one question set with the nine largest items as state (no customer
data, no secrets).

| Question | Jev answer | Confidence | My view |
|---|---|---|---|
| Which item first? | schema_channels (0.81), test_gaps (0.16), legacy_dual_write (0.03) | 0.77 | Agree |
| Schema channel split incident likelihood, 6 months | 2.72 / 3 ≈ critical | 0.73 | Agree |
| Dual-write incident likelihood, 6 months | 1.98 / 3 ≈ high | 0.74 | Agree on risk; effort keeps it at rank 12 |
| `app` collision wrong-import in production | 1.97 / 3 ≈ high | 0.60 | Lower for production (ingestion sorts first); high for test cost |

---

## 4. Phased plan

Each phase fits beside feature work. Days are for one engineer.

### Phase 0 — this week (4 days)

| Item | Action | Days |
|--:|---|:-:|
| 1 | ADR: Alembic is the only channel. Reconcile production `alembic_version`. CI guard on `supabase/migrations/` and `sql/prod-apply/`. | 3 |
| 8 | Delete or register the 31 orphan scripts. | 0.5 |
| 15 | Remove `graph_update` type and timeout. | 0.1 |
| 13 | Point every workflow at `.nvmrc`. | 0.4 |

Exit: one schema channel documented and enforced; production version row
matches applied state.

### Phase 1 — next four weeks (9 days)

| Item | Action | Days |
|--:|---|:-:|
| 2 | Rewrite bare imports, delete legacy entrypoints, trim `PYTHONPATH`, shrink `conftest.py`. | 3 |
| 9 | Archive `infra/k8s`, root `runbooks/`, `regengine/swarm`; drop `infra-k8s-ci.yml`. | 1 |
| 3 | Ruff `F E B S*` on `services/shared`; mypy non-blocking on `shared`; `noqa` ratchet. | 2 |
| 7 | Fix the three numeric claims in `CODEBASE_MAP.md`; merge duplicate doc dirs; move root reports. | 2 |
| 6 | Split dev requirements out of the production lock. | 1 |

Exit: `pytest` from the root needs no path tricks; the image installs only
runtime packages; orientation docs pass a count check.

### Phase 2 — weeks five to eight (9 days)

| Item | Action | Days |
|--:|---|:-:|
| 4 | Measure PR CI durations; extract a reusable workflow; delete the rerun workflow after fixing its flake. | 4 |
| 5 | Delete the Kafka path and its two packages. | 2 |
| 10 | `--require-db` flag; local DB path in `CONTRIBUTING.md`; re-ratchet `shared` and `ingestion` floors. | 3 |

Exit: PR wall-clock measured and reduced; a lost `DATABASE_URL` fails CI
instead of passing it.

### Phase 3 — quarter (14 days)

| Item | Action | Days |
|--:|---|:-:|
| 12 | Re-point 12 legacy readers, fail-open dual-write with parity metric, drop `cte_events`. | 10 |
| 11 | Bare-`fetch` lint rule; convert 4 proxy routes to `proxy-factory`. | 3 |
| 14 | Split `server/main.py` into lifespan, startup checks and worker boot. | 1 |

Exit: one evidence table; one frontend API path.

Items 3 (per-service ruff expansion), 14 (other large modules) and 16 are
continuous: do them inside feature PRs that already touch the file.

---

## 5. Re-measure commands

Run these before the next audit so the numbers above can be compared.

```bash
# modules over 1,000 lines (non-test)
find services server regengine packages scripts -name '*.py' -not -path '*/tests/*' -not -name 'test_*' | xargs wc -l | awk '$1>1000' | sort -rn
```

```bash
# bare `from app.` imports in production code
grep -rlE '^\s*(from|import) app\b' --include='*.py' services | grep -v tests
```

```bash
# skip sites, noqa and type-ignore counts
grep -rlE 'pytest\.(mark\.)?skip|pytest\.skip\(' --include='*.py' tests services infra | wc -l
grep -rn 'noqa' --include='*.py' services server regengine packages | wc -l
grep -rn 'type: ignore' --include='*.py' services server regengine packages | wc -l
```

```bash
# workflow count and the four largest
ls .github/workflows | wc -l; wc -l .github/workflows/*.yml | sort -rn | head -5
```

```bash
# Kafka surface
find services -name '*.py' -not -path '*/tests/*' | xargs grep -lE 'confluent_kafka|KAFKA_BOOTSTRAP' | wc -l
```
