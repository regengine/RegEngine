# RegEngine Production Remediation PRD

Date: 2026-05-01
Status: Draft for execution planning
Input: 18-team senior engineering audit covering architecture, security, API, ingestion, NLP, compliance, canonical data, audit integrity, scheduler, database, frontend, billing, observability, CI, deployment, privacy, and product planning.

## Executive Summary

RegEngine has a strong FSMA 204 product direction, but the audit found launch-blocking issues in security boundaries, tenant isolation, runtime startup, database schema alignment, ingestion correctness, evidence integrity, CI coverage, deployment readiness, privacy controls, and observability. The most serious risks are not isolated defects. They cluster around one core problem: the product promise depends on a trustworthy evidence spine, and that spine currently has too many paths where data can be accepted, transformed, exported, or displayed without the guarantees customers and regulators would assume.

This PRD defines the remediation program required to make RegEngine production trustworthy for design partners. It turns the bug hunt into sequenced product and engineering requirements with acceptance criteria, verification gates, and ownership boundaries.

## Problem Statement

Design partners need confidence that RegEngine can ingest supplier data, enforce tenant scope, validate FSMA events and KDEs, persist tamper-evident evidence, export FDA-ready records, and operate reliably under real deployment conditions. Today, several paths can bypass or break those guarantees:

- Browser-facing proxy auth can treat server credentials as caller credentials.
- Client-controlled tenant values can be forwarded with privileged server credentials.
- The consolidated FastAPI app has import collisions that can prevent startup.
- Some ingestion and supplier paths can write or read the wrong tenant.
- Canonical, compliance, identity, and rule schemas drift from runtime code.
- Audit/export verification does not bind every mutable evidence surface.
- CI gates miss large parts of the repository and allow frontend E2E to skip green.
- Production health checks and observability can report healthy while dependencies, alerts, or metrics are broken.
- Privacy and retention flows do not consistently honor erasure or mask PII.

## Goals

- Block cross-tenant access, unauthenticated proxying, and tenant override paths before any design-partner pilot.
- Make the consolidated runtime boot, route, and fail health checks correctly in production.
- Make FSMA event ingestion, canonical persistence, rule evaluation, audit chain, and FDA export internally consistent.
- Ensure all high-risk paths have executable tests that run in CI.
- Align deployment, observability, privacy, and docs with the actual production architecture.

## Non-Goals

- New non-FSMA vertical expansion.
- New microservice extraction.
- Broad UI redesign beyond trust, routing, accessibility, and data integrity fixes.
- Speculative NLP or regulatory intelligence features that do not protect the current evidence spine.

## Severity Model

- P0: Must be resolved before production pilot traffic or external trust claims.
- P1: Must be resolved before broad beta or paid onboarding.
- P2: Must be planned and scheduled before scaling usage or support load.
- P3: Debt cleanup that improves maintainability, UX quality, or docs coherence.

## Launch Blockers

| ID | Blocker | Impact | Primary Evidence |
| --- | --- | --- | --- |
| LB-001 | Browser proxy auth trusts server API key or placeholder caller values. | Public proxy routes can become unauthenticated service-key proxies. | `frontend/src/lib/api-proxy.ts`, `frontend/src/lib/proxy-factory.ts` |
| LB-002 | Browser tenant header/cookie can be forwarded with server credentials. | Cross-tenant read/write risk across admin, ingestion, FSMA, and billing surfaces. | `frontend/src/lib/proxy-factory.ts`, `services/shared/auth.py` |
| LB-003 | Consolidated backend import graph is broken by top-level `app` package collisions. | `server.main` import can fail; tests can pass or fail by import order. | `server/main.py`, `services/ingestion/app/webhook_router_v2.py`, `conftest.py` |
| LB-004 | CSV and supplier portal ingestion can persist under caller-controlled tenants. | Supplier records can be written to the wrong tenant or default tenant. | `services/ingestion/app/csv_templates.py`, `services/ingestion/app/supplier_portal.py` |
| LB-005 | Identity and canonical schema drift breaks runtime flows. | Core identity lookup, canonical persistence, FDA exports, and rule joins can fail or corrupt output. | V043/V044/V047 migrations, `canonical_router.py`, `fda_export/queries.py` |
| LB-006 | Evidence/hash-chain verification does not fully bind persisted event rows and mutable audit fields. | Tampered rows or exported PII variants can evade verification or become non-reproducible. | `audit_integrity.py`, `hash_chain`, `fda_export` paths |
| LB-007 | Rule schema and batch evaluation can reject valid runtime states or mark non-FTL products compliant. | Compliance verdicts can be wrong or unavailable. | V044 rules schema, rules engine batch paths |
| LB-008 | RLS fail-open and FORCE RLS mismatches remain in database surfaces. | Archived PCOS data can be cross-tenant readable; supplier portal persistence can fail closed into memory fallback. | V14-V18, V28, V074, `supplier_portal.py` |
| LB-009 | Production health checks, metrics, and alerts are not production-trustworthy. | Broken deployments can be marked healthy; alert rules can be inert. | `railway.toml`, `Dockerfile`, `server/main.py`, `infra/monitoring/prometheus.yml` |
| LB-010 | CI does not execute key repo-level suites and frontend E2E is advisory. | Regressions in security, migrations, kernel, and integration paths can merge green. | `.github/workflows/backend-ci.yml`, `frontend-ci.yml`, `test-suite-check.yml` |

