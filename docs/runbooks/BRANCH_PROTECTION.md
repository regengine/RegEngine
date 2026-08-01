# Branch protection — required contexts and the rules around them

Last verified: 2026-08-01 against the live `main` protection settings
(`gh api repos/regengine/RegEngine/branches/main/protection`) and
`.github/workflows/`. The eight required contexts and strict mode match
the table below and `scripts/workflow_inventory.txt` exactly; see the
`enforce_admins` caveat under "No admin-override merges".

## Required contexts

`main` requires these eight status-check contexts, with **strict** mode on
(a PR must be up to date with `main` before merging):

| Required context | Emitted by | Workflow file |
| --- | --- | --- |
| `CI Status Gate` | job `ci-status-gate` | `.github/workflows/pr-gate.yml` |
| `Contract Status Gate` | job `contract-status-gate` | `.github/workflows/inflow-contract-ci.yml` |
| `Privileged Workflow Tool Pinning` | job `workflow-tool-pinning` | `.github/workflows/security.yml` |
| `Secrets Scan (gitleaks)` | job `secrets` | `.github/workflows/security.yml` |
| `Secrets Audit (detect-secrets)` | job `detect-secrets` | `.github/workflows/security.yml` |
| `Browser Storage PII Guard` | job `browser-storage-pii` | `.github/workflows/security.yml` |
| `SAST (Semgrep)` | job `sast` | `.github/workflows/security.yml` |
| `Dependency Audit` | job `deps` | `.github/workflows/security.yml` |

A context is a **bare string**. GitHub does not know which workflow is
supposed to emit it and will not warn you when nothing does — it just
shows "Expected — waiting for status to be reported" forever.

`scripts/check_workflow_inventory.py` is the guard that closes that gap.
It reads `scripts/workflow_inventory.txt` (the checked-in mirror of these
settings) and fails CI if a required context is unemitted or unreachable,
or if the workflow file set drifts. It runs as `PR Gate: Workflow
Contract`, which feeds the `CI Status Gate` aggregate — so breaking the
contract fails the one required check.

## What the shim is for

`backend-ci.yml` and `frontend-ci.yml` are path-filtered on
`pull_request`. A frontend-only PR never produces `Backend CI Status
Gate`, and a backend-only PR never produces `Frontend CI Status Gate`, so
requiring those job names directly would leave cross-area PRs waiting
forever on a check that will never post.

`pr-gate.yml` is the shim. It is **not** path-filtered, so it runs on
every PR, and for each area it either:

* passes vacuously when that area's paths were not touched (the real
  workflow legitimately did not run), or
* waits for and mirrors that area's real gate when the paths were
  touched.

Its `ci-status-gate` job aggregates both area jobs plus the workflow
contract guard and emits the single required `CI Status Gate` context.
The per-area jobs (`PR Gate: Backend`, `PR Gate: Frontend`) and the
contract job are **not** required contexts — they exist for diagnosis.

The path lists inside `pr-gate.yml` must mirror the `pull_request: paths:`
blocks in `backend-ci.yml` and `frontend-ci.yml`. Drift is biased safe:
over-detection makes the shim wait for a real gate that never appears and
time out (spurious block, recoverable), while the dangerous direction —
passing an area whose real gate actually failed — only happens on
under-detection.

## Rules

### No admin-override merges

If a required check cannot pass, fix the check or fix branch protection —
do not merge past it.

> **Caveat (verified 2026-08-01): this rule is currently POLICY, not a
> setting.** The live protection has `"enforce_admins": {"enabled": false}`
> (from `gh api repos/regengine/RegEngine/branches/main/protection`:
> `{"strict": true, "contexts": [the 8 above], "enforce_admins": false,
> "required_approving_review_count": 1, "allow_force_pushes": false,
> "allow_deletions": false}`), so an admin CAN still merge past a red
> required check. Turning `enforce_admins` on in the settings UI would
> make the rule mechanical — that is an operator decision, deliberately
> not changed by the verification pass that recorded this.
>
> **Decision (2026-08-01): stays OFF for now.** The protection also
> requires 1 approving review, and PR authors cannot approve their own
> PRs — with a single maintainer, every merge necessarily uses the admin
> path to satisfy the review requirement (with green checks). Enabling
> `enforce_admins` today would therefore hard-block ALL merges, not just
> overrides of red checks. Revisit when a second reviewer exists, or if
> the review requirement is dropped to 0 (then `enforce_admins` can be
> enabled and the no-override rule becomes fully mechanical).

Two incidents came from overrides:

* **The phantom context.** From #2551 until 2026-07-31, `CI Status Gate`
  was required but emitted by *nothing* (the real jobs are named `Backend
  CI Status Gate` and `Frontend CI Status Gate`). Every PR in that window
  was merged via admin override, which also silenced every other required
  check on those merges.
* **The unreachable context.** `security.yml` carried
  `paths-ignore: ['**/*.md', 'docs/**', ...]` on `pull_request`, so a
  docs-only PR never produced six of the eight required contexts and was
  structurally unmergeable without an override. That filter is now
  removed from the `pull_request` trigger (the `push` trigger keeps it —
  main-branch runs do not gate merges), which also means secret scanning
  now covers markdown and `docs/`, where secrets actually do get pasted.

Both classes now fail CI loudly via the contract guard instead of being
discovered at merge time.

### One migration-bearing PR on `main` at a time

Alembic's revision DAG must have exactly one head. Three head-forks
landed inside 48 hours (v099/v100, v101/v102, and the v101/v102 → v103
reparent) because two migration-bearing PRs were open simultaneously:
each was single-headed against the `main` it branched from, and the fork
only existed after both merged.

Strict mode helps — the second PR must update to the merged `main`
before merging, at which point `scripts/check_alembic_revisions.py` sees
both heads and fails. Do not bypass that failure by merging the fork and
"fixing it after"; rebase the second migration onto the new head, or use
`alembic merge -m 'merge heads' <head1> <head2>`.

Coverage: the MULTIPLE HEADS check in
`scripts/check_alembic_revisions.py` (runs as the `Alembic revision ID
guard` job in `backend-ci.yml`), with proof fixtures in
`tests/scripts/test_check_alembic_revisions.py::TestMultipleHeadsGuard`
— including a test that runs the guard against the live
`alembic/versions/` tree, so a merged fork fails the test suite as well
as the CI script.

### Changing branch protection

Branch protection lives in the GitHub settings UI; it cannot be changed
from the repository. When you change it:

1. Update `[required-contexts]` in `scripts/workflow_inventory.txt` in
   the same PR.
2. Update the table at the top of this runbook.
3. Confirm every new required context is emitted by a job in a workflow
   that runs on **every** pull request — a `pull_request:` trigger with
   no `paths:` / `paths-ignore:` filter. The guard enforces this, but
   knowing the rule saves a round-trip.

Renaming a job that emits a required context, deleting its workflow, or
adding a path filter to it all break merging for every PR until branch
protection is edited to match. The guard fails the PR that would cause
it, which is the point.

### Verifying the live settings

```bash
gh api repos/regengine/RegEngine/branches/main/protection --jq '.required_status_checks.contexts'
```

Compare against `[required-contexts]` in `scripts/workflow_inventory.txt`.
The guard cannot read GitHub settings from CI (it would need a token with
admin scope), so the inventory is a hand-maintained mirror — this command
is how you check the mirror is still honest.
