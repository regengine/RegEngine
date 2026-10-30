# Plan: production deploys from a release branch (PROPOSED — not in effect)

Written 2026-10-28 from `.github/workflows/deploy.yml`, `railway.toml`,
`docs/runbooks/BRANCH_PROTECTION.md`, `docs/runbooks/MIGRATION_ROLLBACK.md`,
and `docs/operations/DISASTER_RECOVERY.md` section 7. Proposal only: no
workflow, Railway setting, or branch rule changes with this file.

## 1. Status

Until 2026-10-28, production deployed on every backend-relevant push to
`main`: `.github/workflows/deploy.yml` ("Deploy to Railway") ran on `push`
to `main` for the backend path list, and on `workflow_dispatch`, waited for
a green **Backend CI Status Gate** on that commit, then ran `railway up --ci`
against the production Railway service. That workflow is now disabled and
production deploys are manual; section 11 has the current process. Vercel
deploys the frontend separately.

Nothing changes until the founder approves this model and a later pull
request lands.

## 2. Why

On 10–11 October 2026, merges landed about once a minute. Production deployed
about 107 times in roughly seven hours.

One bad commit crashed every new container at boot (`SyntaxError`). Failed
candidates stacked up to about 80% of the 24 GB Railway memory limit named
in the `deploy.yml` header. Live traffic stayed on the last good deploy.
`railway.toml` kept the previous image: `/readiness`, `healthcheckTimeout`
300 seconds, then up to 3 `ON_FAILURE` restarts. Holding was luck.

`railway up --ci` streams the build logs and exits when the build
completes, not when the upload is accepted. It does not prove the new
image is serving, which is why `deploy.yml`'s deployed-commit verification
is still needed. The companion CI PR (branch
codex/ci-merge-queue-reliability) changes the `deploy-main` concurrency
group to cancel-in-progress false, so one deploy runs at a time and only
the newest pending deploy is kept; that caps parallel deploys but not the
deploy rate. Decoupling merge from deploy caps the rate and adds a gate.

## 3. Proposed model

`main` stays the integration branch. Pull requests still pass the required
checks in `BRANCH_PROTECTION.md`: `CI Status Gate`, `PR Gate: Backend`,
`PR Gate: Frontend`, `PR Gate: Workflow Contract`, plus the merge queue
when it is enabled. The companion CI PR adds the `merge_group` triggers
the queue needs.

Production deploys from a long-lived `release` branch (alternative: tags
`release/*` named `vYYYY.MM.DD-N`). Staging keeps deploying from `main`.
`deploy.yml` today targets the one production service. Staging is a separate
Railway environment — confirm its source branch first.

## 4. How a release happens

A **Promote to production** workflow, `workflow_dispatch`, with an optional
weekday schedule (at most two or three times):

1. Choose a `main` commit that already has a green **Backend CI Status
   Gate** (posted by `backend-ci.yml` when the commit landed on `main`) and
   a green post-deploy staging smoke.
2. Fast-forward `release` to that commit. No merge commit. Refuse the run
   when `release` is not an ancestor of the commit. Rollback is not an
   exception (section 6).
3. Promote ends by dispatching `deploy.yml`. A push to `release` made with
   the workflow's default `GITHUB_TOKEN` does not start other workflows.
   GitHub does not create a workflow run from `GITHUB_TOKEN` events, except
   `workflow_dispatch` and `repository_dispatch`, so the fast-forward does
   not start `deploy.yml`. The dispatch is `gh workflow run` or
   `createWorkflowDispatch`, which `GITHUB_TOKEN` is allowed to call, and
   it passes the promoted SHA as an input. `deploy.yml` checks out that
   exact SHA, verifies its **Backend CI Status Gate**, stamps the build,
   and deploys it. The run still refuses unless the SHA is an ancestor of
   `release` or equal to it, and it still runs in the protected
   `production` GitHub Environment with required reviewer C.Lee
   (section 8(c)). The same rules cover Deploy previous SHA. `deploy.yml`
   stops triggering on `push` to `main`. There is no push path filter on
   this dispatch; a missing gate fails the deploy (`fail-on-no-checks`).
   `backend-ci.yml` does not run on `release`, so the gate has to already
   exist on that commit.
   Alternative: push `release` with a GitHub App token. That push does
   trigger workflows, so a `release` push trigger on `deploy.yml` can be
   the deploy instead of this dispatch. Same ancestor check and the same
   `production` environment. One mechanism only.