## User Impact

- Compliance teams could trust an export that does not represent verified, tenant-scoped evidence.
- Operators could onboard suppliers and lose portal links, revoke state, or audit state after restart.
- Developers could follow public docs or dashboard flows that hit stale paths and mask real failures.
- Privacy requests could appear complete while exported audit metadata still includes erased or masked PII.
- On-call responders could see empty dashboards or silent alerts during a production incident.

## Workstreams

### 1. Auth and Tenant Isolation

Requirement `REM-P0-001`: Replace proxy auth with caller-authenticated forwarding.

Acceptance criteria:

- `REGENGINE_API_KEY` and other server env keys never satisfy `requireProxyAuth` for browser requests.
- Placeholder values such as `cookie-managed` are rejected before upstream forwarding.
- Server keys are injected only after a verified session, user JWT, or scoped caller API key.
- Tests prove unauthenticated calls to protected `/api/admin`, `/api/ingestion`, `/api/fsma`, and `/api/v1` proxies return 401 with server keys configured.

Requirement `REM-P0-002`: Make tenant context authoritative and server-derived.

Acceptance criteria:

- Browser-supplied `x-tenant-id` and tenant cookies are not trusted for privileged server calls.
- Tenant is derived from validated session membership or scoped API-key metadata.
- TenantProvider no longer defaults to an all-zero/system tenant before auth hydration.
- Negative tests cover tenant A attempting tenant B access across frontend proxies, CSV upload, supplier portal, billing portal, canonical records, and FDA export.

Requirement `REM-P1-003`: Enforce permissions instead of only API-key presence.

Acceptance criteria:

- Routes that require scoped actions use permission-aware dependencies, not raw `require_api_key`.
- Billing portal, raw record payload, audit export, and admin bootstrap routes require explicit scopes.
- First-user/sysadmin bootstrap is protected by a disabled-by-default flag plus one-time bootstrap secret.

### 2. Runtime Consolidation and Routing

Requirement `REM-P0-004`: Make the consolidated backend importable and bootable.

Acceptance criteria:

- `python3 -c "import server.main"` succeeds in a clean environment.
- Service imports use namespaced packages or relative imports without top-level `app` collisions.
- `server/main.py` no longer relies on ambiguous service directory ordering.
- CI runs an import smoke for the consolidated app.

Requirement `REM-P1-005`: Normalize route contracts between frontend and backend.

Acceptance criteria:

- Frontend proxies target actual mounted monolith routes or explicitly configured service routes.
- Compliance status, FSMA wizard, customer readiness, and NLP query paths have contract tests.
- JSON proxies preserve upstream success/error status codes and error contracts.
- Developer docs render URLs from the same route registry or OpenAPI source used by tests.

Requirement `REM-P1-006`: Decide and document scheduler/runtime ownership.

Acceptance criteria:

- Scheduler is either mounted/started by the consolidated app or documented/deployed as a separate required worker.
- Management/status endpoints reflect real scheduler service state.
- Leadership-loss, shutdown, task-type filtering, and retry semantics have tests.

### 3. Ingestion and Supplier Data Correctness

Requirement `REM-P0-007`: Prevent caller-controlled tenant writes in ingestion.

Acceptance criteria:

