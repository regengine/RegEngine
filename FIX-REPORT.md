# FIX-REPORT: PR #3223 seed scripts (localhost default, TLS)

Merge commit 0345054b69c546392959b61a5633391cc769e666, reviewed on origin/main e854dadc.
Reports read: all six re-rv-3223 angles (blast, correct, ops, security, tenant, tests),
plus lead summaries mentioning #3223 (blast, ops, security, tenant, tests, area-infra,
int-secret-scan). Correct, tenant, blast, and ops angles returned OK with no findings
above low. No queries were touched, so scripts/security/scan_tenant_scope.py does not apply.

## Findings

| Source report | Severity | Finding | Status | Reason |
|---|---|---|---|---|
| re-rv-3223-tests (lead-tests item 4, area-infra high) | High | tests/scripts/test_seed_scripts_no_prod_default.py runs in no required gate: backend-ci operator-tooling step names only two other files, test-suite-check is non-required and its paths omit scripts/** | FIXED AND TESTED | Added the file to the blocking operator-tooling pytest command in .github/workflows/backend-ci.yml with an explanatory comment |
| re-rv-3223-tests (lead-tests medium note) | Medium | Founder --check path builds its own TLS context but the test passed an empty seen dict, asserted only rc != 0 and stdout text, so a downgrade confined to check_health stayed green | FIXED AND TESTED | Test now passes seen through, asserts rc == 1, and calls _assert_verifying_context |
| re-rv-3223-tests | Low | test_no_tls_downgrade_path substring scan misses check_hostname=False and ssl._create_unverified_context() | FIXED AND TESTED | Trivial test-only hardening: scan now also rejects verify_mode, check_hostname=False, and _create_unverified_context |
| re-rv-3223-tests | Low | Refusal tested only with the Railway URL, so a host-specific special case would pass | FIXED AND TESTED | Trivial test-only hardening: refusal and allow tests parametrized over the Railway URL plus https://example.com |
| re-rv-3223-security | Low | Redirects copy X-RegEngine-API-Key (and X-Tenant-ID, X-Webhook-Signature) to the redirect host, which the allowlist never saw | Not fixed, listed | Runtime behavior change (a no-redirect or same-host opener touches all four request paths in both scripts and could break legitimate proxy redirects). Needs Christopher decision, see below |
| re-rv-3223-security | Low | --allow-production accepts cleartext http for non-local hosts | Not fixed, listed | Runtime behavior change: requiring https would break seeding to internal http staging targets. Needs Christopher decision, see below |

## Test commands and results

1. `~/metacode/fleet/heavy .venv/bin/pytest tests/scripts/test_seed_scripts_no_prod_default.py -v --no-cov -o "testpaths=tests"`
   Result: 28 passed in 2.58s.
2. `~/metacode/fleet/heavy .venv/bin/pytest tests/scripts/test_bootstrap_staging_database.py tests/scripts/test_v126_operator_guidance.py tests/scripts/test_seed_scripts_no_prod_default.py --collect-only -q --no-cov -o "testpaths=tests"`
   Result: all three files collect (95 plus 3 plus 28 tests), so the edited backend-ci step references valid files.
3. YAML check: `python -c "import yaml; yaml.safe_load(open('.github/workflows/backend-ci.yml'))"` prints backend-ci.yml YAML OK.
4. Lint: `ruff check` on the test file and both seed scripts passes; `ruff format --check` on the test file passes.
5. Fail-without-fix probes (scratch scripts in /tmp, not committed):
   - /tmp/probe_3223_check.py replaces create_ssl_context with ssl._create_unverified_context() and runs the --check path. Output: new strengthened test FAILS as intended (downgrade caught); old test logic would PASS (rc != 0 with "tls" printed), confirming the old test missed this downgrade class.
   - /tmp/probe_3223_lows.py runs a hypothetical Railway-only resolver and a downgraded source snippet. Output: old single-host test would PASS while the new parametrized test FAILS as intended; old substring scan passes on the downgraded source while the new scan rejects it; both real scripts refuse https://example.com without the flag.

## Notes needing Christopher decision

1. Redirect header copying (security low): fix by refusing cross-host redirects or using a no-redirect opener in both seed scripts. Small change, but it alters runtime behavior. Recommend doing it, but it is a behavior call.
2. Cleartext http with --allow-production (security low): fix by requiring https for non-local targets. This would block seeding to internal http endpoints, so confirm no workflow depends on that before enforcing.
3. Pre-existing non-regressions noted in the reports, left untouched: founder --check returns 0 on non-TLS health failures, and the demo script returns 0 when events are rejected. Both match the pre-PR behavior.
4. Runbook check (from ops/correct angles): confirm no runbook outside this repo still invokes the seed scripts expecting the old production default of https://regengine-production.up.railway.app.
5. Out of scope per the task order and untouched here: the suspended-tenant deny on live auth, the tenant-scope gate failure, and the 7 xfail cross-tenant leaks.

## Decision applied (Decision 2, PR 3223, Oct 8 2026): https required, no redirect following

Status: FIXED AND TESTED

Christopher decided: 1) every seed and helper script touched by 3223 must refuse
plain http for any non-local host (localhost and 127.0.0.1 may stay http for
local dev), including with --allow-production; 2) on any redirect, do not
forward X-RegEngine-API-Key, X-Tenant-ID or X-Webhook-Signature, implemented
as never following redirects and failing with a clear error.

What changed (PR 3223 touched exactly two scripts, both fixed identically):
- scripts/seed_demo_ctes.py and scripts/seed_founder_demo_ctes.py: new
  require_https_for_non_local() called at the end of resolve_base(), so plain
  http to a non-local host raises UnsafeTargetError even with
  --allow-production. http stays allowed for localhost, 127.0.0.1 and ::1
  (all loopback; ::1 kept alongside the two named hosts because it is the
  same machine).
- Both scripts: new urlopen_no_redirect() used on all four request paths
  (demo post_events; founder check_health, status, post_batch). It builds an
  explicit OpenerDirector whose chain contains _NoFollowRedirect instead of
  the default redirect handler. Any 301/302/303/307/308 raises
  RedirectRefusedError (an HTTPError subclass) with a message naming the
  redirect target, and each caller catches it first to print a clear error
  and return 1 (founder check_health now returns 1 on redirect while keeping
  its pre-existing 0 on other non-TLS health failures).
- tests/scripts/test_seed_scripts_no_prod_default.py: 24 new tests. http
  refusal via CLI, env var and direct resolve_base with the flag (both
  scripts, two non-local http URLs), local http still allowed with and
  without the flag, both mains refusing http with the flag, redirect
  handler unit tests, and loopback-server tests proving post_events, status,
  check_health and post_batch never touch the redirect target while the
  redirecting server demonstrably received the credentials.

Exact commands and pass/fail lines:
- `~/metacode/fleet/heavy .venv/bin/pytest tests/scripts/test_seed_scripts_no_prod_default.py -v --no-cov -o "testpaths=tests"`: 52 passed in 5.35s (28 pre-existing plus 24 new).
- `.venv/bin/ruff check` on both scripts plus the test file: All checks passed. `ruff format --check` on the same three files: 3 files already formatted.
- Fail-without-fix probe `/tmp/dec2_old/probe_old.py` loading HEAD versions of both scripts: old resolve_base ALLOWED http://example.com with the flag in both scripts; old post_events returned rc 0 while the redirect target received the request with the API key; old post_batch followed the redirect and the target received the key. All four new-test behaviors fail on old code and pass on new code.
- Redirect leak proof `/tmp/probe_leak.py` on repo Python 3.11: default urlopen followed a 302 and delivered X-RegEngine-API-Key, X-Tenant-ID and X-Webhook-Signature to the redirect target; the explicit no-follow opener raised and the target got zero requests.
- Repo reference check: no runbook, doc, shell script, CI file or other Python file in this repo invokes either seed script, so nothing in-repo depends on http seeding or redirect following.

Anything that must happen before a deploy:
- Confirm no workflow OUTSIDE this repo (runbooks, dashboards, saved shell history) seeds a staging target over plain http or behind a redirecting proxy or ingress path. After this change such targets fail closed: http staging targets need an https endpoint, and redirecting URLs need the final direct URL. This is the intended behavior per the decision, but it can break a previously working seed command.
- No migration needed (no schema change, additive-only rule respected: nothing added).
