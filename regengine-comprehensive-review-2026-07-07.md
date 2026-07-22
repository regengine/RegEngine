# RegEngine Comprehensive Repository Review — Backend & Frontend

**Date:** 2026-07-07
**Scope:** Full repository — backend monolith and services, frontend, data layer, SDK, schemas, tests, CI/CD, security posture, and repo hygiene.
**Method:** Five parallel deep-dive audits (backend core pipeline; backend supporting services and data layer; frontend; infrastructure/CI/security; SDK/schemas/test health), synthesized into this report. File references are to the tree at commit `f373d5b`.

---

## 1. Executive Summary

RegEngine is a **pre-production FSMA 204 food-traceability platform**: it ingests supplier/ERP records (webhooks, CSV, EPCIS 2.0, EDI X12), normalizes them into CTE/KDE traceability evidence, scores and gates them through the Inflow Workbench, persists tenant-scoped events with a tamper-evident SHA-256 hash chain, evaluates compliance rules, and produces FDA export/audit surfaces.

**Overall verdict:** the engineering maturity here is **well above typical pre-production startup level** — particularly in tenant isolation, audit-evidence integrity, and CI security gating. The recent commit history shows disciplined, issue-tracked remediation of exactly the right vulnerability classes (cross-tenant pivots, IDOR, fail-open RLS, MFA race conditions, hash-chain integrity). The honest, self-critical documentation (`ASYNC_PROCESSES.md`, `SECURITY_BOUNDARIES.md`, trust-claims matrix) is a standout.

The debt is equally real and concentrated in five places:

