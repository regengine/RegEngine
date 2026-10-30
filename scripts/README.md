# scripts/ registry

Every top-level file in `scripts/` has one line here saying what it is for and
what invokes it. `scripts/check_scripts_registered.py` fails CI when a file is
added without a line, so the directory cannot silently collect orphans again
(tech-debt WI-08, 2026-10-30). Subdirectories are described once each.

Status values: **used** (a workflow, image, runbook or document names it),
**data** (a non-executable file a script reads),
**manual** (a documented hand-run procedure), **one-time** (done, kept for the
record), **retire with WI-12**, **archive candidate** (no known use; moving it
to `scripts/_archive/` needs the owner's approval by name, per the
remediation PRD). The 14 candidates stay in place until then; the move is
`git mv scripts/<name> scripts/_archive/<name>` plus a status change here.

## Top-level scripts

| Script | Status | Purpose / invoked by |
|---|---|---|
| `apply_runtime_role_cutover.py` | used | Idempotently reapply the v111 runtime-role cutover as schema owner. — invoked by `Dockerfile`, `docs/operations/DATABASE_ROLE_CUTOVER.md` |
| `audit-issues-pass2.py` | archive candidate | one-off GitHub issue creator, second pass, March 2026 |
| `audit-issues.py` | archive candidate | one-off GitHub issue creator from the March 2026 audit |
| `audit_api_key_scopes.py` | used | Audit RegEngine API keys for over-broad scopes. — invoked by `docs/runbooks/api_key_scope_audit.md` |
| `audit_fsma_rule_catalog.py` | manual | manual: regenerate `docs/audits/FSMA_RULE_CATALOG.md` and `.json` after a rule seed change (tested in `tests/scripts/`) |
| `backfill_canonical_from_legacy.py` | retire with WI-12 | retire with WI-12: WS-1c backfill of canonical rows from legacy `cte_events` |
| `backfill_obligation_catalog.py` | one-time | one-time, run 2026-10-08 (Decision 3 obligation quarantine); kept for the record |
| `backup_neo4j.sh` | used | backup_neo4j.sh — Offline Neo4j backup via neo4j-admin (#2939) — invoked by `docs/operations/DISASTER_RECOVERY.md` |
| `backup_postgres.sh` | used | backup_postgres.sh — Automated PostgreSQL backup with retention (#1003) — invoked by `docs/operations/DISASTER_RECOVERY.md`, `docs/operations/MIGRATION_V079_TO_V120_2026_09_05.md` |
| `check_alembic_revisions.py` | used | CI guard — reject Alembic migrations that would corrupt the revision DAG. — invoked by `.github/workflows/backend-ci.yml`, `README.md` |
| `check_api_host_strings.py` | used | Guard against api.regengine.co (no DNS) in user-visible code samples. — invoked by `.github/workflows/frontend-ci.yml` |
| `check_dep_versions.py` | used | CI guard — reject dependency version drift between the declared floors and the lock. — invoked by `.github/workflows/backend-ci.yml` |
| `check_docs_links.py` | used | Fail CI when documentation references a repo path that does not exist. — invoked by `docs/CODEBASE_MAP.md` |
| `check_enabled_outbound_http.py` | used | Reject raw HTTP clients in release-enabled outbound-fetch paths. — invoked by `.github/workflows/backend-ci.yml` |
| `check_fda_spreadsheet_headers.py` | manual | manual: compare our FDA sortable-spreadsheet headers with FDA's template when FDA republishes it |
| `check_legacy_dead_code.py` | used | Guardrail for high-confidence legacy and dead-code drift. — invoked by `.github/workflows/legacy-code-scan.yml` |
| `check_no_kernel_control_imports.py` | used | Guard: forbid imports of ``kernel.control`` from production code. — invoked by `.github/workflows/backend-ci.yml` |
| `check_orphan_migrations.py` | used | CI guard: keep orphan migrations at zero. — invoked by `.github/workflows/backend-ci.yml`, `README.md` |
| `check_public_api_surface.mjs` | used | check_public_api_surface.mjs — invoked by `.github/workflows/public-api-surface.yml` |
| `check_rls_fallback.py` | used | CI guard — reject RLS policies that fall back to a constant tenant. — invoked by `.github/workflows/backend-ci.yml`, `docs/engineering/TEARDOWN_FOLLOWUP_2026_09_05.md` |
| `check_schema_channels.py` | used | CI guard — every SQL file in the two non-Alembic schema channels names the — invoked by `.github/workflows/backend-ci.yml`, `docs/runbooks/ALEMBIC_VERSION_RECONCILE.md` |
| `check_scripts_registered.py` | used | this registry's guard — invoked by `.github/workflows/backend-ci.yml` (lint-repo-roots) |
| `check_tenant_id_uuid_only.py` | used | CI guard — reject new migrations that drift tenant isolation. — invoked by `.github/workflows/backend-ci.yml`, `README.md` |
| `check_trivyignore_sync.py` | used | CI guard — keep .trivyignore in lockstep with the pip-audit ignore set. — invoked by `.github/workflows/security.yml` |
| `check_trust_safety_copy.py` | used | Fail CI when trust-and-safety outcome claims drift back into UI copy. — invoked by `.github/workflows/frontend-ci.yml`, `.github/workflows/pr-gate.yml` |
| `check_workflow_inventory.py` | used | CI guard: keep workflows and branch-protection required contexts in sync. — invoked by `.github/workflows/pr-gate.yml`, `docs/runbooks/BRANCH_PROTECTION.md` |
| `clear_fsma_data.sql` | manual | dev/test helper: clear FSMA demo rows for the zero-UUID tenant in one transaction; header says never against production |
| `compliance_sweep.py` | used | self-described legacy sweep; named by `tests/swarm/test_swarm_guards.py`, so it stays (PRD WI-08 requirement 4) |
| `create_copilot_issues.sh` | archive candidate | one-off issue batch for retired vertical development |
| `create_neo4j_indexes.sh` | manual | create Neo4j indexes for the optional graph tier; its secret handling is covered by `services/shared/tests/test_secret_redaction.py` |
| `create_test_api_key.py` | used | Mint a tenant-scoped RegEngine API key for local/dev testing. — invoked by `README.md` |
| `demo_freshness.py` | manual | manual: check the demo narrative dates before a demo |
| `deploy_railway.sh` | manual | Railway deploy wrapper for the monolith; documented in its own header (`docs/operations/PRODUCTION_DEPLOYMENT.md` is the procedure) |
| `deploy_rls.py` | used | Retired direct RLS SQL deploy helper. — invoked by `docs/runbooks/MIGRATION_ROLLBACK.md` |
| `deploy_rls.sh` | used | deploy_rls.sh — invoked by `docs/operations/rls_deployment_runbook.md`, `docs/runbooks/MIGRATION_ROLLBACK.md` |
| `e2e_brutal_scenario.py` | used | Brutal End-to-End Scenario — invoked by `docs/engineering/security-findings-2026-09-10/dispositions.json` |
| `e2e_tests.js` | archive candidate | targets the retired multi-service ports (8400, 8000, 8500); superseded by `tests/` e2e suites and `frontend/` Playwright |
| `env_preflight.sh` | manual | manual: local environment preflight before starting the stack |
| `export-openapi.sh` | manual | legacy helper for local inspection of non-production services (its header says so) |
| `export_env_bundle.py` | used | Validate the local secret set, and optionally emit it to stdout for piping. — invoked by `docs/engineering/TEARDOWN_FOLLOWUP_2026_09_05.md` |
| `extract_document.py` | used | Extract structured data from a local document with LlamaIndex Extract v2.5. — invoked by `docs/engineering/DOCUMENT_EXTRACT.md` |
| `format_chaos_results.py` | manual | manual: after a `scripts/chaos/` run, format results for a GitHub step summary |
| `generate_redis_certs.sh` | manual | local-dev self-signed Redis TLS certs (#999); output dir is gitignored |
| `generate_route_security_manifest.py` | used | Generate or verify the route-complete production security manifest. — invoked by `.github/workflows/backend-ci.yml`, `docs/engineering/ROUTER_SURFACE.md` |
| `health_check.py` | manual | manual: founder's health check against a running stack (tested in `tests/scripts/`) |
| `ingest_document.py` | used | RegEngine Regulatory Document Ingestion Script — invoked by `docs/engineering/CONTENT_INGESTION.md` |
| `init-postgres.sh` | used | init-postgres.sh — Create additional databases required by services — invoked by `.github/workflows/backend-ci.yml`, `.github/workflows/inflow-contract-ci.yml` |
| `install_pkgs.sh` | used | Non-interactive bootstrap for Claude Code on the web sessions, whose — invoked by `.github/workflows/sentinel.yml` |
| `jev_ask.py` | used | Ask TypeSafe Jev typed questions from the command line. — invoked by `docs/engineering/JEV_HEADER_MAPPING.md`, `docs/engineering/JEV_LAB.md` |
| `jev_eval.py` | used | Measure TypeSafe Jev on RegEngine's own CSV header rows. — invoked by `docs/engineering/JEV_HEADER_MAPPING.md`, `docs/engineering/JEV_LAB.md` |
| `jev_header_preview.py` | used | Preview TypeSafe Jev header-mapping suggestions for a local CSV file. — invoked by `docs/engineering/JEV_HEADER_MAPPING.md` |
| `lifecycle_test_results.json` | data | captured output of an old lifecycle run; named in `scripts/check_trust_safety_copy.py`; archive candidate once that reference is dropped |
| `lint_response_models.py` | manual | manual lint: every FastAPI route declares `response_model`; candidate for CI (WI-03 follow-up) |
| `okr_pilots_ingesting_weekly.sql` | used | okr_pilots_ingesting_weekly.sql — invoked by `docs/runbooks/design_partner_funnel_operating_rhythm.md`, `docs/runbooks/first_pilot_session.md` |
| `orphan_migrations_allowlist.txt` | data | allowlist read by `scripts/check_orphan_migrations.py` (backend-ci) |
| `phone_test_quickstart.sh` | manual | run the published quickstart curl against prod to catch docs/contract drift; companion to `scripts/smoke_test_ingest.sh` |
| `qa_health_summary.py` | used | Build a redacted QA health dashboard artifact from CI test outputs. — invoked by `.github/workflows/qa-health.yml` |
| `render_ingestion_ignores.py` | used | Render ``--ignore=<path>`` flags for the ingestion suite-runs gate. — invoked by `.github/workflows/backend-ci.yml` |
| `run-migrations.sh` | used | run-migrations.sh — Idempotent Alembic migration runner with distributed lock — invoked by `.github/workflows/backend-ci.yml`, `.github/workflows/security.yml` |
| `run-performance-baseline.sh` | used | Performance Baseline Test Script — invoked by `docs/operations/performance-baseline.md` |
| `run_verification.sh` | archive candidate | ad-hoc verification runner with no documented procedure |
| `scale_benchmark.py` | archive candidate | 42-line tenant onboarding benchmark, no caller |
| `schema_parity_audit.py` | used | Schema parity audit (WS-2c) — fresh-DB `alembic upgrade head` ≡ expected schema. — invoked by `.github/workflows/backend-ci.yml`, `README.md` |
| `seed_agent_review_demo.py` | manual | manual: seed synthetic agent-review artifacts for a demo (tested in `tests/scripts/`) |
| `seed_demo.js` | used | seeds the demo tenant via the Admin API; named by `tests/test_e2e_fda_request.py` and `docs/persistence/ws1d-retirement-plan.md` |
| `seed_demo_data.py` | manual | manual: seed demo tenants and events into a local stack |
| `seed_passwordless_e2e_user.py` | used | Seed the local Playwright passwordless auth user. — invoked by `.github/workflows/frontend-ci.yml`, `.github/workflows/pr-gate.yml` |
| `seed_phase2b_key.py` | used | deprecated by its own docstring (use `scripts/create_test_api_key.py`), but `tests/scripts/test_seed_phase2b_key_masking.py` exercises its masking, so it stays (PRD WI-08 requirement 4) |
| `seed_v1_data.py` | used | payload = {"text": content, "source_url": unique_url, "source_system": "seed_script", "ver — invoked by `scripts/run_verification.sh` |
| `sentinel-backfill.py` | archive candidate | one-off backfill of closing-PR references for closed issues |
| `setup_dev.sh` | used | RegEngine Local Development Setup Script — invoked by `scripts/ci/supply_chain_baseline.json`, `scripts/install_pkgs.sh` |
| `setup_e2e_postgres.py` | used | Migrate the isolated local Playwright database before starting its servers. — invoked by `.github/workflows/frontend-ci.yml` |
| `setup_production.sh` | archive candidate | superseded by `docs/operations/PRODUCTION_DEPLOYMENT.md` and Railway config |
| `smoke_test_ingest.sh` | used | Smoke test for /v1/ingest/* endpoints. — invoked by `docs/runbooks/r2_provisioning.md` |
| `start-e2e-backend.sh` | used | start-e2e-backend.sh — invoked by `.github/workflows/frontend-ci.yml`, `.github/workflows/pr-gate.yml` |
| `start-fsma.sh` | used | FSMA-only runtime: keep local stack small during pilot work. — invoked by `scripts/start-stack.sh` |
| `start-stack.sh` | used | RegEngine Stack Startup Script — invoked by `docs/operations/OPERATIONS.md` |
| `stop-fsma.sh` | used | Shut down FSMA-only runtime. — invoked by `scripts/stop-stack.sh` |
| `stop-stack.sh` | used | RegEngine Stack Shutdown Script — invoked by `docs/operations/OPERATIONS.md` |
| `stress_test.py` | used | RegEngine Massive Stress Test — invoked by `docs/engineering/security-findings-2026-09-10/README.md`, `docs/engineering/security-findings-2026-09-10/dispositions.json` |
| `summon_agent.py` | used | RegEngine agent prompt helper. — invoked by `.github/workflows/legacy-code-scan.yml` |
| `test-all.sh` | used | RegEngine Full Test Suite Runner — invoked by `docs/engineering/TESTING_REQUIREMENTS.md` |
| `test_connectors.sh` | archive candidate | 10-line connector smoke with no documented procedure |
| `test_fsma_endpoints.js` | archive candidate | targets the retired graph service on port 8200; superseded by `tests/` FSMA endpoint suites |
| `test_id_003.sh` | archive candidate | hard-codes a demo tenant id; superseded by `scripts/regctl/` |
| `trust_safety_copy_allowlist.txt` | data | allowlist read by `scripts/check_trust_safety_copy.py` (frontend-ci, pr-gate) |
| `validate_data_integrity.py` | manual | manual: after a `scripts/chaos/` run, validate data integrity |
| `validate_env.py` | manual | manual: validate a `.env` against the startup contract (#533) |
| `validate_release_evidence.py` | used | Validate sanitized, deployment-bound security release evidence. — invoked by `.github/workflows/backend-ci.yml` |
| `verify-health.sh` | used | RegEngine Health Verification Script — invoked by `docs/operations/OPERATIONS.md` |
| `verify_canonical_parity_live.py` | retire with WI-12 | retire with WI-12: live dual-write parity verifier (#1335) |
| `verify_ciam_models.py` | archive candidate | 28-line import check for retired CIAM models |
| `verify_compliance_lineage.py` | used | Configuration — invoked by `.github/workflows/backend-ci.yml` |
| `verify_fda_export.py` | archive candidate | ad-hoc check superseded by `tests/` FDA export suites |
| `verify_fsma_only.py` | archive candidate | one-off check that non-FSMA vertical stubs were deleted (done) |
| `verify_inflow_to_regengine_e2e.py` | used | Hard-fail local Inflow-to-RegEngine evidence proof. — invoked by `README.md`, `docs/runbooks/inflow_workbench_design_partner_demo.md` |
| `verify_live_freshness.py` | used | verify_live_freshness.py — invoked by `scripts/run_verification.sh` |
| `verify_production_readiness.py` | manual | manual: release-day readiness verification |
| `workflow_inventory.txt` | data | the committed workflow inventory read by `scripts/check_workflow_inventory.py` (supply-chain, inflow-contract-ci) |

## Subdirectories

| Directory | Purpose |
|---|---|
| `scripts/chaos/` | chaos and resilience drills (see its README or headers); results feed `format_chaos_results.py` |
| `scripts/ci/` | helpers invoked by workflows under `.github/workflows/` |
| `scripts/copy-lint/` | the SEL-452 copy gate (`copy-gate.yml`, `copy-lint.yml`) |
| `scripts/fixtures/` | fixture files consumed by `tests/scripts/` (for example the RLS fail-open cases) |
| `scripts/jev_lab/` | Jev Lab: `venv/bin/python scripts/jev_lab --help` (see `docs/engineering/JEV_LAB.md`) |
| `scripts/railway/` | Railway bootstrap and staging helpers referenced by `docs/operations/` |
| `scripts/regctl/` | tenant management CLI (`python scripts/regctl/tenant.py --help`) |
| `scripts/scheduler/` | standalone scheduler entrypoints; production runs the embedded scheduler instead (`ASYNC_PROCESSES.md`) |
| `scripts/security/` | release-gate and scanning helpers referenced by `security.yml` and `docs/security/` |
| `scripts/test/` | test database bootstrap SQL used by `docker-compose.dev.yml` and CI |
| `scripts/utilities/` | local diagnostics; none is referenced by CI or a runbook |

Counts on 2026-10-30: 60 used, 4 data, 21 manual/one-time/retire, 14 archive candidates.
