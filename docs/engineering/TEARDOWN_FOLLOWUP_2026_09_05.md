# Teardown follow-up — 2026-09-05

Scope: narrow follow-ups to the repository teardown, based on commit
`dfd900699289c5574edcc1179d57878f49f6c286`. No deployed schema, authentication
behavior, public API, or production configuration was changed.

## Changes

- Preserved the pre-existing untracked revision `942f92c88738` outside
  `alembic/versions/`. It introduced a second head alongside `c6a120b4e901`.
  The preserved bytes have SHA-256
  `21fbbab431d97327c99199f697a26543971d135b6e503d3049615dddd3249158`.
  The tracked 81-file graph already has one head and needs no new migration.
- Updated stale tenant-guard expectations for caller-owned API-key forwarding.
  Added route tests for cookie/header/alias forwarding, upstream 401/409
  propagation, missing credentials, and absence of ambient server-key substitution.
- Added backend tests using real `require_api_key` and `resolve_tenant_context`
  dependencies: invalid/expired/revoked credentials, cross-tenant reads/writes,
  and successful isolated reads. Key storage is in-memory and snapshot storage
  is SQLite in these API tests; PostgreSQL RLS is verified separately below.
- Removed the duplicate frontend dependency installation and Vitest invocation
  from QA Pipeline. Frontend CI retains its coverage-enforcing unit suite. QA
  retains its Node built-in sample/security checks and existing job names.
- Updated only the existing secret-baseline entry's line number; no new
  secret finding was suppressed.

## Local verification

Commands run from the repository root unless noted:

- `.venv/bin/python -m pytest services/compliance/tests/test_snapshots_router.py tests/scripts/test_check_alembic_revisions.py tests/scripts/test_check_rls_fallback.py services/shared/tests/test_tenant_context_set_guc.py tests/shared/test_canonical_persistence_tenant_context.py tests/shared/test_task_queue_hardening.py services/shared/tests/test_rules_deadletter_2709.py tests/security/test_audit_integrity.py -x --no-cov -o addopts= -q --tb=short`: **133 passed**.
- In `frontend/`, `npm run test:run --` for `enforce-tenant-match`,
  `compliance-proxy-auth-boundary`, `compliance-snapshots-proxy`,
  `proxy-sanitization`, `ingestion-proxy-auth`, `proxy-ip-attestation`, and
  `proxy-csrf`: **110 passed**.
- Disposable local HTTP smoke: real Next.js snapshot route handler -> FastAPI
  snapshot router -> SQLite, with the real auth/tenant dependencies and local
  test keys: **4 passed**, covering cookie/header/alias own-tenant success,
  cross-tenant rejection, and invalid-key rejection. This is not a deployed
  browser session, the complete Next.js middleware stack, or production key storage.
- Disposable Homebrew PostgreSQL **16.14**, with `REGENGINE_REQUIRE_DB=1`:
  `tests/migrations/test_rls_coverage.py`: **8 passed**;
  `tests/migrations/test_seeded_mid_chain_upgrade.py` with Supabase-style
  client roles: **4 passed**.
- Against the migrated scratch database, with `PGOPTIONS='-c timezone=UTC'`:
  `tests/invariants/test_dual_write_parity.py`,
  `tests/invariants/test_fda_export_v1_golden.py`,
  `tests/invariants/test_chain_verify_golden.py`,
  `tests/shared/test_chain_verify_dual_write_live.py`, and
  `services/shared/tests/test_rls_enforcement_live.py`: **27 passed**.
- `alembic check`: no new upgrade operations. `scripts/schema_parity_audit.py
  check`: **116 tables match**. The existing contract omits foreign-key entries,
  so this result does not establish foreign-key parity.
- Targeted ESLint, TypeScript `tsc --noEmit --incremental false`, Ruff,
  `actionlint .github/workflows/qa-pipeline.yml`, and workflow inventory passed.
  The retained QA scripts passed 31 sample checks and 25 static security checks.

The first golden-chain run used the local cluster's non-UTC timezone and failed
two assertions because timestamp serialization changed the recomputed hash.
The UTC rerun matches the live database timezone and passed. Non-UTC chain
verification remains a known limitation; this change does not repair it.

## Live findings and release blockers

Read-only Supabase queries against project `magbeerafyxmyuqmbfgv` on 2026-09-05:

- `public.alembic_version` is **`267d8053ced5` (v079)**.
- RLS is disabled and not forced on `fsma.cte_events`,
  `fsma.traceability_events`, `fsma.hash_chain`, and `fsma.rule_evaluations`.
- RLS is enabled and forced on `public.audit_logs` and `public.audit_log_buffer`.
- Database version is PostgreSQL **17.6** and its timezone is UTC.

These are live catalog observations, not proof of a particular unauthorized
access path. The local PostgreSQL 16 checks do not prove that the deployed
PostgreSQL 17 schema, grants, migration-owner credential, or runtime roles are
ready for cutover. Rehearse that exact deployed state and verify backups and
runtime-role separation before running the supported migration runner.

[Frontend CI run 33996665060](https://github.com/regengine/RegEngine/actions/runs/33996665060)
and PR Gate annotations report that jobs could not start because of an account
billing lock. The organization billing UI confirms failed payment authorization.
The account owner must resolve that authorization, then rerun checks on the
intended release SHA. No payment, budget change, or plan change was performed.

Do not squash revisions still needed by the v079 environment or retire legacy
writes from these local results. The existing WS-1d gates still require live
reconciliation, export parity, a verified soak, and all direct legacy writers
to be cut over before legacy tables become read-only.
