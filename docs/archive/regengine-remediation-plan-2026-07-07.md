> **ARCHIVED — HISTORICAL SNAPSHOT, NOT CURRENT STATE.**
>
> This report describes RegEngine as it stood on **2026-07-07**. It was moved
> from the repository root to `docs/archive/` on 2026-08-26 (#2872) because
> its findings had drifted out of date and a root-level file reads as current.
> Do not cite it as the present state of the codebase, and do not action its
> recommendations without re-verifying them against the tree first.
>
> For current state see `ARCHITECTURE.md`, `PRODUCTION_SURFACE.md`, and
> `docs/engineering/ROUTER_SURFACE.md` at the repository root.
>
> Workstream status here is frozen at the plan date; several items have since
> been completed or superseded. Check the issue tracker before starting any of them.

---

# RegEngine Remediation Plan

**Date:** 2026-07-07
**Source:** [regengine-comprehensive-review-2026-07-07.md](regengine-comprehensive-review-2026-07-07.md) (merged in #2562). This plan turns that review's P0–P2 risk register into sequenced, verifiable workstreams. Each item has scope, concrete steps, acceptance criteria, and a size estimate (S ≤ 1 day, M ≤ 1 week, L = multi-week).

**Already fixed in #2562** (no further action): frontend lockfile drift breaking `npm ci`/Fast Gate; stale `.secrets.baseline`; unpinned `sentinel.yml` action tags; missing dependabot cooldowns.

---

## Sequencing at a glance

| Order | Workstream | Priority | Size | Depends on |
| --- | --- | --- | --- | --- |
| 1 | WS-3 MFA lockout fail-closed | P0 | S | — |
| 2 | WS-4 Tenant-GUC convergence | P0 | M | — |
| 3 | WS-5 Re-enable automated deploys | P1 | S–M | — |
| 4 | WS-6 Decouple Neo4j from `/readiness` | P1 | S | — |
| 5 | WS-7 Governance quick wins (CODEOWNERS, `.python-version`, stale automation config) | P1 | S | — |
| 6 | WS-8 Durable admin audit logging | P1 | M | — |
| 7 | WS-2 Migration consolidation | P0 | L | — |
| 8 | WS-1 Dual-write retirement (#1335) | P0 | L | WS-2 recommended first |
| 9 | WS-9 Compliance `/validate` rewire (#1203) | P2 | M | — |
| 10 | WS-10 Frontend quality (ESLint, client errors) | P2 | M | — |
| 11 | WS-11 SDK cleanup | P2 | S–M | — |
| 12 | WS-12 Dead code & repo hygiene | P2 | S–M | — |

Rationale for order: the small fail-closed and operational fixes (WS-3..7) close live risk in days; the two large structural workstreams (WS-2, WS-1) run behind them, with migration consolidation first because dual-write retirement itself requires new migrations and is far safer on a single, drift-free migration system.

---

## P0 — Correctness/security of the evidence product

### WS-1: Retire the dual-write CTE persistence path (#1335)

**Problem.** Two live write paths persist traceability events with *different idempotency-key formulas*: the legacy `CTEPersistence` mixins (`services/shared/cte_persistence/`, → `fsma.cte_events`/`fsma.cte_kdes`, key from `location_gln/name`) and the canonical writer (`services/shared/canonical_persistence/writer.py`, → `fsma.traceability_events`, key from `from/to_facility`). Cross-table reconciliation is only possible via `sha256_hash` (`DUAL_WRITE_RECONCILIATION_NEEDED = True`); the reconciliation script (#2521) is a compensating control, not a fix.

**Steps.**
1. **Freeze the divergence:** add a CI-run invariant test asserting that every event written in a test ingest appears in both stores with matching `sha256_hash` (promote `scripts/validate_data_integrity.py` logic into `tests/invariants/`).
2. **Read-path inventory:** enumerate every consumer of `fsma.cte_events`/`cte_kdes` (compliance_score, FDA export, chain verification, graph sync, frontend proxies) and record which already read canonical vs legacy. Output: a checked-in cutover table (mirror the pattern of `docs/security/tenant-route-inventory.md`).
3. **Cut reads over** consumer-by-consumer to `fsma.traceability_events`, each cutover behind a per-consumer env flag with a one-release soak; verify per consumer with golden comparisons (legacy read vs canonical read must produce identical export/score output on the seeded test corpus).
4. **Backfill & verify:** one-shot backfill of any legacy rows missing from canonical (match on `sha256_hash`), then run the full chain-verification suite against canonical only.
5. **Retire writes:** remove the `CTEPersistence` write mixins' dual-write calls; keep the tables read-only for one release (DB trigger rejecting INSERT), then archive.
6. **Guard the retirement:** Sentinel anchor + a CI grep gate that fails on new imports of `cte_persistence.writes`/`batch`.

**Acceptance.** Single write path; `DUAL_WRITE_RECONCILIATION_NEEDED` deleted; all chain/Merkle/export tests green against canonical store; reconciliation script retired from ops runbooks.
**Size:** L (multi-sprint — matches the existing #1335 framing). **Risk:** highest-value, highest-care item in the plan; never delete legacy tables until an FDA-export golden diff over real seeded data is byte-identical.

### WS-2: Consolidate the three migration systems

**Problem.** ~84 migration files across Alembic (`alembic/versions/`, 51), raw Flyway SQL (`migrations/`, 28), and `services/admin/migrations/` (46, overlapping) — the proven driver of drift-repair migrations (`v077`, `v078`) and of the two divergent RLS predicate styles fixed in v090. Alembic autogenerate sees only admin's `Base`, so shared/ingestion models silently escape tracking.

**Steps.**
1. **Freeze legacy trees:** CI gate rejecting any new file in `migrations/` or `services/admin/migrations/` (extend the existing `alembic-revision-check` job in `backend-ci.yml`).
2. **Parity audit:** script that diffs the schema produced by `alembic upgrade head` on a fresh DB against a dump of the production/staging schema; every discrepancy becomes either a forward-port revision or a documented intentional difference. (The baseline `20260324_*_baseline_consolidate` already collapsed V002–V042; this closes the remainder.)
3. **Archive** the two legacy trees to `docs/archive/migrations/` (history preserved, not executable), and delete the orphan `alembic/sql/Vxxx__*.sql` files that the parity audit proves superseded.
4. **Unify metadata:** import all ORM `Base`s (`services/shared/tenant_models`, `canonical_persistence/models`, `cte_persistence/models`, per-service `models.py`) into `alembic/env.py`'s `target_metadata` (combine via `MetaData` merge or a single shared declarative base). Add a CI job running `alembic check`/autogenerate-diff that fails on untracked model drift.
5. **Extend boot check:** widen `verify_orm_db_type_alignment` beyond tenant/audit/auth tables to all canonical FSMA tables.

**Acceptance.** One executable migration system; fresh-DB `alembic upgrade head` ≡ production schema; autogenerate covers every ORM model; CI blocks new legacy-tree files and untracked drift.
**Size:** L. **Note:** `docs/MIGRATION_CONSOLIDATION.md` already commits to this direction — this workstream is finishing funded work, not a new decision.

### WS-3: Make MFA brute-force lockout fail closed

**Problem.** `_check_mfa_counter_lockout` / `_record_mfa_counter_failure` (`services/admin/app/mfa.py:478-514`) wrap Redis in `except Exception: warning` — a Redis outage silently disables lockout, TOTP replay protection, and progressive delay.

**Steps.**
1. Add a **DB-backed fallback counter** (small `fsma.mfa_failed_attempts` table keyed on user_id, pruned by the existing retention sweep) used when Redis raises; keep Redis as the fast path.
2. If the DB fallback also fails, **fail closed**: reject the MFA attempt with a retryable 503 rather than skipping lockout (consistent with the documented "fail-closed outside dev/test" auth boundary in `SECURITY_BOUNDARIES.md`).
3. Emit a Prometheus counter (`mfa_lockout_backend_fallback_total`) + alert, mirroring the `admin_audit_log_failures_total` pattern.
4. Tests: Redis-down simulation asserting lockout still enforced; Redis+DB-down asserting 503; TOTP replay under Redis outage.

**Acceptance.** No code path where repeated MFA failures go unthrottled while auth stays available. **Size:** S–M.

### WS-4: Converge tenant-GUC setting onto the canonical primitive

**Problem.** 8 ad-hoc `set_config('app.tenant_id', …)` call sites (inflow_workbench `_set_tenant_context` at ~line 261, CTEPersistence, CanonicalEventStore, ExceptionQueueService, inline SQL in canonical_router, admin paths) duplicate `services/shared/tenant_context.py::set_tenant_guc`. Divergence here is how fail-open RLS bugs (v090 class) re-enter.

**Steps.**
1. Mechanically replace each call site with `set_tenant_guc` / `set_tenant_guc_if_uuid` (the module docstring already enumerates the sites — Phase B of EPIC-A).
2. Add a Semgrep rule to `.semgrep/tenant-trust.yaml` forbidding raw `set_config('app.tenant_id'` outside `tenant_context.py` (this gate is already wired into `security.yml` as a hard gate — the rule addition makes regression impossible).
3. Run the repo-root RLS/isolation suites (`REGENGINE_REQUIRE_DB=1`) as verification.

**Acceptance.** One GUC-setting primitive; Semgrep gate enforces it; RLS suites green. **Size:** M (mostly mechanical; care needed in inflow_workbench's file-store fallback path).

---

## P1 — Operational

### WS-5: Re-enable automated deploys
`deploy.yml` is `workflow_dispatch`-only pending an unresolved Railway healthcheck investigation. Steps: reproduce the healthcheck failure against a staging Railway service (suspects from the review: `/readiness` probing Neo4j — see WS-6 — and per-call engine creation in `readiness()`); fix root cause; restore the `push`-to-main trigger behind the existing "Backend CI Status Gate" wait (#2537 semantics preserved); keep manual dispatch as fallback. **Acceptance:** two consecutive auto-deploys green from main merges. **Size:** S–M (unknown-shaped; timebox the investigation, keep manual deploys meanwhile).

### WS-6: Decouple Neo4j from production readiness
`/readiness` (server/main.py:862-1012) probes Neo4j when `NEO4J_URI` is set even though graph routers are prod-disabled — a down Neo4j can degrade or fail the Railway healthcheck. Steps: report Neo4j state as informational-only (never affects HTTP status) unless `ENABLE_EXPERIMENTAL_ROUTERS` includes graph; while there, reuse the shared engine in the Postgres probe instead of `create_engine` per call. Add a readiness unit test matrix (pg up/down × redis up/down × neo4j up/down). **Acceptance:** only Postgres can 503 readiness in the default prod config. **Size:** S. *(Do before or with WS-5 — it's a prime suspect for the healthcheck flakiness.)*

### WS-7: Governance quick wins
- **CODEOWNERS:** add a second owner (human or a review-bot requirement) for the security-critical paths (`services/shared/auth.py`, `tenant_context.py`, `.semgrep/`, migrations). If no second human exists yet, require the Copilot "Double-Lock" security persona review as an interim control — and fix `copilot-review.yml`/`labeler.yml` path routing, which still points at the retired `shared/`/`.agent/` layout, so those personas actually fire.
- **`.python-version`:** change `3.12` → `3.11` to match Docker/CI/lockfile.
- **Sentinel pinning gate:** extend `security.yml`'s `workflow-tool-pinning` job to cover *all* workflows, not just `deploy.yml`/`security.yml` (the gap that let `sentinel.yml` drift; #2562 fixed the instance, this fixes the class).
**Size:** S total.

### WS-8: Durable admin audit logging
`log_event` (`services/admin/app/audit.py:287-317`) swallows DB errors and returns `None` — a security event can be silently lost (the Prometheus counter alerts, but the record is gone). Steps: on persistence failure, spill the event to a durable side channel (append-only local file + the existing Postgres task queue for replay into the chain with correct `sequence_num` under the existing advisory lock); document that replayed events carry their original timestamp but a late sequence position; add a failure-injection test. Decide and document explicitly whether any admin mutations must *abort* when audit logging fails (recommended for tenant/role/API-key mutations — true fail-closed auditing). **Acceptance:** injected DB failure during `log_event` loses zero events across restart. **Size:** M.

---

## P2 — Debt & hygiene

### WS-9: Rewire compliance `/validate` to the real rules engine (#1203)
`services/compliance/app/routes.py` `/validate` runs only the lightweight `_validate_fsma204_config` contract behind the FTL gate; the real engine lives in `services/shared/rules/`. Steps: implement the documented "option-2 rewire" — call the rules engine's evaluation with the caller's config, map `EvaluationSummary` to the endpoint's response shape, keep the FTL scope gate in front; add golden tests comparing endpoint verdicts to direct engine evaluation; update the endpoint docstring and API docs. **Acceptance:** `/validate` verdicts derive from `services/shared/rules` with the enforcement-manifest drift test extended to cover it. **Size:** M.

### WS-10: Frontend quality
1. **Restore ESLint:** repair the `next lint` breakage from the Next 16 upgrade (or move fully to the flat-config `eslint .` invocation in CI), then burn down the downgraded `react-hooks` v7 rules one rule at a time (warning → error per rule as violations hit zero). Track as a small burndown board, not one mega-PR.
2. **Client-side error reporting:** make an explicit decision on the `instrumentation-client.ts` no-op. Recommended: a minimal `window.onerror`/`onunhandledrejection` beacon to a first-party `/api/client-errors` route (keeps Sentry out of the bundle, which was the original goal) with PII-free payloads and sampling. If the team prefers status quo, record the accepted risk in `SECURITY_BOUNDARIES.md`-style prose instead.
3. **Doc refresh:** regenerate `PAGE_AUDIT.md` route inventory (163 pages / 38 handlers; remove `/owner/*`, `/forgot-password`, `/reset-password`), fix `.env.example` (drop the stale `AUTH_SECRET_KEY` claim; document `CSRF_SECRET`, `ALLOWED_ORIGINS`, `REGENGINE_API_KEY`), prune dead prefixes from `app-routes.ts`.
4. Confirm `allowDevComplianceSnapshotFallback()` and `/auth/sso/mock` are prod-inert; add explicit tests for both gates.
**Size:** M (rule burndown is background work).

### WS-11: SDK cleanup (pre-PyPI checklist)
Reconcile the three version strings (`0.1.0.dev0` / CHANGELOG `1.1.0` / `verify_chain --version` `1.0.0`) to one source of truth; rewrite CHANGELOG to SDK-only history; remove or fix README's advertised-but-`NotImplementedError` methods (`create_record`, `check_ftl`) — either point them at the consolidated routes or delete them; extract `regengine/swarm/` (~100 KB legacy agent framework) out of the customer package; add unit tests for client retry/backoff and error mapping; execute the planned rename disambiguating `regengine/verify_chain.py` (per-record) from `frontend/public/sdk/verify_chain.py` (Merkle bundle). **Acceptance:** `pip install` of the built sdist exposes only the documented client surface; `sdk-ci` covers client behavior, not just the verifier. **Size:** S–M.

### WS-12: Dead code & repo hygiene
- **Delete:** `schemas/*.avsc` (dead, mutually inconsistent duplicate `FSMATraceEvent` defs — live contracts are `data-schemas/events/` + Pydantic), `services/scheduler/api.py` (never mounted), `frontend/build_output.txt` + `build_v2_log.txt` (stale logs leaking a developer's local path), `frontend/fix_header_verticals.py` (one-off codemod), scheduler's vestigial `redis_url` config.
- **Decide-and-do:** register a handler for the `graph_update` task type or stop enqueueing it (rows currently sit unclaimed forever); remove the deprecated Kafka consumers (`services/nlp/app/consumer/`, `review_consumer.py`, `graph/scripts/fsma_sync_worker.py`) once `EVENT_BACKBONE=pg` default is confirmed permanent.
- **Relocate:** investor `.docx` memos (repo root ×2, `docs/archive` ×7), `docs/product/Honest_Valuation_Update_2026-04-30.pdf`, `sales/`, `sales_enablement/`, and `production_bundle/` to a non-code repository or drive; refresh the stale graph/NLP service READMEs and the 5-month-old `audit/` snapshots.
- **Structural (optional, larger):** address the import-collision root cause behind the 342-line juggling `conftest.py` by renaming per-service `app/` packages to unique names — only worth doing as part of a broader services re-layout; otherwise leave documented.
**Size:** S–M (relocation needs the founder's sign-off on where business docs live).

---

## Verification standard (applies to every workstream)

- Security-touching changes (WS-1..4, WS-8) must keep the repo-root DB-required suites green (`REGENGINE_REQUIRE_DB=1`: `test_rls_coverage`, `test_e2e_tenant_isolation`, `test_audit_integrity`, `test_rls_hardening`) and pass a `/sentinel-check` run before merge.
- Anything touching persistence or export must include a golden diff against the seeded corpus (FDA export CSV byte-comparison), matching the pattern of the existing EDI/extractor golden tests.
- Each workstream lands as its own PR series referencing this plan; no batching of unrelated fixes (per `REPO_PURPOSE.md`'s production standard).