- CSV ingestion, supplier portal, supplier validation, EDI, EPCIS, and URL ingestion derive tenant from principal or secure token lookup.
- No ingestion path defaults to `default` tenant outside explicit local/demo fixtures.
- Tests prove tenant override attempts are rejected or ignored.

Requirement `REM-P1-008`: Fix ingest idempotency, validation, and retry semantics.

Acceptance criteria:

- EDI ISA13 dedup keys are recorded only after validation/persistence succeeds.
- Invalid or missing EDI quantities fail instead of becoming `1.0`.
- CSV invalid dates do not persist as `1970-01-01`.
- Large upload endpoints share the same size/streaming caps.
- URL ingestion validates redirects and final destinations against SSRF rules.
- Kafka and webhook failures do not acknowledge work before durable delivery or retry lease completion.

### 4. Canonical Evidence, Identity, and FDA Export

Requirement `REM-P0-009`: Align migrations, schemas, and canonical runtime models.

Acceptance criteria:

- Active migrations include columns used by identity runtime: `alias_type='tlc'`, `previous_review_id`, and `alias_snapshot`.
- `/identity/lookup` maps alias type and value correctly.
- Canonical endpoints set tenant RLS GUC before touching RLS-protected tables.
- Canonical models and DB constraints agree on quantity, timestamps, status, and rule result enums.
- Fresh Alembic database tests cover identity, canonical writes, rule evaluation, and FDA export queries.

Requirement `REM-P0-010`: Make evidence chain verification row-bound and race-safe.

Acceptance criteria:

- Hash-chain verification binds `fsma.hash_chain`, `cte_events` or `traceability_events` hashes, payload/KDE hash, and row metadata.
- Intra-batch duplicate inserts cannot corrupt successor links or create skipped hash-chain gaps.
- Audit HMAC includes mutable surfaced fields or those fields are excluded from trust claims.
- Merkle proof direction is represented and verified consistently.

Requirement `REM-P0-011`: Make FDA exports reproducible and schema-correct.

Acceptance criteria:

- Canonical FDA export v2 queries use real canonical columns and `(rule_evaluations.result = 'pass')`.
- Export verification persists options such as PII inclusion so exports can be reproduced.
- Export blocks or marks output unusable when evidence verification fails.
- Postgres-backed tests run against V043/V044/V047 schema.

### 5. Rules, Obligations, and Compliance Verdicts

Requirement `REM-P0-012`: Fix rule schema/runtime drift and batch verdict correctness.

Acceptance criteria:

- V044 rule categories and result checks include all runtime seed and engine values.
- Batch evaluation cannot mark non-FTL products compliant when single-event logic would withhold a verdict.
- `/validate` applies industry/CTE scope and treats empty strings as invalid where KDEs require values.
- Obligation graph IDs align across extracted text, YAML/model identifiers, and persisted edges.

Requirement `REM-P1-013`: Preserve semantic extraction safety.

Acceptance criteria:

- LLM fallback results are either merged into route responses or disabled with explicit status.
- Prompt-injection detection prevents model calls when configured as blocking.
- Negation-aware obligation attributes survive into downstream obligations.
- Traceability query planner direction is corrected for backward/forward chain questions.

### 6. Database, RLS, and Migrations

Requirement `REM-P0-014`: Hard-fail legacy fail-open RLS policies.

Acceptance criteria:

- A migration drops all legacy V14-V18 policies with `COALESCE(current_setting(...), tenant_id)` fail-open patterns.
- Archived PCOS tables either use fail-closed policies or are exported/dropped.
- CI rejects raw SQL policies using unsafe `app.is_sysadmin` patterns.

Requirement `REM-P0-015`: Fix supplier portal persistence under FORCE RLS.

Acceptance criteria:

- Authenticated create/list/revoke calls set tenant GUC before DB access.
- Public token lookup uses a narrow security-definer function or constrained service policy.
- In-memory portal link fallback is disabled outside local/demo.
- Tests create a link, clear process memory, and verify DB-backed fetch/submit/revoke.

Requirement `REM-P2-016`: Retire or lint raw migration companions and add hot-path indexes.

Acceptance criteria:

- Duplicate raw V053 SQL companions are moved, renumbered, or marked non-executable.
- CI rejects duplicate raw SQL migration versions.
- Canonical list/history queries have tenant/status/timestamp and tenant/supersedes indexes.
- `EXPLAIN` baselines are captured for large-tenant query paths.

### 7. Privacy, Retention, and PII

