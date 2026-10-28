# PRD: Technical Debt Remediation, RegEngine — 2026-10-28

Audience: an AI implementation agent working inside the RegEngine repository
with no memory of the audit that produced this document. Everything the
agent needs is in this file or in the files it names.

Source analysis: `docs/audits/TECH_DEBT_AUDIT_2026-10-28.md` (the audit).
This PRD turns the audit's sixteen findings into executable work items with
acceptance criteria. Where the two disagree, this PRD wins; it incorporates
the owner's standing rules that the audit did not.

Owner and decision maker: Christopher (GitHub `PetrefiedThunder`). The agent
executes; it does not decide product direction, delete files, or change
production.

---

## 0. Read this first

### 0.1 What RegEngine is

A pre-production FSMA 204 food-traceability evidence platform. One FastAPI
monolith (`server/main.py`) deployed on Railway from the root `Dockerfile`,
one Next.js app (`frontend/`) on Vercel, PostgreSQL on Supabase with
row-level security, Redis, optional Neo4j. The production spine is:

```text
ingest -> canonicalize -> validate -> persist evidence -> export
```

Every change in this PRD must protect that spine or stay out of its way.
Read, in this order, before touching code:

1. `CLAUDE.md` (agent rules, verification commands)
2. `ARCHITECTURE.md`
3. `docs/CODEBASE_MAP.md`
4. `CANONICAL_OWNERSHIP.md`
5. `docs/audits/TECH_DEBT_AUDIT_2026-10-28.md`

### 0.2 Standing rules from the owner (override anything below that conflicts)

- **Never delete files.** Where the audit says "delete", this PRD says
  "move to an archive directory and record it". Deletion of any file
  happens only after Christopher approves it by name in a PR review or a
  message. Git history is not a substitute for this rule.
- **Keep diffs small and in one lane.** One work item per pull request.
  Do not bundle.
- **No product decisions.** If a requirement needs a choice the PRD does
  not make, stop and put the question in the PR description under
  "Decision needed", then continue with the parts that do not depend on
  it.
- **Secrets:** never ask for, print, log or commit a key. Verify a secret by
  its name or effect only (see `CLAUDE.md` → Secrets).
- **Use `python3` and `npm`.** There is no `Makefile`.
- **Tests that need PostgreSQL, Redis or Neo4j:** if the local environment
  lacks them, say so in the PR; do not fake a pass.

### 0.3 Repository mechanics the agent will hit

| Mechanic | What to know |
|---|---|
| Branch prefix | The `Engine Review Pass` CI gate derives the author engine from the branch prefix. Use `<engine>/<topic>`, where engine is one of `claude`, `codex`, `gemini`, `grok`, `muse`, `kimi`, `pi`, `deepseek`, `hermes`, `antigravity`. Example: `codex/wi-02-app-namespace`. `CONTRIBUTING.md` lists `fix/`, `feat/`, `chore/`, `docs/`; the gate rejects those, so use the engine form. |
| Cross-engine review | A PR merges only after a *different* engine posts a comment containing, alone on one line, `REVIEW: PASS <engine> <full 40-char head SHA>`. The author engine's own PASS is ignored. After every push the SHA changes and the marker must be re-posted. Do not post a marker under an engine name that is not yours. |
| PR template | `.github/pull_request_template.md`. Fill every section. |
| Draft PRs | CodeRabbit skips drafts. Open PRs as ready for review unless the work is incomplete. |
| `*AUDIT*.md` is gitignored | `.gitignore` line 153. `docs/audits/*.md` is re-allowed. Put audit-type reports there. |
| Paths in this PRD | A backticked path that does not exist in the tree is a file this PRD tells you to create or a destination to move to. Appendix A lists every path that must already exist. |
| Docs link gate | `scripts/check_docs_links.py` fails CI when a backticked path in a scoped document does not exist. Scope is `runbooks/`, `docs/CODEBASE_MAP.md`, `docs/compliance/`. Run it on any document you edit anyway. A path named deliberately because it was retired goes in `.docs-link-allowlist` with a reason. |
| Workflow inventory gate | `scripts/check_workflow_inventory.py` fails CI when the set of workflows drifts from its checked-in inventory or when a required branch-protection context is emitted by nothing. Adding, renaming or archiving a workflow means updating that inventory in the same PR. |
| Legacy dead-code gate | `scripts/check_legacy_dead_code.py` blocks re-introduction of code paths already removed. Extend it when you retire something, so it cannot come back. |
| Visual report | `visual-report (non-required)` fails on every PR today (Playwright 1.64 rejects extensionless screenshot names). Fix is open as PR #3666. Ignore this check; do not try to fix it inside another work item. |
| Test discovery | `pyproject.toml` `[tool.pytest.ini_options].testpaths` lists every test root. A test directory not listed there never runs. `test-suite-check.yml` guards import failures. |
| Pre-commit | `.pre-commit-config.yaml` exists; install it outside the hash-pinned requirements. |

### 0.4 Verification commands (from `CLAUDE.md`)

```bash
python3 -m pytest tests/swarm -q
python3 -m pytest services/ingestion/tests -q --no-cov
python3 -m pytest services/admin/tests -q --no-cov
python3 -m pytest services/shared/tests -q --no-cov
python3 -m pytest tests/scripts -q --no-cov
```

```bash
cd frontend && npm run lint
cd frontend && npm run test:run
cd frontend && npm run build
```

Backend lint as CI runs it:

```bash
ruff check . --select E9,F63,F7,F82 --line-length 120
```

---

## 1. Goals and non-goals

### Goals

1. One schema-change channel, with production's recorded migration version
   matching what is applied (WI-01).
2. A test and import layout with no hidden path tricks (WI-02, WI-10).
3. Static gates that catch the bug classes recent security fixes were for
   (WI-03).
4. A production image that installs only what production imports (WI-05,
   WI-06).
5. Orientation documents whose numbers are checked by CI, not by readers
   (WI-07).
6. Lower PR wall-clock time with no loss of coverage (WI-04).
7. A single evidence table and a single frontend API path (WI-12, WI-11).

### Non-goals

- New product features or router graduations.
- Changing tenant isolation, RLS policy, auth, or the audit hash chain.
- Any change to production configuration, Railway variables, Vercel
  settings or the Supabase project. The agent prepares; Christopher
  applies.
