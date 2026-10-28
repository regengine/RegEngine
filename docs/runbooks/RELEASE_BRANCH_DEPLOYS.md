# Plan: production deploys from a release branch (PROPOSED — not in effect)

Written 2026-10-28 from `.github/workflows/deploy.yml`, `railway.toml`,
`docs/runbooks/BRANCH_PROTECTION.md`, `docs/runbooks/MIGRATION_ROLLBACK.md`,
and `docs/operations/DISASTER_RECOVERY.md` section 7. Proposal only: no
workflow, Railway setting, or branch rule changes with this file.

## 1. Status

Production still deploys on every backend-relevant push to `main`.

`.github/workflows/deploy.yml` ("Deploy to Railway") runs on `push` to
`main` for the backend path list, and on `workflow_dispatch`. It waits for
a green **Backend CI Status Gate** on that commit, then runs `railway up --ci`
against the production Railway service. Vercel deploys the frontend separately.

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

`railway up --ci` returns when the upload is accepted, so a Railway build
can keep running after the GitHub job ends. The companion CI PR (branch
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
   when `release` is not an ancestor of the commit, unless the run is an
   explicit rollback (section 6).
3. The push to `release` is the production deploy. `deploy.yml`'s production
   job then triggers on `push` to `release` and on `workflow_dispatch`, and
   stops triggering on `push` to `main`. Same wait for **Backend CI Status
   Gate**, same backend path filter, same `railway up --ci`.
   `backend-ci.yml` does not run on `release`, so the gate has to already
   exist on that commit. A missing gate fails the deploy (`fail-on-no-checks`).

Protect `release`: no direct pushes except the promote workflow's GitHub
identity, no force-push, no deletion. The rule lives in GitHub settings,
same as `main` (`BRANCH_PROTECTION.md`).

## 5. Hotfixes

Pull request to `main`, through the queue and the required checks. Then
Promote to production on that commit immediately. Same path. No hotfix
branch.

## 6. Rollback

Two ways, same commit:

- Promote to production with a `sha` input set to the previous release
  commit, so `release` moves back and `deploy.yml` ships that tree.
- Railway: Deployments → last good deployment → Rollback. That restores
  the image and that deployment's variables (`DISASTER_RECOVERY.md`
  section 7). Do not use `railway down`.

The schema stays. On boot the app runs `alembic upgrade head`. If the
database is already past a revision the older image contains, `/readiness`
fails and Railway keeps the current deployment. Going backward across a
migration is a database restore (`DISASTER_RECOVERY.md`) or a forward fix.
Follow `MIGRATION_ROLLBACK.md`: destructive downgrades are refused in
production. One migration-bearing pull request on `main` at a time stays
the rule.

## 7. Railway-side settings

Separate from this document. Needs the founder's yes in the Railway dashboard.

- One production deploy path. Turn Railway's GitHub auto-deploy **off** on
  the production service, or point it at `release` with **Wait for CI**
  enabled. Leaving it on `main` while `deploy.yml` also deploys is two
  paths.
- Consider a shorter `healthcheckTimeout` than the current 300 seconds, so
  a crashed boot fails faster. Keep one concurrent deployment so failed
  candidates cannot stack beside the live replica. Dashboard only. This
  pull request does not edit `railway.toml`.

## 8. Implementation steps

Each step is its own pull request, after section 10 is approved.

(a) Create `release` at the commit production is serving, and add the
ruleset (promote identity only, no force-push, no deletion).

(b) Add Promote to production: fast-forward only, require the green backend
gate and the green staging smoke, `sha` input for rollback.

(c) Switch the `deploy.yml` production trigger from `main` to `release`.
Keep `workflow_dispatch`. Leave staging on `main`. Rename concurrency group
`deploy-main` in that same change.

(d) Update the runbooks (including `DISASTER_RECOVERY.md`, where
`railway redeploy --from-source` means latest `main`) and run the
Reliability smoke check after each promotion. No workflow here has that
title; that PR names it. Closest today: the deployed-commit assert in
`deploy.yml`, Production Uptime, Public API Surface Probe, and
`scripts/security/staging_release_gate.py`.

(e) Rollback drill: promote forward, promote back one commit, confirm
`/readiness` and the deployed commit, and record a migration in between.

## 9. Risks and open questions

- Who can promote. A founder-only dispatch is slower and safer. A bot
  identity that can push `release` can ship production.
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
two or three times per weekday. Until then, production keeps deploying
from `main` through `deploy.yml`.