1. **Dual-write persistence** — two live CTE storage paths with *divergent idempotency-key formulas* (#1335).
2. **Migration fragmentation** — 84 migration files across three parallel systems (Alembic + two raw-SQL trees), the root cause of recurring "schema drift" repair migrations.
3. **Fail-open surfaces under infra degradation** — MFA brute-force lockout disabled on Redis outage; webhook HMAC fail-open when secret unset; `dev-open` ingestion principal dependent on `REGENGINE_ENV` being set correctly.
4. **Operational single points** — one CODEOWNER on all security-sensitive files; automatic deploys disabled (manual `workflow_dispatch` only) pending an unresolved Railway healthcheck issue; Neo4j coupled to the production readiness probe even though graph routers are off in prod.
5. **Hygiene/staleness** — investor `.docx`/valuation PDFs and build logs in git, stale audit docs and READMEs, SDK version chaos, dead Avro schemas, effectively-disabled frontend ESLint.

---

## 2. System Overview & Deployment Topology

| Layer | Technology | Deploy target |
| --- | --- | --- |
| Backend | Python 3.11, FastAPI monolith (`server/main.py`), Gunicorn+Uvicorn | Railway (single container, root `Dockerfile`) |
| Frontend | Next.js 16.2.9 (App Router), React 18.3, TS 6 strict | Vercel (`frontend/`; root `vercel.json` is an intentional no-op) |
| Database | PostgreSQL 17 (Supabase in prod), RLS-enforced | — |
| Graph | Neo4j (experimental routers; supplier-mirror sync live) | — |
| Cache/limits | Redis (subscription gate, MFA counters, rate limits) | — |
| Async | Postgres-backed task queue + embedded APScheduler (Kafka deprecated) | in-process in the monolith |

**Scale:** ~273k lines of Python across 962 files (backend), ~117k lines of TypeScript across 697 files (frontend), 51 Alembic revisions, 586 backend test files (8,874 tests), 87 frontend unit-test files + 11 Playwright e2e specs.

The six `services/*` directories (admin, ingestion, compliance, graph, nlp, scheduler) are **logical boundaries only**. Production ships one image; `server/main.py` (1,012 lines) mounts ~55 routers with a `sys.path` bootstrap so per-service `app.*` imports resolve both standalone and in-monolith. Per-service `main.py` entrypoints self-block in production. Per-service Dockerfiles/requirements are deprecated but retained (#1429).

Key monolith mechanics:

- **Middleware stack:** CORS (never `*` in prod — raises), rate limiting (global + per-tenant 100 rpm), OTel observability, request-ID/correlation-ID, 10 MiB request-size cap, 120 s timeout, tenant-scoped idempotency keys.
- **Router governance:** `_EXPERIMENTAL_ROUTERS` (graph, NLP, etc.) auto-disabled in prod unless `ENABLE_EXPERIMENTAL_ROUTERS`; a compliance-critical guard **refuses boot** if `canonical_records`, `rules`, `exceptions`, `fda_export`, or `chain_verification` is disabled without an explicit override (`server/main.py:396-418`).
- **Boot integrity checks:** `verify_orm_db_type_alignment` fails boot on Alembic-vs-ORM type drift for tenant/audit/auth tables; `validate_auth_config()` refuses prod boot on weak/default/missing JWT secrets, with #2512 defense against ephemeral signing keys.
- **Health:** `/health` is trivial liveness; `/readiness` deep-probes Postgres (required), Redis/Neo4j (optional, bounded timeouts), and background-runner start state (#2518 distinguishes "disabled" from "swallowed boot failure").

---

## 3. Backend — Core Pipeline

### 3.1 Ingestion (`services/ingestion/`) — the largest domain

**Webhook ingest** (`webhook_router_v2/`, hot path `POST /api/v1/webhooks/ingest`): stacked defenses — `require_permission("webhooks.ingest")` → API-key presence check → HMAC signature (#1243) → active-subscription gate → strict tenant-scoped idempotency. Flow: principal-derived tenant resolution, per-tenant rate limit, in-batch dedup, event-timestamp replay window (#1245), KDE validation, rules pre-eval reject partition (`RULES_ENGINE_ENFORCE`), batch hash-chain persistence with per-event fallback, synchronous canonical dual-write + rule-eval persistence, non-blocking graph sync. Errors return correlation-ID-only 500s. Read endpoints return **404 (not 403) on tenant mismatch** to avoid a tenant-existence oracle.

**Inflow Workbench** (`inflow_workbench.py`, 1,170 lines — the product wedge): durable scenarios, saved runs, fix queue, readiness summaries, and a **commit-gate ladder** — `simulation`/`preflight` never export-eligible; `staging` requires zero unresolved items; `production_evidence` requires authenticated + persisted + provenance-attached + zero unresolved. DB-first persistence with a dev-only `/tmp` file fallback; in production a DB failure raises 503 rather than silently falling back (correct).

**Other ingest surfaces:** CSV templates/ingest with formula-injection-safe cells (`csv_templates.py`, 699 lines); EPCIS 2.0 XML parse/normalize/persist with strict validation and GLN check-digit verification; EDI X12 850/810/856/861 parser with segment caps and a rejection log; supplier portal preflight; sandbox rule tracer; Stripe billing with webhook idempotency.

**Subscription gate** (`subscription_gate.py`): fail-closed — missing Redis entitlement → 402, Redis error/circuit-open → 503, no tenant → 401. `SUBSCRIPTION_GATE_FAIL_OPEN=true` exists as an incident escape hatch and logs `critical` per request.

**FDA export** (`fda_export/`, 51 KB router): Merkle proofs, recall support, coverage checks, PII redaction; export windows capped at 90 days; recently hardened `/export/all` with batched fan-out and offloaded blocking DB I/O (#2515/#2516).

### 3.2 Compliance (`services/compliance/`)

Loads `fsma_rules.json` (5 industries, 5 checklists) at import, failing loudly if malformed. `POST /validate` strictly gates on FTL commodity scope (400 `E_NON_FTL_FOOD` for out-of-scope foods — deliberately preventing false "compliant" stamps). The audit-spreadsheet export is the strongest-hardened route: tenant bound to the API key (409 on mismatch), 90-day window, formula-injection/header-splitting defenses, 50k-row cap → 413, zero-row → 404.

**Known gap:** `/validate` runs only a lightweight field contract — it **does not invoke the real rules engine** in `services/shared/rules/` (the #1203 "option-2 rewire" is pending). The compliance service's headline endpoint is semantically thinner than its name implies.

### 3.3 Shared kernel (`services/shared/`)

**Tenant authority** (`tenant_context.py`, 456 lines): declared single source of truth. Tenant derived **only** from the authenticated principal (API key → principal → user), never path/query/body/headers. Defense-in-depth: any caller-supplied tenant claim that conflicts with the principal → 409 `E_TENANT_MISMATCH`. A custom Semgrep rule (`.semgrep/tenant-trust.yaml`) enforces forbidden patterns in CI. The canonical DB primitive is `set_tenant_guc()` (transaction-scoped `set_config('app.tenant_id', …)`); RLS policies reference it via a fail-hard `get_tenant_context()` SQL function. The middleware trusts the `X-RegEngine-Tenant-ID` header only with a valid internal-service HMAC secret; spoofing attempts are logged and counted.

**Hash-chain persistence** (`cte_persistence/`, ~2,500 lines + `canonical_persistence/writer.py`, 54 KB): SHA-256 pipe-delimited canonical hashing (free-text `product_description` excluded so reformatting doesn't break re-verification, #1323; exotic types normalized deterministically, #1313), `'GENESIS'` chain seed, append-only enforced both app-side and by a DB trigger, per-tenant chain serialization via `pg_advisory_xact_lock` (#1332). `verify_chain` walks genesis→head recomputing every link, checks sequence continuity, and cross-checks orphan/missing chain rows. Merkle trees give O(log n) inclusion proofs. Rejected events are persisted for audit but excluded from chain/export/graph.

**Rules engine** (`rules/`, ~1,900 lines): enforcement modes `off|cte_only|all` (default `off` = log-and-accept); a no-verdict never rejects; the manifest of enforcement-aware call sites is drift-tested in CI.

**Auth** (`auth.py` + ingestion `authz.py`): env-gated test bypass (dev/test only, fail-closed), master key that *requires* a valid-UUID tenant (#1068 — prevents RLS bypass via null tenant), DB-backed API-key store in prod, IP-based auth-failure rate limiting, role/action RPM matrix.

**DB session layer** (`database.py`): pool tuning, hand-rolled circuit breaker + jittered retry + bulkhead semaphore, Prometheus gauges, refuses prod boot without `DATABASE_URL`.

### 3.4 Core-pipeline risks

| # | Risk | Detail |
| --- | --- | --- |
| B1 | **Dual-write debt (#1335)** | Legacy `cte_events`/`cte_kdes` path coexists with canonical `traceability_events` writer, with **different idempotency-key formulas** — cross-table reconciliation must use `sha256_hash`. Reconciliation is scripted (#2521) but the shim is live. Single biggest correctness liability. |
| B2 | **Tenant-GUC duplication** | 8 ad-hoc `set_config('app.tenant_id')` call sites remain (inflow_workbench, canonical_router, etc.) vs the canonical `set_tenant_guc` — documented Phase-B convergence, real maintenance hazard until done. |
| B3 | **`/validate` ≠ rules engine** | The compliance validate endpoint doesn't run the real rules engine (#1203 pending). |
| B4 | **Env-dependent fail-open surfaces** | Webhook HMAC fail-open when secret unset (alarmed via health flag); `dev-open` ingestion principal (`scopes=["*"]`, no tenant) if `REGENGINE_ENV` is unset; `SUBSCRIPTION_GATE_FAIL_OPEN` escape hatch. All logged, all dependent on correct env configuration. |
| B5 | **Import/topology fragility** | Dual sys.path scheme; `_COMPLIANCE_ROUTERS` duplicated between `server/main.py` and `services/ingestion/main.py` with a comment demanding manual sync. |
| B6 | Minor | DB circuit breaker only wraps a `SELECT 1` probe, not real queries; `/readiness` constructs a throwaway engine per call. |

---

## 4. Backend — Supporting Services

### 4.1 Admin (`services/admin/`, ~51k LoC — identity, RBAC, MFA, audit)

- **Tenant claims read only from Supabase `app_metadata`** (service-role writable), never user-writable `user_metadata` (#1345). Infra failures fail closed in prod; sysadmin without a bound tenant fails closed (#1065). RBAC via a `PermissionChecker` dependency with wildcard/namespace permissions.
- **Audit hash chain is the crown jewel:** integrity-hash schema is on **v3** — v2 (#1415) folded actor/severity/endpoint fields in (so a SQL-capable attacker can't rewrite "who did this" without breaking the chain); v3 (#2513) folds per-tenant `sequence_num` to detect forked heads/removed rows, with `pg_advisory_xact_lock` chain-head serialization and a `UNIQUE(tenant_id, sequence_num)` constraint. `verify_chain` recomputes v3→v2→v1 with a distinct `sequence_gap` error and surfaces `legacy_v1_rows` so auditors see which rows lack actor tamper-evidence (#2523).
- **Concerns:** audit logging is **best-effort** — `log_event` swallows DB errors and returns `None` (alertable via `admin_audit_log_failures_total`, but the event is simply lost); **MFA brute-force lockout fails open on Redis outage** (`mfa.py:478-514`) — TOTP replay protection and progressive delay share the dependency; MFA secrets Fernet-encrypted with a transitional plaintext-column fallback (#1376); recovery codes hashed and (per #2555) atomically consumed.

### 4.2 Scheduler (`services/scheduler/`)

Embedded APScheduler with **Postgres advisory-lock leader election** (lock id 4294967295) + heartbeat re-verification against `pg_locks` — a genuinely robust single-flight pattern across gunicorn workers/replicas. ~10 jobs (FDA warning letters/import alerts/recalls scrapers with per-scraper circuit breakers, FSMA nightly sync, deadline monitor, retention/archival sweeps). Webhook delivery has a real DLQ with `Retry-After` honoring and 4xx/5xx discrimination.
**Debt:** `redis_url` config is vestigial (circuit-breaker state is actually in-memory, per-worker); `api.py` management API is dead code (never mounted); the `graph_update` task type has a visibility timeout but **no registered handler** — enqueued rows sit unclaimed.

### 4.3 Graph (`services/graph/`) — Neo4j, experimental

FSMA lot-lineage traversal (trace/recall/compliance routers). Tenant isolation: per-tenant *databases* on Neo4j Enterprise, else property-based `tenant_id` predicates — the latter is only as safe as query discipline (no DB-enforced boundary like RLS). Routers are **off in production** (`_EXPERIMENTAL_ROUTERS`), but Neo4j is not dead: admin's supplier-graph sync mirrors onboarding into it, and `/readiness` probes it when `NEO4J_URI` is set — **a disabled subsystem can still degrade the production healthcheck**. README still describes the pre-FSMA "regulatory arbitrage" product (stale).

### 4.4 NLP (`services/nlp/`) — experimental

Production-wired piece: a deterministic regex extractor consumed by the Postgres task queue, plus a rule-based (deliberately non-LLM) NL query planner feeding graph queries. The LLM extractor (OpenAI/Vertex) is wired only into the deprecated Kafka path but has **notably good prompt-injection hardening**: sentinel-wrapped untrusted content, anti-injection system prompts (#1238), and a hallucination guard requiring extracted text to appear verbatim in the source. Whole router surface is off in prod, consistent with the "Not an AI product" positioning. README's LLM wiring section is stale.

### 4.5 Test data (`services/test_data/`)

Not a service — 25 `.jsonl` scraper audit fixtures with no code and no production imports; name-collides with the root-level `test_data/` used by e2e simulation. Relocate.

---

## 5. Data Layer — Migrations, RLS, Models

- **51 Alembic revisions**, date-prefixed, with a baseline consolidating 41 legacy Flyway migrations and a guard blocking baseline downgrade (#1264). Alembic's `target_metadata` is admin's `Base` only.
- **RLS is the dominant theme and the most instructive history:** `v090_rls_predicate_hardening` (#2526) converged two divergent policy styles — fail-hard `get_tenant_context()` vs **fail-open** `current_setting('app.tenant_id', true)` (unset GUC silently matched rows; `task_queue` even had an explicit `OR current_setting(...) = ''` returning **every tenant's rows**). This was a latent cross-tenant leak, live until recently. CI now has an `rls-fallback-check` guard rejecting fail-open predicates in new migrations — the right systemic response.
- **Three parallel migration systems** (`docs/MIGRATION_CONSOLIDATION.md` admits it): Alembic (51) + raw Flyway SQL `migrations/` (28) + `services/admin/migrations/` (46) ≈ **84 files with overlapping operations**. This is the highest systemic data-layer risk and demonstrably drives drift-repair migrations (`v077 railway_warning_schema_drift`, `v078 orphan_migration_forward_ports`).
- **Model sprawl:** ORM models scattered across `services/admin/app/sqlalchemy_models.py` (canonical), four `services/shared/*` model modules, and per-service `models.py`. Alembic autogenerate only sees admin's `Base`, so shared/ingestion models risk silently escaping migration tracking.

---

## 6. Frontend (`frontend/`)

### 6.1 Stack & structure

Next.js 16.2.9 / React 18.3 / TypeScript 6 strict; Radix + Tailwind (semantic `--re-*` token design system) + CVA + framer-motion; React Query + axios; Dexie (offline scan flow), jsPDF, html5-qrcode, PostHog + Vercel Analytics. Deliberate exact-version **pinning policy** (next, eslint-config-next, @sentry/nextjs, @supabase/supabase-js — enforced by `package-pins.test.ts`) plus an `overrides` block pinning security-sensitive transitives.

**163 pages** across ~130 route directories: marketing/product/compare/blog/verticals, ~25 SEO lead-gen `/tools/*` pages, the authenticated app (`/dashboard/*` ~24 pages, `/fsma/*`, compliance/controls/review/ingest/records/rules/audit), passwordless auth flows (email-OTP/WebAuthn/SSO — no password reset by design), sandbox/proof/verify public trust surfaces, `/docs/*` + developer portal, and admin/sysadmin.

### 6.2 BFF / proxy layer — the strongest part of the frontend

**38 API route handlers** consolidated through `src/lib/proxy-factory.ts` + `api-proxy.ts` (factories introduced after per-route drift caused bug #1152). Shared preflight: static-export guard → proxy auth → session validation → path sanitization (blocks `..`, null bytes) → typed UUID validation on dynamic segments. Security properties:

- **Browser JS never holds service credentials.** Caller-supplied `Authorization`/API-key/tenant headers are *stripped* on browser-origin requests and re-injected from httpOnly cookies; first-party service credentials are injected only after validation and **fail closed** (401 `TENANT_CONTEXT_REQUIRED`).
- **IDOR guard** (`enforceTenantMatch`, #2501/#2504/#2552): for `[tenantId]` routes, the authoritative tenant comes from the JWT claim or is server-derived from `/auth/me`; the client-writable `re_tenant_id` cookie is **never** an authorization input; unknown principals → 403.
- `src/proxy.ts` (Next 16's renamed middleware) applies per-request **CSP nonces**, double-submit CSRF on mutating API calls, and a three-strategy auth gate (opaque `__Host-` session → legacy JWT → Supabase). JWTs are decoded but not verified client-side — the backend is authoritative.
- Session route: httpOnly token cookies, strict same-origin POST enforcement via `ALLOWED_ORIGINS` (login-CSRF defense), GET returns booleans never tokens, legacy localStorage secrets migrated to cookies then deleted.
- `nlp/ask` proxy rewritten (#2538) to stop forwarding caller credentials verbatim; gated behind an experimental-features flag with explicit `503 nlp_service_not_configured`.

Production startup asserts `CSRF_SECRET` is present and distinct from legacy JWT secrets (`instrumentation.ts`).

### 6.3 Frontend concerns

| # | Concern | Detail |
| --- | --- | --- |
| F1 | **ESLint effectively off** | Config comments admit `next lint` silently broke at the Next 16 upgrade; multiple react-hooks v7 rules downgraded to warnings "so existing violations don't block CI." Real lint-debt backlog. |
| F2 | **No client-side error reporting** | `instrumentation-client.ts` is a deliberate no-op shim — browser Sentry disabled; client runtime errors are invisible. Needs a conscious sign-off or a lightweight reporter. |
| F3 | **Doc/route drift** | `PAGE_AUDIT.md` and `app-routes.ts` reference non-existent `/owner/*` (15 pages), `/forgot-password`, `/reset-password` (obsolete post-passwordless); counts stale (says ~150 routes/29 handlers vs actual 163/38). `.env.example` describes an `AUTH_SECRET_KEY` verification role the code no longer has; `ALLOWED_ORIGINS`/`CSRF_SECRET` are required in prod but undocumented there. |
| F4 | **Checked-in junk** | `build_output.txt`/`build_v2_log.txt` (stale Next 15.5 logs leaking a developer's local absolute path), `fix_header_verticals.py` (one-off codemod). Delete. |
| F5 | **Dual auth complexity** | Custom JWT/opaque-session + Supabase fallback with cross-validation — several documented desync edge cases; long-term consolidation candidate. |
| F6 | **Mock-data surface** | Substantial mock/dev data in `src/lib/`; dev compliance-snapshot fallback is gated by `allowDevComplianceSnapshotFallback()` — verify that gate can't activate in prod. |
| F7 | `/auth/sso/mock` route | Confirm dev-only gating. |
| F8 | `npm ci` fails on lockfile drift | Session bootstrap had to fall back to `npm install` — `package-lock.json` is out of sync with `package.json`. Regenerate and commit. |

Testing is strong where it matters: 87 vitest files (11 dedicated to proxy sanitization/IDOR/session-origin, 19 lib incl. CSRF/safe-redirect/permissions), 11 Playwright e2e specs (auth, RBAC gates, tenant isolation, security-audit fixes), plus `promise-audit` and `production-readiness` script gates. Coverage is thinner on the sprawling `/tools/*` and marketing pages.

---

## 7. SDK (`regengine/`) & Schemas (`schemas/`)

**SDK:** an httpx-based customer client (retry/backoff, typed exceptions, dataclass models) whose headline feature is `regengine-verify` (`verify_chain.py`) — an MIT, dependency-light offline verifier that must stay byte-identical to the server's canonical hash (pinned by a golden-digest test, #2507). Not yet on PyPI.

Flags:
- **Version chaos:** `__init__.py`/`setup.py` say `0.1.0.dev0`, CHANGELOG says `1.1.0`, `verify_chain --version` says `1.0.0`. CHANGELOG also documents methods that don't exist and backend-platform changes that aren't SDK changes.
- **README advertises broken methods:** `create_record()` and `check_ftl()` now `raise NotImplementedError` (routes removed in consolidation, #2531) but remain in Quick Start.
- **`regengine/swarm/`:** a ~100 KB legacy autonomous-agent framework (Planner/Coder/Reviewer/Tester + GitHub integration) shipping *inside the customer SDK package*, disabled behind `REGENGINE_ENABLE_LEGACY_SWARM=1`. Extract or delete before publishing.
- Client methods (retries, error mapping) have no unit tests; only the verifier is tested.
- Name collision: `regengine/verify_chain.py` (per-record) vs `frontend/public/sdk/verify_chain.py` (Merkle bundle) — same filename, different programs; rename planned.

**Schemas:** the three root `schemas/*.avsc` files are **dead** — no code loads them; live contracts are JSON-Schema in `data-schemas/events/` plus the Pydantic `FSMAEvent`. Worse, `fsma_event.avsc` and `fsma_trace_event.avsc` define the *same record name with conflicting enums* (DISPOSE/CREATION/INITIAL_PACKING vs DISPOSE/CREATE) — a latent trap. Delete or archive.

---

## 8. Testing & Code Quality

- **8,874 backend tests / 535 modules collect cleanly** (exit 0, no external services needed for collection; SQLite/in-memory degradation paths). Distribution: ingestion 179 files, root `tests/` 174, admin 89, shared 46, graph 30, nlp 28, scheduler 24, compliance 12.
- **Security-heavy coverage** matching the threat model: tenant (49 files), audit (27), isolation (12), RLS (7), security (16), auth (16), MFA (4), IDOR (2), Merkle (2). Golden/snapshot tests freeze the FSMA regex extractor and EDI X12→KDE mapping against committed expected outputs (#2525/#2536) — the right defense against silent evidence corruption.
- CI enforces **per-service coverage floors** (compliance 80% … shared 35%) and the `repo-root-suite` sets `REGENGINE_REQUIRE_DB=1` so RLS/isolation/hash-chain suites **fail rather than skip** when the DB is absent (#2502/#2530) — an unusually good anti-pattern-defeat.
- **Quality-tooling gaps:** repo-wide ruff config selects import-sorting only (CI's separate bug gate runs `E9,F63,F7,F82`); mypy configured but explicitly not a CI gate. Tech-debt markers are remarkably low (21 TODO/HACK/XXX total).
- **Structural smells:** a 342-line root `conftest.py` juggles `sys.modules`/`sys.path` per-test because six services each ship a colliding top-level `app/` package — clever, fragile, and a symptom of the import layout fighting the monorepo. `services/admin/app/database.py` creates its engine at **import time** (bare `import server.main` fails without env), blocking import-only tooling. Several 50–72 KB test files want splitting. ~120 ingestion test files carry a mechanical `_1342` suffix from a coverage-backfill batch.

---

## 9. Infrastructure, CI/CD & Security Posture

### 9.1 Build & deploy

Two-stage hash-pinned (`pip install --require-hashes`) backend image, non-root user, runtime prunes build tooling, entrypoint runs migrations then Gunicorn; Railway healthcheck on `/readiness`. Frontend: standalone Next build on Vercel (Docker image exists for parity). Dev stack is deliberately minimal (Postgres 17 only).

**Delivery gap:** `deploy.yml` is `workflow_dispatch`-**only** — automatic deploys disabled pending a Railway healthcheck investigation. The gate itself is well-built (#2537 fixed frontend-only SHAs green-lighting backend deploys; skipped-checks ≠ pass).

### 9.2 CI (19 workflows) — a genuine strength

- **Self-policing supply chain:** all actions SHA-pinned, with a meta-gate that rejects any mutable ref in privileged workflows; gitleaks + detect-secrets + Semgrep (OWASP gate + custom tenant-trust rules) + pip-audit/npm-audit with per-CVE documented ignores + Trivy + syft SBOM with cosign keyless signing.
- **Incident-encoding migration guards:** `rls-fallback-check` (rejects fail-open RLS), `tenant-id-uuid-check` (rejects TEXT tenant-id drift), alembic-revision sanity, f-string SQL ban, new-migration `tenant_id` + `ENABLE ROW LEVEL SECURITY` enforcement, append-only enforcement on audit tables (blocks UPDATE/DELETE/UPSERT).
- **Trust-claims gating:** `docs/security/TRUST_CLAIMS_MATRIX.md` + CI checks ban overclaiming phrases ("SOC 2 Type II", "FDA-ready", "GA") in public copy — unusually disciplined for a startup.
- **Project Sentinel:** a bespoke regression-audit harness (`.claude/agents/`, `sentinel.yml`) that anchors checks to closing-PR diffs to detect (a) shipped security fixes being weakened/reverted and (b) new cross-service interstitial vulnerabilities — mature internal audit machinery.
- Dependabot gives security-critical packages solo PRs (unbatched review) weekly.

### 9.3 Security posture & recent remediation

`SECURITY_BOUNDARIES.md` defines a crisp threat model (tenant, persistence, auth, admin boundaries; fail-closed outside dev/test) including a documented **accepted risk**: B2B `/exchange/send` deliberately does not existence-check receiver tenants to avoid an enumeration oracle. `docs/security/` includes an ADR trail from a 2026-03 audit (10 criticals), SOC2 control matrix, pentest scope, IR plan, and a remediation matrix.

The last ~30 commits are a dense, issue-tracked hardening stream: cross-tenant pivot + DB-key 401 gaps (#2504/#2524/#2543), compliance IDOR via server-derived tenant guard (#2552), graph fail-closed on null tenant (#2511/#2540), RLS predicate convergence (#2526), atomic MFA recovery-code consume + portal abuse controls (#2555), audit-chain serialization + fail-closed export self-logging (#2513/#2522), canonical chain verifier + SDK hash fix (#2506/#2507/#2523). Active, competent remediation — but also evidence these classes were present until recently; the graph layer and any remaining legacy routes deserve continued suspicion.

### 9.4 Secrets & env hygiene

`.env` untracked (verified); `.env.example` fully templated with no real secrets; layered scanning baselines kept in sync (`.gitleaks.toml` tightened per #1161, `.trivyignore` sync-checked). **Flag:** `.python-version` says **3.12** while Docker/CI/lockfile are pinned to **3.11** — a local pyenv user will resolve dependencies that diverge from CI/prod. Should read 3.11.

### 9.5 Governance

**Single CODEOWNER (`@PetrefiedThunder`) on everything including security-sensitive files** — bus-factor and segregation-of-duties gap. Stale automation config: `copilot-review.yml` and `labeler.yml` route personas at retired paths (`shared/**`, `.agent/`), silently weakening those review lanes.

---

## 10. Repo Hygiene

Non-code material living in the product repo: two investor-outreach `.docx` memos at repo root, seven more `.docx` + a **valuation PDF** under `docs/archive`/`docs/product`, `sales/` and `sales_enablement/` collateral trees, a buyer-facing `production_bundle/`, checked-in frontend build logs, root-level point-in-time status reports, and the stale-by-its-own-admission `audit/` directory (2026-03 snapshot). Recommend moving business/investor material to a separate repo or drive, and deleting generated artifacts. (Counterpoint: the *control* docs — `README`, `REPO_PURPOSE`, `ASYNC_PROCESSES`, `PRODUCTION_SURFACE`, `SECURITY_BOUNDARIES` — are accurate, honest, and should stay.)

---

## 11. Prioritized Risk Register

**P0 — correctness/security of the evidence product**
1. Finish dual-write retirement (#1335) — divergent idempotency keys across two live CTE stores (§3.4 B1).
2. Consolidate 84 migrations / 3 systems into Alembic; bring all ORM `Base`s under autogenerate (§5).
3. Make MFA lockout fail closed (or degrade to DB-backed counters) on Redis outage (§4.1).
4. Converge the 8 ad-hoc tenant-GUC call sites onto `set_tenant_guc` and add a CI guard (§3.4 B2).

**P1 — operational**
5. Resolve the Railway healthcheck issue and re-enable automated deploys (§9.1).
6. Decouple Neo4j from `/readiness` (or make it never-degrading) while graph is experimental (§4.3).
7. Add a second CODEOWNER/reviewer for security-sensitive files (§9.5).
8. Durable failure handling for admin audit `log_event` (queue + retry, not swallow) (§4.1).
9. Fix `.python-version` → 3.11; fix frontend lockfile so `npm ci` works (§9.4, §6.3 F8).

**P2 — debt & hygiene**
10. Rewire compliance `/validate` to the real rules engine (#1203) (§3.2).
11. Restore frontend ESLint and burn down the react-hooks warning backlog; decide on client-side error reporting (§6.3 F1/F2).
12. SDK: reconcile versions/CHANGELOG/README, remove `swarm/`, test the client surface, rename the colliding verifier (§7).
13. Delete dead `schemas/*.avsc`, `scheduler/api.py`, deprecated Kafka consumers; register or remove the `graph_update` task type (§4.2, §7).
14. Refresh stale docs (`PAGE_AUDIT.md`, `.env.example`, graph/NLP READMEs, copilot/labeler paths); purge build logs, codemods, and investor artifacts from git (§6.3, §10).

---

## 12. Bottom Line

For a pre-production codebase, RegEngine's security engineering — fail-closed tenant authority, tamper-evident hash chains with real verification, RLS with CI-enforced fail-hard predicates, self-policing supply-chain CI, and honest self-documenting risk registers — is exceptional. The FSMA ingest→canonicalize→validate→persist→export spine is real, tested, and defensible. The counterweights are consolidation debt (dual-write, triple migration systems, model sprawl, import juggling), a handful of fail-open behaviors under infra degradation, and organizational single points (one code owner, manual deploys). None are architecture-invalidating; all are tractable; the P0 list above is where the next engineering cycles should go.