- Rewriting modules only because they are long (WI-14 is opportunistic).
- Fixing `visual-report (non-required)` (owned by PR #3666).

---

## 2. Scoring and sequencing

Priority = (Impact + Risk) × (6 − Effort), from the audit. Days are for one
agent with review turnaround excluded.

| WI | Title | Priority | Phase | Days | Depends on |
|--:|---|--:|:-:|:-:|---|
| 01 | Single schema channel and version-row reconciliation kit | 27 | 0 | 3 | — |
| 08 | Register or archive orphan scripts | 20 | 0 | 0.5 | — |
| 15 | Retire the dead `graph_update` task type | 10 | 0 | 0.1 | — |
| 13 | One Node version across CI | 12 | 0 | 0.4 | — |
| 02 | Remove the `app` package collision | 24 | 1 | 3 | 09 |
| 09 | Archive the retired six-service topology | 20 | 1 | 1 | — |
| 03 | Widen ruff; stage mypy | 24 | 1 | 2 | 02 |
| 07 | Make orientation docs count-checked | 20 | 1 | 2 | 02, 09 |
| 06 | Split dev and experimental requirements from the production lock | 20 | 1 | 1 | — |
| 04 | CI consolidation | 21 | 2 | 4 | 09, 13 |
| 05 | Retire the Kafka backbone | 20 | 2 | 2 | 06 |
| 10 | DB-dependent tests fail loudly when the DB is missing | 18 | 2 | 3 | 02 |
| 12 | Retire the `cte_events` dual-write | 14 | 3 | 10 | 01, 10 |
| 11 | One frontend API path | 15 | 3 | 3 | — |
| 14 | Split `server/main.py` | 10 | 3 | 1 | 02 |
| 16 | Frontend hook-rule suppressions | 8 | ongoing | — | — |

Execute in phase order. Inside a phase, the order shown.

---

## 3. Work items

Each item has: Problem (with the evidence the audit measured), Scope,
Requirements (numbered, testable), Acceptance criteria, Verification,
Out of scope, Rollback. "Baseline" numbers come from the audit and must be
re-measured with the commands in Appendix A before the work starts, so the
PR can show before and after.

### WI-01 — Single schema channel and version-row reconciliation kit

**Problem.** Schema changes reach production three ways: the Alembic chain
(`alembic/versions/`, 105 revisions, head v137), `supabase/migrations/`
(45 SQL files, newest 2026-10-26, mentioned by no document), and
hand-rendered scripts in `sql/prod-apply/`. `DEVOPS_NOTES.md` (2026-10-20)
records that production's `public.alembic_version` still reads v079 while
v128 policies are applied, so `alembic upgrade head` there would replay
v080 to v137. `docs/MIGRATION_CONSOLIDATION.md` describes a state from
March (10 Alembic revisions, a `migrations/` directory that no longer
exists). The Docker `CMD` runs `scripts/run-migrations.sh` before the app
starts.

**Scope.** Documentation, a read-only SQL kit, one CI guard with tests. No
database is touched by the agent.

**Requirements.**

1. Write `docs/decisions/2026-11-01-schema-change-channel.md` (use the
   date the PR opens; the directory's existing files are named
   `YYYY-MM-DD-topic.md`, follow their format). It must
   state: Alembic is the only authoritative channel; `supabase/migrations/`
   and `sql/prod-apply/` are *rendered outputs* of Alembic revisions, never
   hand-edited; every rendered file names the Alembic revision it renders in
   a header comment; and the rendering command used.
2. Inventory `supabase/migrations/` and `sql/prod-apply/`: for every file,
   record in the ADR appendix which Alembic revision it corresponds to, or
   "no Alembic counterpart". Files with no counterpart are a "Decision
   needed" list for Christopher; do not write migrations for them.
3. Produce `sql/prod-apply/PRECHECK_alembic_version_reconcile.sql`
   containing only `SELECT` statements that report: the current
   `alembic_version` row; for each Alembic revision from v080 to head,
   whether its observable effect is present (table, column, policy or
   function existence, derived from each revision's `upgrade()`); and a
   final computed "highest revision whose effects are all present".
4. Produce `docs/runbooks/ALEMBIC_VERSION_RECONCILE.md`: steps for
   Christopher to run the precheck, read the result, set the version row
   with a single `UPDATE public.alembic_version SET version_num = '<rev>'`
   inside a transaction, and re-run the precheck. State explicitly that
   the agent did not run it.
5. Add `scripts/check_schema_channels.py` with tests in
   `tests/scripts/test_check_schema_channels.py`: fails when a PR diff adds
   or changes a file under `supabase/migrations/` or `sql/prod-apply/` that
   lacks the `-- alembic-revision: <id>` header, or whose named revision
   does not exist under `alembic/versions/`. Wire it into
   `.github/workflows/pr-guards.yml` next to the other guards.
6. Replace `docs/MIGRATION_CONSOLIDATION.md` body with a two-line pointer to
   the ADR (do not delete the file; other docs may link it).

**Acceptance criteria.**

- `python3 -m pytest tests/scripts/test_check_schema_channels.py -q` passes,
  including a case for a file without the header and a file naming a
  non-existent revision.
- `python3 scripts/check_docs_links.py docs/decisions/2026-11-01-schema-change-channel.md docs/runbooks/ALEMBIC_VERSION_RECONCILE.md` passes.
- The PRECHECK file contains no statement other than `SELECT`, `WITH`, and
  comments (add a test asserting this).
- The "Decision needed" list is in the PR description.

**Out of scope.** Running anything against a database. Writing new Alembic
revisions. Changing `scripts/run-migrations.sh`.

**Rollback.** Revert the PR. Nothing outside the repo changes.

### WI-02 — Remove the `app` package collision

**Problem.** `services/{admin,compliance,graph,ingestion,nlp,scheduler}/app/`
are six packages with one import name. Root `conftest.py` (347 lines)
rewrites `sys.path` per service so tests resolve `from app.X`. 20
non-test files still use bare `from app.`/`import app`; 27 use
`services.<svc>.app`. `Dockerfile` sets `PYTHONPATH` to all six service
directories, so in the container `app` always means
`services/ingestion/app`. Baseline: the exact 20 files are listed by
Appendix A command A2.

**Scope.** Imports, legacy entrypoints, `Dockerfile` `PYTHONPATH`,
`conftest.py`, `pyproject.toml`.

**Requirements.**

1. Rewrite every bare `from app.` / `import app` in non-test code to the
   `services.<svc>.app` form. Keep behaviour identical; this is a rename.
2. Legacy entrypoints `services/admin/main.py`, `services/compliance/main.py`,
   `services/graph/main.py`, `services/graph/app/main.py`,
   `services/ingestion/main.py`, `services/nlp/main.py`,
   `services/scheduler/main.py` (1,818 lines): move to
   `docs/archive/retired-topology/entrypoints/<svc>_main.py` with a header
   comment giving the original path and the date (WI-09 creates the
   directory; if WI-09 has not landed, create it here). Do not delete.
   If any of these is imported by live code or a workflow, that is a
   "Decision needed"; leave it in place and report.
3. `services/admin/app/logging_config.py` is a compatibility shim for the
   bare form. Keep its public function; remove the bare-import fallback once
   no caller uses it.
4. Reduce `Dockerfile` `PYTHONPATH` to `/app:/app/services`. Keep the
   build-time path check that follows it.
5. Reduce `conftest.py` to fixtures. Remove the `sys.path` switching once
   every test imports through `services.<svc>.app`. Tests that still use
   `from app.` must be rewritten in the same PR (count them first with
   Appendix A command A3; if above 150 files, split this into two PRs:
   production imports first, tests second, and keep the conftest shim until
   the second lands).
6. Remove the non-existent `services/test_data/tests` entry from
   `pyproject.toml` `testpaths`.
7. Extend `scripts/check_legacy_dead_code.py` so a new bare `from app.`
   import in `services/` fails CI, with a test.

**Acceptance criteria.**

- Appendix A command A2 returns zero files.
- `python3 -m pytest --collect-only -q` from the repo root reports no
  collection errors.
- The five pytest commands in §0.4 pass with the same pass counts as before
  the change (record both in the PR).
- `docker build .` succeeds locally if Docker is available; if not, say so
  and rely on the `docker-build` CI job.
- `conftest.py` no longer contains `sys.path` manipulation.

**Out of scope.** Renaming the `app` directories themselves. Changing what
any module does.

**Rollback.** Revert the PR.

### WI-03 — Widen ruff; stage mypy

**Problem.** CI runs `ruff --select E9,F63,F7,F82`; `pyproject.toml`
selects only `I`. mypy is configured but not a gate. 766 `noqa` and 223
`type: ignore` markers in non-test backend code. Two of the five commits
before the audit were security fixes found by external scanning (ReDoS,
header sanitisation, shell exec, URL host checks).

**Scope.** `pyproject.toml`, `.github/workflows/backend-ci.yml`, the code
under `services/shared/` for the first pass.

**Requirements.**

1. In `pyproject.toml` `[tool.ruff.lint]`, add a per-directory override for
   `services/shared/**` selecting `F`, `E`, `B`, `S102`, `S105`, `S106`,
   `S107`, `S108`, `S113`, `S301`, `S324`, `S602`, `S603`, `S604`, `S605`,
   `S606`, `S607`. Fix every finding or add `# noqa: <code> -- <reason>`
   with a reason. A `noqa` without a reason is not acceptable in this PR.
2. Make `backend-ci.yml`'s `lint-shared` job run `ruff check services/shared`
   with the project config (drop the explicit narrow `--select` for that
   job only).
3. Add a non-blocking `mypy` job for `services/shared` using the existing
   `[tool.mypy]` config, uploading its report as an artifact. Exclude
   `frontend/public/sdk` from mypy so the `verify_chain.py` duplicate
   (noted in `BREAK-REPORT.md`) does not stop it.
4. Add `scripts/check_noqa_ratchet.py` with tests: counts `noqa` markers
   lacking a `--` reason under `services/` and fails if the count exceeds
   the number committed in `scripts/noqa_baseline.txt`. Commit the baseline
   measured after step 1. Wire into `pr-guards.yml`.
5. Document in `CONTRIBUTING.md` → Code Guidelines: the rule set, the
   `noqa` reason convention, and that one more service directory joins the
   override each time a PR touches it substantially.

**Acceptance criteria.**

- `ruff check services/shared` exits 0 with the new config.
- `tests/scripts/test_check_noqa_ratchet.py` passes.
- The mypy job runs in CI and is marked non-blocking in `ci-status`.
- Count of `noqa` without reason under `services/shared` is zero.

**Out of scope.** Enabling the rules repo-wide. Making mypy blocking.

**Rollback.** Revert the PR; no runtime change.

### WI-04 — CI consolidation

**Problem.** 33 workflows. `backend-ci.yml` 1,530 lines, `pr-guards.yml`
1,401, `pr-gate.yml` 1,123, `security.yml` 875.
`pr-gate-frontend-rerun.yml` exists to re-run flaky frontend gates. The
ingestion test leg has a 25-minute timeout. `infra-k8s-ci.yml` runs on PRs
for a retired topology.

**Scope.** `.github/workflows/`, the workflow inventory consumed by
`scripts/check_workflow_inventory.py`, `docs/CODEBASE_MAP.md` §7.

**Requirements.**

1. Measure first. Using the GitHub API (the `gh` CLI if available, else the
   REST API with the token the environment provides), pull the last 30
   completed `pull_request` runs of `pr-gate.yml`, `pr-guards.yml`,
   `backend-ci.yml`, `frontend-ci.yml`, `security.yml`. Produce
   `docs/engineering/CI_TIMING_2026-11.md` with, per job: median duration,
   p90, failure count, and the top failure cause from logs. Commit this
   before changing any workflow.
2. Extract the shared setup steps (checkout, Python setup with
   `requirements.lock`, Node setup from `.nvmrc`, caches) into one reusable
   workflow (`workflow_call`) and call it from the five workflows above.
3. Identify the flaky spec behind `pr-gate-frontend-rerun.yml` from the
   timing document. Fix that spec's root cause (waits, selectors, test
   isolation), prove ten consecutive green local runs, then archive the
   rerun workflow to `docs/archive/retired-topology/workflows/` and update
   the inventory. Do not delete.
4. Archive `infra-k8s-ci.yml` the same way (depends on WI-09).
5. Ensure every PR-triggered workflow has a `concurrency` group keyed on the
   PR number with `cancel-in-progress: true`, except jobs the repo marks as
   must-not-cancel (the `engine-review-pass` job already says so).
6. Update `docs/CODEBASE_MAP.md` §7 with the real workflow count (WI-07
   adds the CI check for it).

**Acceptance criteria.**

- `python3 scripts/check_workflow_inventory.py` passes.
- `python3 -m pytest tests/scripts/test_check_workflow_inventory.py -q` passes.
- A follow-up timing measurement after the change, appended to the timing
  document, shows median PR wall-clock reduced. If it is not reduced, say
  so; do not remove jobs to force the number.
- No required branch-protection context is left without an emitter.

**Out of scope.** Changing what any test checks. Removing coverage gates.
Lowering thresholds.

**Rollback.** Revert the PR; restore inventory.

### WI-05 — Retire the Kafka backbone

**Problem.** 13 non-test modules import `confluent_kafka` or read
`KAFKA_BOOTSTRAP_SERVERS`; the main ones total 3,505 lines
(`services/shared/kafka_auth.py` 786, `services/nlp/app/consumer/__init__.py`
1,118, `services/shared/kafka_compat.py`, `services/shared/kafka_consumer_base.py`,
`services/shared/observability/dlq_producer.py`,
`services/admin/app/review_consumer.py`, `services/ingestion/app/kafka_utils.py`).
`services/shared/event_backbone.py` defaults `EVENT_BACKBONE` to `pg`;
`ASYNC_PROCESSES.md` says the backbone is the Postgres task queue.
`confluent-kafka[schema-registry,avro]` and `fastavro` ship in the
production image.

**Scope.** The modules above, `requirements.in`/`requirements.lock`,
`server/main.py` gating, docs.

**Requirements.**

1. Before removing anything, produce a call graph: for each Kafka module,
   list every importer outside the Kafka set. Any importer on the `pg` path
   (for example tracing helpers in
   `services/shared/observability/kafka_propagation.py` used by
   `server/main.py`) must keep its function; move the needed function to a
   non-Kafka module first and update the importer.
2. Move the Kafka-only modules to `docs/archive/retired-topology/kafka/`
   preserving relative paths. Do not delete. Remove their imports and the
   `EVENT_BACKBONE=kafka` branch in `services/nlp/main.py` (which WI-02 has
   already archived) and in `services/shared/event_backbone.py`.
3. Remove `confluent-kafka` and `fastavro` from `requirements.in`;
   recompile `requirements.lock` with the repo's pip-tools command
   (`pip-compile --generate-hashes`; check `ARCHITECTURE.md` → Dependency
   Management and `.github/workflows/dependabot-lock-sync.yml` for the
   exact invocation). Confirm no other package depended on them.
4. Remove Kafka-related environment variables from `.env.example` and any
   `validate_env.py` checks; list them in the PR.
5. Extend `scripts/check_legacy_dead_code.py` so `import confluent_kafka`
   in `services/` fails CI.
6. Update `ARCHITECTURE.md` → Infrastructure and `ASYNC_PROCESSES.md` to
   drop the "legacy Kafka paths still exist" language.

**Acceptance criteria.**

- Appendix A command A5 returns zero.
- `pip install --require-hashes -r requirements.lock` succeeds in a clean
  virtualenv.
- All five §0.4 pytest commands pass; tests that only exercised Kafka move
  with the modules to the archive directory and are listed in the PR.
- `python3 scripts/check_docs_links.py ARCHITECTURE.md ASYNC_PROCESSES.md` passes.

**Out of scope.** Any change to `services/shared/task_queue.py` or
`server/workers/task_processor.py`.

**Rollback.** Revert the PR, which restores the lock.

### WI-06 — Split dev and experimental requirements from the production lock

**Problem.** `requirements.in` includes pytest, pytest-asyncio, pytest-cov,
pytest-mock, pytest-xdist, hypothesis, aiosqlite and testcontainers;
`docker` is a transitive. The `Dockerfile` compensates with
`find /app -name "test_*.py" -delete`. The image also ships langchain,
langchain-community, langgraph, langsmith, openai, llama-cloud,
pytesseract, pdf2image, pyzbar, whose routers (`nlp`, `agent_org`,
`label_vision`, `qr_decoder`) are in `EXPERIMENTAL_ROUTERS`
(`server/router_policy.py`) and never mount in production.

**Scope.** Requirements files, `Dockerfile`, `backend-ci.yml` install
steps, `dependabot.yml`, `supply-chain.yml`.

**Requirements.**

1. Create `requirements-dev.in` holding the testing block from
   `requirements.in`; compile `requirements-dev.lock` with hashes,
   constrained by `requirements.lock` (`-c requirements.lock`) so versions
   never diverge.
2. Create `requirements-experimental.in` for packages imported only by
   modules behind `EXPERIMENTAL_ROUTERS`. Determine the set by import
   tracing, not by guessing; list the trace in the PR. Packages imported by
   any always-mounted or production-allowlisted router stay in
   `requirements.in`.
3. `Dockerfile` installs `requirements.lock` only. Remove the
   `find ... -delete` line only if no `test_*.py` file is copied by the
   remaining `COPY` lines (check `.dockerignore`); otherwise leave it and
   say why.
4. CI jobs install `requirements.lock` plus `requirements-dev.lock`, and
   `requirements-experimental.lock` only in jobs that run experimental
   tests (identify them by their test paths).
5. Add the new files to `dependabot.yml` and to the `supply-chain.yml`
   `paths` trigger.
6. Add a startup guard test: with only `requirements.lock` installed in a
   clean virtualenv, `python3 -c "import server.main"` succeeds with
   `ENABLE_EXPERIMENTAL_ROUTERS` unset. Automate this as a CI job
   (`image-import-check`) that builds the venv from the production lock
   alone.

**Acceptance criteria.**

- `image-import-check` passes in CI.
- Count of packages in `requirements.lock` is lower than before; report
  before and after.
- `docker-build` CI job passes.
- Dependabot opens no "lock out of sync" PR for the new files (verify the
  `dependabot-lock-sync.yml` logic covers them).

**Out of scope.** Removing any experimental router or its code.

**Rollback.** Revert the PR.

### WI-07 — Make orientation docs count-checked

**Problem.** `docs/CODEBASE_MAP.md` claims every line was checked against
the tree, and says 23 workflows (there are 33), 81 `include_router` calls
in `server/main.py` (there are 2; registration moved to
`server/router_policy.py`), and lists 14 experimental routers (the
frozenset has 15; `agent_org` is missing). `ARCHITECTURE.md`'s
large-module table is dated 2026-07-31. Four duplicate doc directory
pairs: `docs/archive` and `docs/_archive`; `docs/schema` and
`docs/schemas`; `nfr/` and `docs/nfr`; `runbooks/` and `docs/runbooks`.
20 Markdown files at the repo root including one-off reports
`BREAK-REPORT.md`, `FIX-REPORT.md`.

**Scope.** Documentation, `scripts/check_docs_links.py` or a sibling
script, `.docs-link-allowlist`.

**Requirements.**

1. Add `scripts/check_docs_counts.py` with tests: a small table of
   (document, regex capturing a number, shell-free Python function that
   computes the true value). Seed it with: workflow count in
   `docs/CODEBASE_MAP.md` §2 and §7; `include_router` count in §4; the
   experimental router list in §4 versus `server/router_policy.py`
   `EXPERIMENTAL_ROUTERS`; the number of files in the `ARCHITECTURE.md`
   large-module table versus the live count. Fails when they differ. Wire
   into `pr-guards.yml`.
2. Correct the documents so the check passes. For the experimental router
   list, render it from the frozenset rather than hand-typing.
3. Merge directory pairs by moving files (never deleting): `docs/_archive/*`
   → `docs/archive/`; `docs/schemas/*` → `docs/schema/`; `nfr/*` →
   `docs/nfr/`; root `runbooks/*` → `docs/runbooks/legacy/` (they carry a
   `LEGACY:` banner already). Update every link; run the link checker on
   every document that referenced a moved file. Update
   `scripts/check_docs_links.py` `DEFAULT_SCOPE` so it still covers the
   moved runbooks.
4. Move `BREAK-REPORT.md` → `docs/engineering/cli-break-report-2026-10.md`
   and `FIX-REPORT.md` → `docs/engineering/about-copy-fix-report-2026-10.md`
   (confirm dates from their content). Leave `GEMINI.md` in place; it is an
   agent instruction file and its removal is a decision for Christopher.
5. Re-stamp `ARCHITECTURE.md` "Last verified" after re-checking each
   section against the tree; record what changed in the PR.

**Acceptance criteria.**

- `python3 scripts/check_docs_counts.py` and its tests pass.
- `python3 scripts/check_docs_links.py` with default scope passes.
- `ls docs/_archive docs/schemas nfr runbooks` each report "No such file"
  or an empty directory with only a `README.md` pointer.

**Out of scope.** Rewriting document prose beyond the counts and moved
paths.

**Rollback.** Revert the PR.

### WI-08 — Register or archive orphan scripts

**Problem.** 31 of 87 top-level files in `scripts/` are referenced by no
workflow, `Dockerfile`, `railway.toml`, runbook, other script, README,
CONTRIBUTING or DEVOPS_NOTES. Largest:
`scripts/verify_canonical_parity_live.py` (1,702 lines),
`scripts/backfill_canonical_from_legacy.py` (1,423),
`scripts/seed_demo_data.py` (680), `scripts/audit-issues.py` (665),
`scripts/e2e_brutal_scenario.py` (654), `scripts/jev_header_preview.py` (602).

**Scope.** `scripts/`, a new `scripts/README.md`.

**Requirements.**

1. Re-run Appendix A command A8 to get the current orphan list.
2. For each orphan, classify: (a) used by a documented manual procedure
   (register it), (b) tied to WI-12 (`verify_canonical_parity_live.py`,
   `backfill_canonical_from_legacy.py`: register under "retire with
   WI-12"), (c) no known use (archive).
3. Create `scripts/README.md`: one line per script in `scripts/` and its
   subdirectories: purpose, the workflow or runbook that invokes it, or
   "manual: <when>". Scripts in class (c) move to `scripts/_archive/` with
   the same name and a line in the README saying so and when. Do not
   delete.
4. Any orphan with tests under `tests/scripts/` stays registered (the test
   is a use).
5. Add a check to `scripts/check_legacy_dead_code.py` or a new
   `scripts/check_scripts_registered.py` (with tests): every file in
   `scripts/` top level must have a README line. Wire into `pr-guards.yml`.

**Acceptance criteria.**

- The registration check passes.
- `tests/scripts` suite passes.
- The PR lists every moved script with its classification reason.

**Out of scope.** Editing any script's behaviour.

**Rollback.** Revert the PR.

### WI-09 — Archive the retired six-service topology

**Problem.** `infra/k8s/` (`base/`, `overlays/`) plus `infra-k8s-ci.yml`;
five root `runbooks/` with `LEGACY:` banners; `regengine/swarm/` (about
2,600 lines) behind `REGENGINE_ENABLE_LEGACY_SWARM`; `infra/gateway/`
"reference-only" nginx config with its own tests in `testpaths`; the seven
legacy entrypoints (WI-02).

**Scope.** Those paths, `pyproject.toml` `testpaths`, workflow inventory,
`docs/CODEBASE_MAP.md`.

**Requirements.**

1. Create `docs/archive/retired-topology/README.md` stating what the
   six-service topology was, when it was retired, and that nothing under
   this directory is loaded by any build, test or deploy.
2. Move (do not delete) `infra/k8s/` → `docs/archive/retired-topology/k8s/`;
   `infra/gateway/` → `docs/archive/retired-topology/gateway/` **only if**
   `ARCHITECTURE.md`'s claim that it is reference-only still holds (check
   `Dockerfile`, `railway.toml`, workflows for any use); `regengine/swarm/`
   → `docs/archive/retired-topology/swarm/`.
3. Remove `infra/gateway/tests` from `testpaths`; move those tests with the
   config. Remove `tests/swarm` from `CLAUDE.md`'s verification list and
   from `testpaths` after confirming `tests/swarm` tests only the swarm
   runtime (if any test there covers live code, keep that test and say so).
4. Archive `infra-k8s-ci.yml` to `docs/archive/retired-topology/workflows/`
   and update the workflow inventory.
5. Update `docs/CODEBASE_MAP.md` §1, §2 and `CLAUDE.md` (the
   `regengine.swarm` sentence and the verification list) to match.
6. `regengine/` is also the published SDK. Confirm `regengine/setup.py` (or
   `pyproject`) does not package `regengine.swarm`; if it does, exclude it
   and say so.

**Acceptance criteria.**

- `python3 -m pytest --collect-only -q` has no errors.
- `python3 scripts/check_workflow_inventory.py` passes.
- `python3 scripts/check_docs_links.py` default scope passes.
- `python3 -m pytest tests/sdk -q` passes.

**Out of scope.** Anything under `services/`.

**Rollback.** Revert the PR.

### WI-10 — DB-dependent tests fail loudly when the DB is missing

**Problem.** 170 skip sites; the most common reason is "migrated Postgres
with fsma schema not available". A bare `pytest` locally passes while
exercising none of the RLS, migration or persistence paths. CI does run
`live-db-suite` (postgres:17) and `seeded-migration-rehearsal`, so
production is covered; the risk is a lost `DATABASE_URL` turning the suite
green. Per-service coverage floors: compliance 80, admin 70, scheduler 65,
graph 60, ingestion 48, shared 35.

**Scope.** `conftest.py` fixtures, `backend-ci.yml`, `CONTRIBUTING.md`,
`docker-compose.dev.yml` docs.

**Requirements.**

1. Add a pytest option `--require-db` (in root `conftest.py`): when set,
   every skip whose reason matches the DB-unavailable patterns (collect the
   exact strings with Appendix A command A10) becomes a failure. Implement
   by routing those skips through one helper `skip_or_fail_without_db()`
   and replacing the 170 call sites' inline conditions with the helper
   where the reason is DB availability.
2. Pass `--require-db` in `live-db-suite` and `seeded-migration-rehearsal`.
3. The helper's skip message must print the exact local setup commands:
   `docker compose -f docker-compose.dev.yml up -d`, the `alembic upgrade
   head` invocation with the dev `DATABASE_URL`, and the environment
   variables needed. Put the same text in `CONTRIBUTING.md` → Development
   Setup under a new "Running database tests locally" heading.
4. Re-measure `shared` and `ingestion` coverage on CI after WI-02 and WI-05
   land; if measured value minus 5 exceeds the floor, raise the floor to
   that value in `backend-ci.yml` with a dated comment, following the
   existing comment style there.

**Acceptance criteria.**

- With `DATABASE_URL` unset: `python3 -m pytest services/shared/tests -q --no-cov --require-db` fails with the helper's message, and without the flag skips as before.
- `live-db-suite` passes in CI with the flag.
- Skip-site count (Appendix A command A10) drops; report before and after.

**Out of scope.** Writing new tests. Changing what the DB tests assert.

**Rollback.** Revert the PR.

### WI-11 — One frontend API path

**Problem.** `frontend/src/lib/api-client.ts` (1,163 lines) is imported by
15 files under `app/`, `components/`, `hooks/`; 33 non-test files in those
directories call `fetch(` directly. 30 route handlers under
`frontend/src/app/api/`; 22 use `frontend/src/lib/proxy-factory.ts`, 8 are
hand-rolled: `client-errors`, `inflow-lab/[...path]`, `openapi.json`,
`session`, `health`, `contact`, `tools/check-access`, `tools/verify`.

**Scope.** `frontend/src/app`, `frontend/src/components`,
`frontend/src/hooks`, `frontend/src/lib`, `frontend/eslint.config.mjs`.

**Requirements.**

1. Add an ESLint `no-restricted-syntax` rule forbidding bare `fetch(` under
   `src/app/**`, `src/components/**`, `src/hooks/**`, excluding
   `src/app/api/**` (route handlers legitimately fetch the backend) and
   test files. Message must name `api-client.ts` as the replacement.
2. Convert the 33 call sites to `api-client.ts` functions or typed hooks.
   Where no function exists, add one next to its neighbours in
   `api-client.ts`, typed with the shapes in `frontend/src/types/api.ts`.
   Preserve request headers, credentials mode, tenant header handling and
   error mapping exactly; diff the network request in a test for at least
   five converted sites using the existing MSW or mock pattern in
   `frontend/src/test/`.
3. Convert `tools/check-access`, `tools/verify` and `inflow-lab/[...path]`
   to `proxy-factory.ts` if they proxy the backend with no local logic;
   leave `health`, `session`, `contact`, `client-errors`, `openapi.json` as
   they are and say why in a comment at the top of each.
4. Do not change any page's rendered output. Run the existing page tests.

**Acceptance criteria.**

- `cd frontend && npm run lint` passes with the new rule enabled.
- `cd frontend && npm run test:run` passes with coverage not below the
  thresholds in `frontend/vitest.config.mts`.
- `cd frontend && npm run build` passes.
- Appendix A command A11 returns zero outside `src/app/api`.

**Out of scope.** Splitting the large page components. Changing API
shapes.

**Rollback.** Revert the PR.

### WI-12 — Retire the `cte_events` dual-write

**Problem.** `services/shared/canonical_persistence/writer.py` calls
`legacy_dual_write.dual_write_legacy` on single and batch writes; since
#1277 a failure raises and rolls back the canonical write.
`services/shared/canonical_persistence/legacy_dual_write.py` (532 lines) is
headed "TEMPORARY". `CANONICAL_OWNERSHIP.md` calls `cte_events` a legacy
derived copy to be removed. 12 non-legacy modules still read `cte_events`,
including `services/admin/app/supplier_onboarding_routes.py`,
`services/admin/app/supplier_facilities_routes.py`,
`services/admin/app/data_export_routes.py`,
`services/admin/app/supplier_funnel_routes.py`,
`services/shared/workflows/export_output.py`,
`services/shared/supplier_data_quality.py`. Jev scored six-month incident
likelihood high (1.98 of 3).

**Scope.** The 12 readers, the writer, one feature flag, one Alembic
revision at the end. Three PRs minimum.

**Requirements.**

PR A (readers):

1. For each of the 12 readers (Appendix A command A12 lists them), re-point
   the query to `fsma.traceability_events`, mapping KDE columns from the
   `kdes` JSONB as `CANONICAL_OWNERSHIP.md` documents. One commit per
   reader.
2. For each, add a parity test that seeds the same event through the
   canonical writer and asserts the route's response is byte-identical
   before and after the change (use the live-db fixtures).
3. Readers that are export surfaces (`export_output.py`,
   `data_export_routes.py`) additionally run the existing FDA export
   fixtures under `tests/` and `services/ingestion/tests` unchanged.

PR B (flag):

4. Add `CANONICAL_LEGACY_DUAL_WRITE` setting (default `on`) in
   `services/shared/base_config.py`; when `off`, `writer.py` skips the
   legacy write and increments a Prometheus counter
   `legacy_dual_write_skipped_total`. When `on`, behaviour is unchanged.
5. Document in `DEVOPS_NOTES.md` the plan: set `off` on staging for two
   weeks, run `scripts/verify_canonical_parity_live.py` daily, then
   production. Christopher flips the flag; the agent does not.

PR C (removal, only after Christopher confirms the two-week window passed):

6. Remove the dual-write call and move `legacy_dual_write.py`,
   `scripts/verify_canonical_parity_live.py` and
   `scripts/backfill_canonical_from_legacy.py` to
   `docs/archive/retired-topology/legacy-cte/`. Do not delete.
7. Add an Alembic revision that renames `fsma.cte_events` and
   `fsma.cte_kdes` to `fsma.cte_events_retired_<date>` (rename, not drop;
   dropping is a later decision) and removes their RLS policies per
   `docs/engineering/SCHEMA_CHANGE_POLICY.md`. Render the SQL per WI-01's
   ADR.
8. Update `CANONICAL_OWNERSHIP.md` → Canonical Event → Persistence.

**Acceptance criteria.**

- PR A: all parity tests pass in `live-db-suite`; no route's response
  changes.
- PR B: with the flag `off` in a test, the writer commits without touching
  `cte_events` (assert row count unchanged) and the counter increments.
- PR C: `grep -rn cte_events services server` matches only the migration
  and the archive; `alembic-revision-check` job passes.

**Out of scope.** Dropping tables. Neo4j graph sync (`publish_graph_sync`
in the same module): keep it, move it to a non-legacy module in PR C.

**Rollback.** PR A and B revert cleanly. PR C's migration has a
`downgrade()` that renames back.

### WI-13 — One Node version across CI

**Problem.** `.nvmrc` says 22. `copy-gate.yml` pins Node 20; one
`frontend-ci.yml` job pins 24; `package.json` `engines` says 22 or 24.
`dependabot.yml` ignores jsdom 30 and jest-dom 7 with the note "CI runs
Node 20".

**Scope.** Workflows, `dependabot.yml`.

**Requirements.**

1. Replace every `node-version: '<n>'` in `.github/workflows/` with
   `node-version-file: .nvmrc`. List each change in the PR.
2. If any job needed 24 for a reason (read its comments), keep 24 there,
   and change `.nvmrc` to 24 only if `package.json` `engines` allows and
   Vercel's Node setting (ask Christopher; do not change Vercel) matches.
   Otherwise leave `.nvmrc` at 22.
3. Remove the jsdom and jest-dom major ignores from `dependabot.yml`,
   leaving a comment that the Node blocker is gone and CI will judge the
   upgrade.

**Acceptance criteria.**

- `grep -rn "node-version:" .github/workflows` returns nothing.
- `frontend-ci.yml` passes on the PR.

**Out of scope.** Performing the jsdom or jest-dom upgrade.

**Rollback.** Revert.

### WI-14 — Split `server/main.py`

**Problem.** `server/main.py` is 1,256 lines holding the lifespan, startup
checks, worker boot and router policy wiring. 25 non-test modules exceed
1,000 lines (20 under `services/` and `server/`); the others are split
only when a feature touches them.

**Scope.** `server/`.

**Requirements.**

1. Extract into `server/startup_checks.py` (environment, RLS role posture,
   secret presence checks), `server/workers_boot.py` (task processor and
   embedded scheduler start/stop), and keep `server/main.py` as app
   construction, middleware order and lifespan that calls the two. Keep
   every log line and its order; the deploy log is parsed by humans
   (`jev_configured`, `document_extract_configured` lines in `CLAUDE.md`).
2. No behaviour change. Add a test that imports `server.main` with
   production-like env (`ENVIRONMENT=production`, no experimental routers)
   and asserts the same set of mounted route paths as before the split
   (snapshot the list in the test).

**Acceptance criteria.**

- `server/main.py` under 500 lines.
- The route-set snapshot test passes.
- `tests/security` suite passes.

**Out of scope.** The other 24 large modules.

**Rollback.** Revert.

### WI-15 — Retire the dead `graph_update` task type

**Problem.** `graph_update` is declared in `services/shared/task_types.py`
and given a 120-second timeout in `server/workers/task_processor.py`, but
nothing enqueues it and `TASK_HANDLERS` has no handler.
`ASYNC_PROCESSES.md` describes unclaimed rows; none are produced today.

**Requirements.**

1. Remove the type and the timeout entry. If a CHECK constraint or enum in
   the database lists task types (search `alembic/versions` for
   `graph_update`), leave the database alone and say so; only code changes.
2. Update `ASYNC_PROCESSES.md`'s table.

**Acceptance criteria.** `grep -rn graph_update services server` returns
nothing outside migrations; `tests/shared` passes.

### WI-16 — Frontend hook-rule suppressions (ongoing)

**Problem.** 14 `eslint-disable` comments in product code: 8
`react-hooks/set-state-in-effect`, 4 `react-hooks/exhaustive-deps`, 2
`no-console`. All 192 `any` usages are in test files and are not in
scope.

**Requirements.** No standalone PR. When a PR touches one of these files
(`frontend/src/components/lead-gate/LeadGate.tsx`,
`frontend/src/lib/tenant-context.tsx`, `frontend/src/components/ui/tutorial.tsx`,
`frontend/src/components/layout/theme-toggle.tsx`,
`frontend/src/components/accessibility/AccessibilityWidget.tsx`,
`frontend/src/app/status/StatusBoard.tsx`,
`frontend/src/app/settings/profile/page.tsx`,
`frontend/src/app/tools/knowledge-graph/components/KnowledgeGraph.tsx`,
`frontend/src/app/tools/label-scanner/page.tsx`,
`frontend/src/app/dashboard/settings/users/page.tsx`), remove the
suppression by restructuring the effect, and keep the page's tests green.

---

## 4. Definition of done, per PR

A work-item PR is done when all of the following hold:

1. Branch named `<engine>/wi-<nn>-<slug>`.
2. PR body follows `.github/pull_request_template.md`, with three extra
   sections: **Baseline vs after** (the Appendix A numbers for this item),
   **Decision needed** (empty or a list), **Files moved to archive**
   (empty or a list with original paths).
3. Every acceptance criterion above is quoted in the PR body with the
   command run and its last line of output.
4. Required CI is green on the head commit. `visual-report (non-required)`
   is ignored. `Engine Review Pass` needs a non-author engine's marker; the
   agent asks Christopher to arrange that and does not post one itself.
5. `docs/audits/TECH_DEBT_AUDIT_2026-10-28.md` §1 table gets a new
   "Status" column entry for the item (`PR #nnnn open` / `merged
   <date>`), in the same PR.
6. No file deleted. `git diff --diff-filter=D --name-only main...HEAD` is
   empty, or every listed path is a rename (`--diff-filter=R` shows it)
   or was approved by name.

---

## 5. Decisions needed from Christopher (collected)

The agent proceeds on everything else and records these in each PR:

| Item | Decision |
|---|---|
| WI-01 | Which `supabase/migrations/` and `sql/prod-apply/` files without an Alembic counterpart should become Alembic revisions, and who runs the version-row reconcile. |
| WI-02 | Whether any legacy entrypoint is still used for local debugging and should stay as a thin shim. |
| WI-05 | Confirmation that no customer or partner integration is on the Kafka path (the code default is `pg`). |
| WI-06 | Whether any experimental router will graduate in the next quarter (its packages would then stay in the production lock). |
| WI-07 | Whether `GEMINI.md` stays at the root. |
| WI-08 | Approval, by name, for any script the agent proposes to archive. |
| WI-12 | The go-ahead for PR C after the two-week flag window, and whether to rename or drop the legacy tables. |
| WI-13 | Vercel's Node version, so `.nvmrc` can match it. |

---

## Appendix A — Baseline measurement commands

Run from the repo root before and after each item; paste both into the PR.

```bash
# A2: non-test files with bare `app` imports (WI-02 target: 0)
grep -rlE '^\s*(from|import) app\b' --include='*.py' services | grep -v tests
```

```bash
# A3: test files with bare `app` imports (WI-02 sizing)
grep -rlE '^\s*(from|import) app\b' --include='*.py' services tests | grep tests | wc -l
```

```bash
# A5: production modules on the Kafka path (WI-05 target: 0)
find services -name '*.py' -not -path '*/tests/*' | xargs grep -lE 'confluent_kafka|KAFKA_BOOTSTRAP' | wc -l
```

```bash
# A7: workflow count and the four largest (WI-04, WI-07)
ls .github/workflows | wc -l; wc -l .github/workflows/*.yml | sort -rn | head -5
```

```bash
# A8: top-level scripts referenced by nothing (WI-08 target: 0)
for s in scripts/*.py scripts/*.sh; do b=$(basename "$s"); grep -rq "$b" .github/workflows Dockerfile railway.toml docs/runbooks runbooks scripts/*.sh README.md CONTRIBUTING.md DEVOPS_NOTES.md scripts/README.md 2>/dev/null || echo "$s"; done
```

```bash
# A10: pytest skip sites and DB-unavailable reasons (WI-10)
grep -rlE 'pytest\.(mark\.)?skip|pytest\.skip\(' --include='*.py' tests services infra | wc -l
grep -rhoE 'skip(if)?\([^)]*reason\s*=\s*f?"[^"]{0,70}' --include='*.py' tests services infra | sed -E 's/.*reason\s*=\s*f?"//' | sort | uniq -c | sort -rn
```

```bash
# A11: bare fetch( in frontend product code (WI-11 target: 0 outside src/app/api)
grep -rlE '\bfetch\(' --include='*.ts' --include='*.tsx' frontend/src/app frontend/src/components frontend/src/hooks | grep -v __tests__ | grep -v 'src/app/api'
```

```bash
# A12: non-legacy readers of cte_events (WI-12 target: 0)
grep -rln 'cte_events' --include='*.py' services server | grep -v tests | grep -v 'cte_persistence\|legacy_dual_write'
```

```bash
# A14: modules over 1,000 lines (WI-14)
find services server regengine packages scripts -name '*.py' -not -path '*/tests/*' -not -name 'test_*' | xargs wc -l | awk '$1>1000 && $2!="total"' | sort -rn
```

```bash
# A3b: lint suppression counts (WI-03)
grep -rn 'noqa' --include='*.py' services server regengine packages | wc -l
grep -rn 'type: ignore' --include='*.py' services server regengine packages | wc -l
grep -rnE 'noqa(?!:.*--)' --include='*.py' services 2>/dev/null | wc -l
```

## Appendix B — Baseline values on 2026-10-28 (commit `9f6efb3`)

| Measure | Value |
|---|--:|
| Workflows | 33 |
| Bare `app` import files (non-test) | 20 |
| Kafka-path production modules | 13 |
| Orphan top-level scripts | 31 of 87 |
| pytest skip sites | 170 |
| `noqa` markers (backend, non-test) | 766 |
| `type: ignore` markers | 223 |
| Frontend files with bare `fetch(` | 33 |
| Hand-rolled API route handlers | 8 of 30 |
| Non-legacy `cte_events` readers | 12 |
| Modules over 1,000 lines | 25 (20 under `services/` + `server/`) |
| Alembic revisions / head | 105 / v137 |
| `supabase/migrations/` files | 45 |
| Open GitHub issues | 3 |