Requirement `REM-P1-017`: Make erasure enforceable in audit exports.

Acceptance criteria:

- User erasure markers are honored by every audit render/export path, including privileged PII exports.
- Audit metadata is recursively scrubbed for known PII keys and value patterns unless explicitly authorized.
- Erased subjects remain masked even when `include_pii=true`.

Requirement `REM-P1-018`: Replace broken destructive retention with archival/redaction.

Acceptance criteria:

- FSMA retention uses valid schema columns and append-only-compatible archival/redaction.
- Canonical raw payloads, evidence attachments, S3 artifacts, export packages, tool leads, and alpha signups have retention rules.
- Retention jobs are tested against migrated DB schemas with append-only triggers enabled.

Requirement `REM-P2-019`: Remove durable browser PII storage.

Acceptance criteria:

- Lead capture, retailer readiness, auth context, FSMA checklist, and Inflow Lab no longer store raw email, company, CSV, or operational payloads in `localStorage` or `sessionStorage`.
- Existing legacy keys are purged on load.
- Client storage tests assert only opaque IDs or non-PII flags are written.

### 8. Billing and Subscription Safety

Requirement `REM-P1-020`: Make Stripe idempotency and tenant scope safe.

Acceptance criteria:

- Stripe webhook events are marked processed only after successful handler completion, or use an in-progress lease plus completed marker.
- Retried events after handler failure process successfully.
- Legacy tenant-path billing portal endpoint is removed or enforces principal tenant equality.
- Same-second webhook events cannot reactivate terminal canceled states without live Stripe confirmation.

Requirement `REM-P2-021`: Fix pricing and redirect configuration.

Acceptance criteria:

- Annual checkout fails clearly when annual Stripe price envs are missing, or explicitly downgrades billing period and amount consistently.
- Redirect allowlist no longer trusts all `*.vercel.app`; it accepts only configured first-party hosts.

### 9. Frontend Product Trust

Requirement `REM-P1-022`: Make dashboard and tool flows work under cookie-only auth.

Acceptance criteria:

- Proxy-backed dashboard hooks gate on authenticated session state, not a readable API key cookie.
- Recall drills and export jobs preserve React Query cache shape after mutations.
- Customer readiness routes forward credentials and preserve upstream 401/403/500 statuses.
- Knowledge graph posts through `/api/nlp/ask`, not direct service URLs or localhost fallbacks.

Requirement `REM-P2-023`: Fix silent lead loss and accessibility blockers.

Acceptance criteria:

- Retailer readiness submission persists through an implemented route or server action.
- Failed submissions surface an error and do not store PII in localStorage.
- EmailGate uses dialog semantics, focus management, labels, and announced errors.
- Notification switches expose names and checked state.

Requirement `REM-P3-024`: Create frontend registries for tools and public APIs.

Acceptance criteria:

- Tool landing cards, related tools, nav, JSON-LD, sitemap entries, and route tests use one typed registry.
- Developer curl snippets and public endpoint docs are generated from a canonical API registry or OpenAPI source.

### 10. Deployment, Observability, and CI Gates

Requirement `REM-P0-025`: Make production health and deployment fail closed.

Acceptance criteria:

- Railway and Docker health checks point at dependency-aware `/readiness`, not shallow `/health`.
- Missing or broken `DATABASE_URL` returns 503 and fails deployment.
- `scripts/validate_env.py --strict` runs before migrations and server startup.
- Production fallbacks to dev database URLs are removed.

Requirement `REM-P1-026`: Fix container and K8s deploy artifacts.

Acceptance criteria:

- Frontend Dockerfile chooses one mode: standalone server or static `out/` serving.
- Reporting Dockerfiles build from existing paths.
- K8s service ports, probes, NetworkPolicies, and partner gateway routes match real app ports.
- CI builds production Dockerfiles and validates K8s manifests.

Requirement `REM-P0-027`: Make observability real.

Acceptance criteria:

- Prometheus can scrape every deployed service with the configured metrics auth mechanism.
- Graph, NLP, scheduler, admin, ingestion, compliance, and frontend targets are represented correctly.
- Alert rules are loaded by Prometheus and selectors match scraped labels.
- Grafana dashboards use real labels.
- Readiness checks include required dependencies and alert on dependency-specific failure.
- Tenant, request, and correlation IDs propagate through logs and Kafka headers.