Protect `release`: no direct pushes except the promote workflow's GitHub
identity, no force-push, no deletion. No protection bypass for rollback
(section 6). The rule lives in GitHub settings, same as `main`
(`BRANCH_PROTECTION.md`).

## 5. Hotfixes

Pull request to `main`, through the queue and the required checks. Then
Promote to production on that commit immediately. Same path. No hotfix
branch.

## 6. Rollback

`release` is never rewound. Pointing the branch at an older commit is a
non-fast-forward update, and the no-force-push rule forbids it. No
protection bypass.

- **Forward revert (preferred).** `git revert` the bad change(s) on `main`
  through the normal pull request. Promote to production fast-forwards
  `release` to that commit. Same ancestor check as any other promotion.
- **Deploy previous SHA.** A `workflow_dispatch` on `deploy.yml` runs
  `railway up --ci` for a chosen earlier commit. Refuse unless that SHA is
  an ancestor of `release` or equal to it. The job runs in the protected
  `production` GitHub Environment with required reviewer C.Lee
  (section 8(c)). The branch does not move. The job summary records the
  SHA. The next promotion supersedes this deploy.
- **Railway dashboard (fastest).** Deployments → last good deployment →
  Rollback. Restores the image and that deployment's variables
  (`DISASTER_RECOVERY.md` section 7). Does not move `release`. Do not use
  `railway down`. Record the deployed SHA, then reconcile with a forward
  revert on `main` plus Promote so `release` and the running image match
  again. The rollback restores that deployment's variables: if any secret
  was rotated since, re-apply the current variables and secrets before the
  rollback or right after it. Never reinstate a retired credential.

The schema stays. On boot the app runs `alembic upgrade head`. If the
database is already past a revision the older image contains, `/readiness`
fails and Railway keeps the current deployment. Going backward across a
migration is a database restore (`DISASTER_RECOVERY.md`) or a forward fix.
Follow `MIGRATION_ROLLBACK.md`: destructive downgrades are refused in
production. Any rollback that touches `fsma.cte_events`, `fsma.hash_chain`,
or `fsma.traceability_events` requires the audit-chain integrity check in
that runbook (section 7.1, Hash Chain Verification). Do not roll back past
`V039__hash_chain_immutability.sql`: removing it drops `fsma.hash_chain`
immutability protections, so UPDATE and DELETE become possible. One
migration-bearing pull request on `main` at a time stays the rule.

## 7. Railway-side settings

Separate from this document. Needs the founder's yes in the Railway dashboard.

- Exactly one production deploy owner. Recommended: `deploy.yml` owns
  production deploys, and Railway's GitHub auto-deploy for the production
  service is **off**. Do not leave auto-deploy on for a push that
  `deploy.yml` also deploys. Pointing auto-deploy at `release` while
  `deploy.yml` deploys `release` is two owners of the same push. That
  option is not allowed.
- Consider a shorter `healthcheckTimeout` than the current 300 seconds, so
  a crashed boot fails faster. Keep one concurrent deployment so failed
  candidates cannot stack beside the live replica. Dashboard only. This
  pull request does not edit `railway.toml`.

## 8. Implementation steps

Each step is its own pull request, after section 10 is approved.

(a) Create `release` at the commit production is serving, and add the
ruleset (promote identity only, no force-push, no deletion).

(b) Add Promote to production: fast-forward only, require the green backend
gate and the green staging smoke. Refuse when `release` is not an ancestor.
No input rewinds the branch. The workflow's `GITHUB_TOKEN` push does not
start `deploy.yml`. End Promote by dispatching `deploy.yml`
(`gh workflow run` / `createWorkflowDispatch`, which `GITHUB_TOKEN` may
call; the job needs `actions: write`) with the promoted SHA as input.
Add Deploy previous SHA on that same `workflow_dispatch`: check out the
given SHA and run `railway up --ci` only when the SHA is an ancestor of
`release` or equal to it (section 8(c)), record it in the job summary,
and do not move the branch.

