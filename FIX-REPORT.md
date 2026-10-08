# FIX-REPORT: PR #3231 (merge a8ca551d) CONCERN and BLOCKER findings

Base: origin/main e854dadc. Reports read: all six re-rv-3231-<angle> SUMMARY.md
plus REPORT.md for correct and blast, and every angle, area and integration
lead that mentions #3231. Out of scope items (suspended-tenant deny on live
auth, tenant-scope gate failure, 7 xfail cross-tenant leaks) do not arise
from PR #3231; nothing in this diff touches request paths, so they are
noted here only as untouched.

## Findings

| # | Source report | Severity | Status | Reason / note |
|---|---|---|---|---|
| 1 | correct, blast, lead-correct #5, lead-blast 3231a, area-infra H1: default `--scopes epcis.ingest,csv.ingest` matches no `require_permission` name, README mint flow 403s on `webhooks.ingest` routes | High | FIXED AND TESTED | Default is now `webhooks.ingest`, the permission the webhook and CSV routes check (`webhook_router_v2/routes.py:107`, `csv_templates.py:1370`). `test_api_key_default_scope_passes_ingest_permissions` asserts `has_permission` against the real matcher. Old default fails that check (proven in /tmp/fx3231/old_behavior.py). |
| 2 | security, lead-security #5, area-infra M9: `?host=` / `?hostaddr=` query values bypass the loopback guard while SQLAlchemy passes them to the driver | High | FIXED AND TESTED | `diag_db.py`, `seed_chaos_data.py`, `verify_inflow_to_regengine_e2e.py` now collect authority host plus every `host`/`hostaddr` query value (comma-split) and refuse unless all are local. Refusal (fail closed) was chosen over rebuilding the engine from checked parts. New tests pin `?host=`, `?hostaddr=` and multi-host refusal with zero connect calls (pure unit checks, no socket opened). |
| 3 | ops, blast, lead-ops #7, lead-blast 3231b: R2 runbook probes localhost after the smoke default changed | High | FIXED AND TESTED | Runbook step 3 now sets `REGENGINE_API_BASE=https://regengine.co/api/ingestion` and passes `--allow-production`, and states a localhost pass does not count. The script header carries the same production example. Loopback passes print "Local endpoints functional (... only; not a production R2 check)" instead of "R2 wired". |
| 4 | tests, lead-tests #6, lead-ops #24: `test_prod_default_guards.py` runs in no required merge job | High | FIXED AND TESTED | Added to the `repo-root-suite` pytest list in `.github/workflows/backend-ci.yml` (that job already triggers on `scripts/**`). `test_guard_suite_runs_in_required_backend_ci` pins the membership. |
| 5 | security, tenant, lead-security 3231b, lead-tenant M4: `create_test_api_key.py` guard covers only Supabase substrings and `REGENGINE_ENV` | Medium | FIXED AND TESTED | `_guard_against_production` now also refuses any non-local `DATABASE_URL` (with the finding 2 query-host check) and any non-local `REDIS_URL`, unless `--allow-production`. Parametrized tests cover Railway, Neon, raw IP, and crafted query hosts with env unset. |
| 6 | tenant, lead-tenant M4: `_seed_billing_status` writes `trialing` to whatever `REDIS_URL` is set | Medium | FIXED AND TESTED | Takes `allow_production`, returns a SKIPPED note instead of writing when `REDIS_URL` is non-local without the flag. `_main` passes the flag through. Test pins the skip note. |
| 7 | tenant, lead-tenant M4: regctl create/delete have no production guard before schema create / `DROP SCHEMA CASCADE` | Medium | FIXED AND TESTED | `ensure_local_database` runs first in `create_tenant`, `delete_tenant` (and `reset_tenant` passes the flag through); CLI gains `--allow-production`. `click.confirmation_option` on delete is unchanged. Tests assert `SystemExit` before any write, proven to proceed on pre-fix code via /tmp/fx3231/old_regctl.py (HEAD file, stubbed side effects). |
| 8 | security, lead-security 3231c: `seed_lifecycle_test.py` follows 301/302/303 and resends `X-RegEngine-API-Key` to the redirect host | Medium | FIXED AND TESTED | `_NoRedirect` handler exits 2 instead of following, used by both `api_post` and `api_get`. Live two-server tests prove the second host receives nothing. Old `urlopen` behavior proven to leak (key resent, follow-up becomes GET) in /tmp/fx3231/redirect_old.py. |
| 9 | correct: guards refuse `.env.example` compose hostnames (`postgres`, `neo4j`) unless `--allow-production` | Medium | FIXED AND TESTED | Explicit `DEV_COMPOSE_HOSTS = {"postgres", "neo4j", "redis"}` allowlist (exactly the `.env.example` service names) added to all five Python guards. `test_compose_hostnames_count_as_local` pins it. Any other docker hostname still needs `--allow-production`; needs Chris sign-off (see decisions). |
| 10 | correct: smoke success text readable as a production R2 pass | Medium | FIXED AND TESTED | Covered in finding 3; loopback test now asserts exit 0 plus the local-only line and absence of the R2 line. |
| 11 | tests, lead-tests: guards tested as bare functions, dropping the `main` call stays green; `REGENGINE_ENV=production` on localhost untested | Medium | FIXED AND TESTED | Entrypoint tests call `main` / `_configure_environment` / `_main` with production URLs and production env on localhost, pinning exit code 2 (guard) so a seeding failure (exit 1) cannot masquerade as a refusal. |
| 12 | tests: `create_tenant` still prints the raw key against a "never print" header | Medium | FIXED AND TESTED | One-time display at creation is intentional (list masks afterward and the file is the durable copy), so the test module docstring now states that exception instead of claiming "never print". No behavior change. |
| 13 | security, correct: `.tenants.db` stays 0644 until next write; symlink-unsafe creation | Low | FIXED AND TESTED | Trivial: chmod 0600 before every read path; `O_NOFOLLOW` plus 0600-at-create for append and rewrite. Tests pin tighten-on-list and symlink refusal. |
| 14 | security: smoke curl may send the key to a configured proxy | Low | FIXED AND TESTED | Trivial: loopback probes pass `--noproxy '*'` via a `smoke_curl` wrapper; production path unchanged. Header text test pins `--noproxy`. |
| 15 | (found during fix) unquoted semicolon in the two multipart `probe` lines aborts the script under `set -u` before any RESULT line | Low | FIXED AND TESTED | Quoted the `-F` payload argument. The loopback test now asserts a full exit 0 run, which fails on the old lines. |
| 16 | tests: Railway/Neon URLs and the regctl delete path unasserted | Low | FIXED AND TESTED | Covered in findings 5 and 7. |
| 17 | tenant: diag probe inserts `is_sysadmin=true` with literal `hash` | Low | NOT FIXED, listed | Tenant lead kept this out of the confirmed list: no password verifier compares `password_hash`, so the row is not a working credential. Left untouched; flagging for Chris in case the probe should insert a non-admin row instead. |
| 18 | blast: any non-loopback host (incl. docker names) treated as production | Low | NOT FIXED, listed | Partially addressed by finding 9 for the documented compose names. Remaining docker hostnames still require `--allow-production` by design (fail closed). |