Requirement `REM-P0-028`: Make CI catch cross-cutting regressions.

Acceptance criteria:

- Repo-root tests under `tests/shared`, `tests/security`, `tests/integration`, `tests/migrations`, and `kernel/*/tests` execute in CI, not only collect.
- Frontend smoke E2E is blocking in a deterministic local or staging environment.
- Production-like Playwright setup never creates users against production.
- Smoke jobs fail when service smoke tests are missing or failing.
- Coverage gates include frontend, shared services, kernel, and high-risk top-level suites.

Requirement `REM-P2-029`: Reduce supply-chain drift.

Acceptance criteria:

- Dependabot watches root Python production manifests.
- Vercel uses `npm ci` and critical frontend packages are exact-pinned or policy is updated.
- Runtime Docker image installs prod dependencies only, with test tooling in a dev/test lock.

## Milestones

### Milestone 0: Stop the Bleeding, 24 to 48 hours

- Patch proxy auth so server env keys cannot satisfy caller auth.
- Strip and re-derive tenant context for browser-facing protected routes.
- Add import smoke for `server.main` and fix the immediate top-level `app` collision.
- Make `/readiness` fail when Postgres is missing and point deploy checks at it.
- Add a blocking CI job for auth/tenant negative tests and consolidated import smoke.

Exit criteria:

- No unauthenticated protected proxy route forwards with server credentials.
- `python3 -c "import server.main"` passes.
- Broken database config fails readiness and deployment.

### Milestone 1: Tenant-Safe Evidence Spine, Week 1

- Fix CSV/supplier tenant override paths.
- Fix supplier portal FORCE RLS persistence and remove process-memory fallback outside local/demo.
- Set tenant GUC for canonical and identity RLS reads.
- Add tenant negative tests across ingestion, canonical, supplier, billing, admin, and export.

Exit criteria:

- Tenant A cannot read, write, export, bill, or portal into tenant B through audited surfaces.
- Supplier portal links survive process restart and respect revoke/expiry.

### Milestone 2: Schema, Rules, and Export Integrity, Weeks 1 to 2

- Align identity/canonical/rule migrations with runtime models.
- Fix FDA export v2 schema mapping and result joins.
- Bind evidence verification to persisted rows and payload/KDE hashes.
- Fix batch verdict handling for non-FTL products.

Exit criteria:

- Fresh DB tests cover canonical write, rule evaluation, FDA export, and verification.
- Tampered event rows or failed verification block trusted export.

### Milestone 3: Async, Billing, Privacy, and Retention, Weeks 2 to 3

- Fix webhook retry/idempotency semantics across Stripe and internal webhooks.
- Fix scheduler leadership-loss, task-type filtering, delivery acknowledgment, and shutdown behavior.
- Enforce audit erasure in export and recursively scrub metadata.
- Replace destructive retention with archival/redaction-compatible flows.

Exit criteria:

- Failed handler work retries successfully.
- Erased users cannot reappear in audit exports.
- Retention jobs pass against migrated schema with append-only triggers.

### Milestone 4: Production Readiness Gates, Weeks 3 to 4

- Make Prometheus scrape, alert rules, Grafana dashboards, and readiness probes truthful.
- Build frontend and reporting Docker images in CI.
- Validate K8s manifests and health probes.
- Run repo-root suites and blocking frontend smoke E2E in CI.

Exit criteria:

- Broken metrics, missing services, failed smoke tests, or broken Docker builds fail CI/deploy.
- On-call runbooks match live health and metrics contracts.

### Milestone 5: Product Promise Hygiene, Weeks 4 to 6

- Update product docs, roadmap, developer docs, and public tool flows to match shipped behavior.
- Remove browser PII storage and silent lead fallbacks.
- Add partner-loop metrics for readiness score delta, fix queue closure, commit-gate blocks, time-to-first-successful-ingest, and export usage.

Exit criteria:

- Public claims, developer examples, and onboarding flows match verified product behavior.
- Design-partner success metrics are observable without exposing PII.

## Verification Plan

Required pre-pilot checks:

