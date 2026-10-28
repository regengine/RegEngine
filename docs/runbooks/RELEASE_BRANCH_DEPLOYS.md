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
   when `release` is not an ancestor of the commit. Rollback is not an
   exception (section 6).
3. The push to `release` is the production deploy. `deploy.yml`'s push
   trigger is `release` only. It stops triggering on `push` to `main`.
   Any `workflow_dispatch`, including Deploy previous SHA, refuses unless
   the SHA is an ancestor of `release` or equal to it, and runs in the
   protected `production` GitHub Environment with required reviewer C.Lee
   (section 8(c)). Same wait for **Backend CI Status Gate**, same backend
   path filter, same `railway up --ci`.
   `backend-ci.yml` does not run on `release`, so the gate has to already
   exist on that commit. A missing gate fails the deploy (`fail-on-no-checks`).

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
No input rewinds the branch. Add Deploy previous SHA: `workflow_dispatch`
on `deploy.yml` runs `railway up --ci` only when the SHA is an ancestor of
`release` or equal to it (section 8(c)), records it in the job summary,
and does not move the branch.

(c) Switch the `deploy.yml` production push trigger from `main` to
`release` only. Exactly one production deploy owner: `deploy.yml` owns
production deploys, and Railway GitHub auto-deploy for the production
service is off (section 7). Keep `workflow_dispatch`, and refuse the run
unless the SHA is an ancestor of `release` or equal to it. That includes
Deploy previous SHA. The job runs in a protected `production` GitHub
Environment with required reviewer C.Lee. Leave staging on `main`. Rename
concurrency group `deploy-main` in that same change.

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