No BLOCKER or critical findings were reported for #3231 (security: "Critical: None").
No fix was backed out; every attempted fix held.

## Exact test commands and results

- `~/metacode/fleet/heavy .venv/bin/python -m pytest tests/scripts/test_prod_default_guards.py --no-cov -o testpaths=tests` then `tail -1`
  result: `80 passed in 9.32s` (final run; earlier runs: 78 passed, then 80 passed).
- `~/metacode/fleet/heavy .venv/bin/ruff check scripts/create_test_api_key.py scripts/seed_chaos_data.py scripts/seed_lifecycle_test.py scripts/regctl/tenant.py scripts/utilities/diag_db.py scripts/verify_inflow_to_regengine_e2e.py tests/scripts/test_prod_default_guards.py`
  result: `All checks passed!` (a later probe that wrongly included the `.sh` file reported 271 errors, all inside the shell script which ruff cannot parse; `bash -n` on the script passes).
- `bash -n scripts/smoke_test_ingest.sh` then a stub-curl render on localhost
  result: `RESULT: ... Local endpoints functional (http://localhost:8000 only; not a production R2 check).`, `rc=0`.
- Fail-without-fix proofs (scratch, kept under /tmp/fx3231, not committed):
  `/tmp/fx3231/old_behavior.py` confirms old default fails `has_permission`, old authority-only check calls the crafted URL local, old Supabase-only guard allows a Railway URL with env unset;
  `/tmp/fx3231/redirect_old.py` confirms plain `urlopen` delivers the API key to the redirect target;
  `/tmp/fx3231/old_regctl.py` (HEAD copy of `regctl/tenant.py` with stubbed side effects) confirms pre-fix `create_tenant` proceeds on a Railway `DATABASE_URL` with zero `ensure_local_database` references in the file.
- Not run: full suite (targeted file only, per fleet guidance); `scripts/security/scan_tenant_scope.py` (no SQL or Cypher touched); the two `*_pg.py` tests importing the inflow verifier (they call only `_configure_paths`, which is unchanged, and need a local Postgres that was not provisioned).

## Needs Chris decision

1. Runbook production base: step 3 uses `https://regengine.co/api/ingestion` (the pre-3231 script default). Confirm that is still the live ingest base, or name the current one.
2. Default key scope is now `webhooks.ingest` only. A general local key still needs `--scopes '*'` (documented in help). Confirm, or add `fda.export` to the default.
3. `postgres`, `neo4j`, `redis` now count as local without DNS proof. Confirm acceptable, or restrict to `REGENGINE_ENV=development`.
4. Diag probe still inserts an `is_sysadmin=true` row (finding 17). Confirm acceptable, or direct a non-admin probe row.