- `python3 scripts/check_alembic_revisions.py`
- `python3 scripts/check_orphan_migrations.py`
- `python3 scripts/check_tenant_id_uuid_only.py`
- `python3 -c "import server.main"`
- Auth and tenant negative tests for protected proxy, ingestion, canonical, billing, and export paths.
- Fresh-database Alembic migration plus canonical/rule/export integration tests.
- Postgres-backed FDA export test using real V043/V044/V047 schema.
- Evidence tamper test that mutates persisted event row, payload hash, and mutable audit fields.
- Docker builds for backend, frontend, and reporting images.
- K8s manifest validation and in-cluster `/ready` smoke.
- Prometheus scrape and alert-rule tests.
- Frontend blocking smoke for login, dashboard load, tenant-scoped data, and core tool submission.

Observed baseline during audit:

- Alembic revision checks passed with one current head and grandfathered orphan files.
- Tenant UUID migration check passed for non-grandfathered migrations.
- `python3 -m compileall -q server services/shared services/ingestion/app services/admin/app services/compliance services/nlp services/scheduler kernel` passed.
- `python3 -c "import server.main"` failed due `app.authz` import collision.
- Frontend TypeScript check passed in one scoped audit.
- Frontend lint with `--max-warnings=0` failed with existing warnings.

## Risks and Dependencies

- A quick proxy-auth fix must not strand legitimate server-to-server tasks. Separate browser and internal route auth explicitly.
- RLS hardening can reveal endpoints that relied on SQL predicates without tenant GUC. Fix endpoint context before enforcing.
- Export integrity changes may force decisions on canonical versus legacy CTE source of truth for the next 90 days.
- Retention remediation must preserve legal traceability while honoring erasure and minimization.
- CI expansion may initially expose many latent failures. Treat first wave as remediation queue, not a reason to weaken gates.

## Open Questions

- What is the design-partner pilot date and minimum acceptance bar?
- Is `fsma.traceability_events` the committed canonical production contract for all new FSMA evidence?
- Which dependencies are required for `/readiness` in each deployment mode: Postgres, Kafka/Redpanda, Redis, Neo4j, S3, Stripe?
- Should rule enforcement block production evidence by default for pilot tenants?
- Who owns compliance signoff for all 7 FSMA CTE/KDE maps?
- Which public product claims should be hidden until their backing requirement is verified?

## Appendix: 18-Team Audit Coverage

1. Architecture and service boundaries: consolidation import failure, stale service URLs, scheduler ownership, readiness semantics.
2. Security, auth, and tenant isolation: proxy service-key bypass, client-controlled tenant, bootstrap, API-key permissions, RLS posture.
3. FastAPI and API surface: wrong proxy targets, stale status endpoints, wizard route mismatch, pagination and status masking.
4. Ingestion pipeline: CSV/supplier tenant override, EDI dedup and quantity validation, EPCIS session threading, SSRF redirects.
5. NLP and extraction: request tenant trust, dropped LLM fallback, Kafka retry coverage, prompt injection, negation handling.
6. Compliance, rules, and obligations: schema/runtime category drift, batch non-FTL verdict, per-industry scope, obligation IDs.
7. Canonical CTE and identity: identity schema drift, duplicate batch hash corruption, lookup argument order, RLS GUC gaps.
8. Audit, evidence, hash, and Merkle: row tamper gaps, audit HMAC mutable fields, proof direction, export reproducibility.
9. Scheduler, workers, and async: leadership-loss swallowing, unscoped task worker, shutdown, Kafka ack timing, DLQ retries.
10. Database, RLS, and indexes: supplier portal FORCE RLS, archived fail-open RLS, FDA export schema mismatch, hot-path indexes.
11. Frontend dashboard/app router: proxy auth bypass, cookie-only auth disabled queries, tenant default, cache shape.
12. Frontend tools/docs/marketing: silent assessment loss, direct NLP calls, docs base-path drift, accessibility and registry debt.
13. Billing and Stripe: webhook dedup before handler success, cross-tenant portal endpoint, annual price fallback, redirect allowlist.
14. Observability: metrics auth scrape mismatch, inert alert rules, weak readiness, missing tenant correlation, cardinality risks.
15. Test strategy and CI: repo-root tests not run, advisory E2E, production-like mutation, order-sensitive imports, fail-open QA gate.
16. Deployment and supply chain: broken frontend Docker mode, health checks on liveness, env validation not wired, stale K8s ports.
17. Privacy and retention: audit erasure/export gap, broken FSMA retention, metadata PII leak, raw payload exposure, browser storage.
18. Product remediation planning: FSMA evidence spine, tenant trust, runtime truth, design-partner readiness, promise hygiene.