(c) Stop `deploy.yml` on `push` to `main`. `workflow_dispatch` takes the
SHA input, checks out that exact SHA, verifies its **Backend CI Status
Gate**, stamps the build with that SHA, and deploys it. Refuse unless the
SHA is an ancestor of `release` or equal to it. That includes Promote and
Deploy previous SHA. The job runs in a protected `production` GitHub
Environment with required reviewer C.Lee. Leave staging on `main`. Rename
concurrency group `deploy-main` in that same change. Exactly one production
deploy owner: `deploy.yml` owns production deploys, and Railway GitHub
auto-deploy for the production service is off (section 7). Alternative to
the dispatch in (b): a GitHub App token pushes `release`, and `deploy.yml`
keeps a `release` push trigger instead. Do not ship both.

(d) Update the runbooks (including `DISASTER_RECOVERY.md`, where
`railway redeploy --from-source` means latest `main`) and run the
Reliability smoke check after each promotion. No workflow here has that
title; that PR names it. Closest today: the deployed-commit assert in
`deploy.yml`, Production Uptime, Public API Surface Probe, and
`scripts/security/staging_release_gate.py`. Before adopting this process,
add read-only checks that an FDA sortable export generates, and that TLC,
KDE, and CTE data and the append-only chain verify. Run those same checks
after each promotion.

(e) Rollback drill: promote forward, then roll back without rewinding
`release`. Exercise the Railway dashboard rollback (record the deployed
SHA; re-apply current variables and secrets if any were rotated; then a
forward revert and Promote so `release` matches the running image), Deploy
previous SHA (branch unchanged; job summary names the SHA; refused unless
that SHA is an ancestor of `release` or equal to it), and a forward
`git revert` fast-forwarded by Promote. Confirm `/readiness` and the
deployed commit, and record a migration in between. When that migration
touches `fsma.cte_events`, `fsma.hash_chain`, or `fsma.traceability_events`,
run the audit-chain integrity check (section 6).

## 9. Risks and open questions

- Who can promote. A founder-only dispatch is slower and safer. A bot
  identity that can dispatch `deploy.yml`, or that pushes `release` with
  a GitHub App token, can ship production. A `GITHUB_TOKEN` push to
  `release` by itself cannot.
- Cadence. On demand, or a cap of two or three promotions per weekday.
  A hotfix uses the same path and skips the cap.
- Vercel. The frontend keeps its own production branch until someone sets
  it to `release`. Until then the site and the API can move on different
  days.
- Migrations that must ship with the backend. Once that commit has migrated
  staging, production has to take the same commit the same day, or the two
  databases diverge. An image rollback will not undo the migration
  (section 6). A direct commit on `release` breaks the next fast-forward;
  the ruleset is what stops that.

## 10. Decision needed

Approve or reject this model, and pick the cadence: on demand, or at most
two or three times per weekday. Until then, production deploys by hand as
section 11 describes.

## 11. Manual deploys today (in effect, not part of the proposal)

Since 2026-10-28 the Railway production service has no GitHub source and
`deploy.yml` is disabled, so every production deploy is a hand-run
`railway up` from a local checkout. A hand deploy must go through
`scripts/railway/deploy_prod.sh`, never a bare `railway up`.

Reason: the image has no `.git` (`.dockerignore` excludes it), so the only
commit identity it carries is `build-sha.txt`, which the `Dockerfile` copies
to `/app/build-sha.txt`. The tracked file is the placeholder `unknown`.
`deploy.yml` overwrites it with the commit before `railway up`; a bare
`railway up` ships the placeholder and `/health` reports `commit_sha: null`.
The 2026-10-29 deploy (Railway deployment `44c0486a`) did exactly that, and
the live commit could only be identified by hashing files inside the
container over `railway ssh`.

The script refuses a dirty tree, stamps `git rev-parse HEAD` into
`build-sha.txt`, runs `railway up --ci` against the production project,
service and environment named on the command line, restores
the placeholder (also on failure), then polls `https://api.regengine.co/health`
until `build.commit_sha` equals the stamped commit, with the same three
failure diagnoses as `deploy.yml`. `--dry-run` does everything except the
upload and the poll. `RAILWAY_PROJECT`, `RAILWAY_SERVICE` and
`RAILWAY_ENVIRONMENT` override the production defaults; `railway link`
state is ignored so a checkout linked to staging cannot redirect it.
