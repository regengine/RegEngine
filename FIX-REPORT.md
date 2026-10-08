# FIX-REPORT: PR #3236 (merge 9c171b474041ca0725c51e0995dbfb26ad59a483)

Scope: confirmed CONCERN and BLOCKER findings for PR #3236 from the six
re-rv-3236 angle reports plus the angle and area leads that mention #3236.
Out of scope per orders (noted, not fixed): suspended-tenant deny on live
auth, tenant-scope gate failure, 7 xfail cross-tenant leaks.

## Findings

| # | Source report | Severity | Finding | Status | Reason |
|---|---|---|---|---|---|
| 1 | re-rv-3236-blast, re-rv-3236-correct, re-rv-lead-blast, re-rv-lead-correct #8, re-rv-lead-security (3236b part) | High | `_get_commit_checks_state` returns failure for completed runs with skipped or neutral conclusions, so a normal green PR (this repo skips workflow jobs on PRs) never auto-merges | FIXED AND TESTED | `GREEN_CONCLUSIONS = {success, skipped, neutral}` in `github_integration.py`; docstring and `merge_pr` doc updated; old test flipped to assert green |
| 2 | re-rv-3236-blast Medium, re-rv-lead-blast Medium | Medium | `sweep`/`troubleshoot`/CLI `solve` drop `human_approved`; `solve` returns completed while the PR step was blocked, sweep logs look successful | FIXED AND TESTED | `sweep` and `troubleshoot` accept and forward `human_approved`; `run`/`solve`/`troubleshoot` CLI gained `--approve-pr` forwarded into `solve`; blocked auto-fix now appends an error and sets `completed_with_warnings`; sweep logs errors per service |
| 3 | re-rv-3236-security High 1, re-rv-lead-security 3236a | High | Coder writes `.git/config` and `.github/workflows/*`; auto-fix runs `git add .` with no config overrides, so a planted hook, fsmonitor, sshCommand, or pushed workflow executes | FIXED AND TESTED | `is_sensitive_write_path` deny in `CoderAgent.act`; explicit `_stageable_paths` staging (empty list pushes nothing); every git call wrapped in `_git` with `core.fsmonitor=`, `core.hooksPath=/dev/null`, `core.sshCommand=ssh -oBatchMode=yes` |
| 4 | re-rv-3236-security Medium 4, re-rv-lead-security 3236d | Medium | Standing approval env restores auto-push silently; task text copied into PR body can carry logged secrets | FIXED AND TESTED | Approval forwarding (row 2) plus `redact_for_pr_body` on task and file JSON in PR body; blocked runs now visible as `completed_with_warnings` |
| 5 | re-rv-3236-security Medium 3, re-rv-lead-security 3236c | Medium | One `--approve-merges` covers every open PR; model reads attacker-controlled comments; one GitHub error aborts the whole scan | FIXED AND TESTED | Janitor loop wrapped per PR (error recorded as hold, scan continues); new optional `--prs` allowlist limits scope; approval gate itself covered by CLI tests |
| 6 | re-rv-3236-tests Medium, re-rv-lead-tests | Medium | `--approve-merges` flag untested; deleting the check stays green | FIXED AND TESTED | Four janitor CLI tests: no merge without flag, merge with flag, per-PR error continues, `--prs` filter limits scope |
| 7 | re-rv-3236-blast Low | Low | One GitHub error aborts the whole open-PR scan | FIXED AND TESTED | Same per-PR try as row 5 (trivial) |
| 8 | re-rv-3236-security Low 5 | Low | `is_path_within_base` compares unresolved paths; a future caller passing `..` reopens the bypass | FIXED AND TESTED | Helper resolves both sides, fails closed on error (trivial) |
| 9 | re-rv-3236-tests Low | Low | Approval env var path untested | FIXED AND TESTED | New test: env var true without flag still runs push and PR path (trivial) |
| 10 | re-rv-3236-security High 2 remainder, re-rv-lead-security 3236b | High | No required check-name allowlist; legacy status success with empty check list returns success; `get_check_runs` uses default filter | BLOCKED | Needs Christopher decision (see below). No required-check config exists anywhere; status-only success is legitimate for status-only repos, so blocking it would break those merges |
| 11 | re-rv-3236-security Medium 3 remainder | Medium | Ignore issue comments as verdicts; code-only merge decision; bot-login restriction | BLOCKED | Needs Christopher decision (see below). Changes janitor UX and needs a known bot login |
| 12 | re-rv-3236-security Low 6 | Low | `require_green_checks=False` lets any in-process caller skip the gate | Listed, not fixed | Tested public API; the only production caller uses the default True. Removal would break the existing bypass test and callers that pre-checked. Needs Christopher decision to remove |
| 13 | re-rv-3236-tests Low | Low | PyGithub signature test skips (library not installed); race test rejects in fake, not via GitHub | Listed, not fixed | Shared venv lacks PyGithub and must not be touched; GitHub-side race cannot be proven offline. Both limits are stated in the test file |

Skipped, could not confirm: none. Every finding above was confirmed by
reading the cited code before fixing.

## Test commands and results

New code, from the worktree root:

`.venv/bin/python -m pytest tests/swarm/test_swarm_guards.py -q --no-cov`
Result: 39 passed, 1 skipped (PyGithub not installed; pre-existing skip).

`.venv/bin/python -m pytest tests/swarm -q --no-cov`
Result: 39 passed, 1 skipped (same file; only swarm suite in that dir).

`.venv/bin/python -m ruff check` on the six touched files
Result: All checks passed.

`.venv/bin/python -m ruff format --check` on the six touched files
Result: clean (two files reformatted to match, diff confined to edited lines).

`.venv/bin/python scripts/security/scan_tenant_scope.py`
Result: 0 findings mention `regengine/swarm` or `compliance_sweep`. Remaining
scan output is pre-existing `services/graph` items owned by other tasks.

Fail without fix proof: the new and updated tests were run against a mirror
in /tmp/verify_old holding HEAD versions of the four swarm source files plus
the HEAD compliance script (read-only `git show`, no worktree files touched).
Result there: 13 failed, 26 passed, 1 skipped. The 13 failures are exactly the
fix-covering tests (green skipped/neutral, explicit staging with config
overrides, no-stageable-files block, sensitive-path staging, warnings status
on blocked solve, unresolved traversal, git/workflow write blocks, redaction,
sweep and troubleshoot forwarding, janitor error continuation, prs filter,
compliance approval forwarding). Three characterization tests pass on both
versions by design (env var approval path, janitor flag on/off basis).

## Needs Christopher decision

1. Required-check allowlist for auto-merge: which check names must be present
   and green, where that list lives, and whether legacy-status success with an
   empty check-run list should block. No config exists today.
2. Janitor merge authority: keep model JSON decision with optional `--prs`,
   or move to code-only decision and ignore comments, possibly restricted to a
   fixed bot login (name the login).
3. Approval model: keep `REGENGINE_SWARM_AUTO_PR_APPROVED` env as approval and
   `REGENGINE_CI_AUTO_FIX=true` inside `compliance_sweep.py` (kept, fail-closed
   otherwise), or require per-run `--approve-pr` only. Also confirm the split
   between `--approve-merges` (janitor merges) and `--approve-pr` (auto-fix PR
   creation) is the intended UX.
4. `require_green_checks=False`: keep the tested escape hatch or remove it so
   no in-process caller can skip the CI gate.
