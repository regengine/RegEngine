# CI timing, November 2026 (WI-04 measurement)

Measured 2026-11-04 with `scripts/ci/ci_timing_report.py`: the last 30 completed
`pull_request` runs of each workflow, read through the GitHub API (`gh api`, one
page per run; the proxy in the agent sandbox rejects paginated numeric-id
links). Durations come from `started_at`/`completed_at` of each job, so queue
time before a job starts is excluded from job numbers but included in the run
wall-clock. "Top failure cause" is the first failing step's name in the failed
jobs, not a log read; where that is a wait-or-poll step the cause is upstream.

Re-measure with:

```bash
venv/bin/python scripts/ci/ci_timing_report.py /tmp/ci_timing.json
```

## Run wall-clock per workflow

| Workflow | Runs | Median | p90 | Success | Failure | Cancelled | Action required |
|---|--:|--:|--:|--:|--:|--:|--:|
| `pr-gate.yml` | 30 | 9.6 min | 24.6 min | 14 | 8 | 5 | 3 |
| `pr-guards.yml` | 30 | 0.4 min | 3.6 min | 4 | 16 | 7 | 3 |
| `backend-ci.yml` | 30 | 24.1 min | 58.3 min | 21 | 3 | 5 | 1 |
| `frontend-ci.yml` | 30 | 4.2 min | 14.5 min | 18 | 6 | 3 | 3 |
| `security.yml` | 30 | 4.4 min | 14.3 min | 23 | 0 | 4 | 3 |

`action_required` runs are Copilot-authored PRs waiting for a maintainer to approve
workflow execution; they never ran. Cancelled runs are superseded pushes.

## `pr-gate.yml` jobs

| Job | n | Median | p90 | Failures | Cancelled | Top failing step |
|---|--:|--:|--:|--:|--:|---|
| PR Gate: Secrets | 27 | 5.1 min | 5.3 min | 0 | 5 |  |
| PR Gate: Frontend | 27 | 3.8 min | 8.3 min | 4 | 4 | Wait for Frontend CI Status Gate (4) |
| PR Gate: Backend | 27 | 0.2 min | 24.4 min | 0 | 2 |  |
| PR Gate: Workflow Contract | 27 | 0.2 min | 0.2 min | 0 | 1 |  |
| Commit Message Check | 27 | 0.2 min | 0.4 min | 8 | 4 | Check commit messages (8) |
| Auto-Label PR | 27 | 0.2 min | 0.3 min | 0 | 4 |  |
| PR Size Check | 27 | 0.2 min | 0.7 min | 0 | 4 |  |
| Audit Trail Protection | 27 | 0.2 min | 0.4 min | 0 | 4 |  |
| Tenant Isolation Check | 27 | 0.1 min | 0.2 min | 0 | 4 |  |
| Supabase Query Patterns | 27 | 0.1 min | 0.2 min | 0 | 4 |  |
| Source Hygiene | 27 | 0.1 min | 0.2 min | 0 | 4 |  |
| SQL Injection Defense | 27 | 0.1 min | 0.4 min | 0 | 4 |  |
| React Patterns | 27 | 0.1 min | 0.2 min | 0 | 4 |  |
| PR Gate: Path Detection | 27 | 0.1 min | 0.1 min | 0 | 1 |  |
| Copy Lint — ban A-F grade/verdict UIs in /tools | 27 | 0.1 min | 0.2 min | 0 | 4 |  |
| PR Gate: Jev Evidence | 27 | 0.1 min | 0.1 min | 0 | 4 |  |
| CI Status Gate | 27 | 0.1 min | 0.1 min | 9 | 0 | Verify all gate dependencies passed (9) |

## `pr-guards.yml` jobs

| Job | n | Median | p90 | Failures | Cancelled | Top failing step |
|---|--:|--:|--:|--:|--:|---|
| Head SHA Check Guard | 27 | 0.3 min | 0.3 min | 0 | 4 |  |
| PR Blocker Checklist | 27 | 0.1 min | 0.1 min | 0 | 7 |  |
| Engine Review Pass | 27 | 0.1 min | 0.1 min | 17 | 6 | Verify engine review pass (17) |

## `backend-ci.yml` jobs

| Job | n | Median | p90 | Failures | Cancelled | Top failing step |
|---|--:|--:|--:|--:|--:|---|
| Test ingestion | 28 | 20.2 min | 21.1 min | 1 | 4 | Run tests with coverage (1) |
| Ingestion full suite (xdist signal) | 29 | 6.2 min | 7.8 min | 2 | 1 | Run ingestion suite with per-file worker isolation (2) |
| Test admin | 28 | 3.9 min | 4.1 min | 0 | 0 |  |
| Test graph | 28 | 3.9 min | 4.1 min | 0 | 0 |  |
| Repo-root security/RLS/isolation suite | 29 | 3.7 min | 4.2 min | 1 | 0 | Schema parity audit (WS-2c) (1) |
| Test shared | 28 | 2.9 min | 3.0 min | 0 | 0 |  |
| Test nlp | 28 | 2.2 min | 2.3 min | 0 | 0 |  |
| Docker Build (monolith) | 29 | 2.1 min | 2.2 min | 0 | 0 |  |
| Live DB suite (migrated scratch) | 29 | 2.0 min | 2.2 min | 0 | 1 |  |
| Test compliance | 28 | 2.0 min | 2.2 min | 0 | 0 |  |
| Test scheduler | 28 | 2.0 min | 2.2 min | 0 | 0 |  |
| Production lock imports server.main | 1 | 1.4 min | 1.4 min | 0 | 0 |  |
| Seeded migration rehearsal (supabase-client-roles, 267d8053ced5) | 29 | 1.4 min | 1.6 min | 0 | 1 |  |
| Seeded migration rehearsal (app-roles-only, 267d8053ced5) | 29 | 1.4 min | 1.5 min | 0 | 1 |  |
| Seeded migration rehearsal (app-roles-only, 38e02636e340) | 29 | 1.4 min | 1.5 min | 0 | 1 |  |
| Seeded migration rehearsal (supabase-client-roles, 38e02636e340) | 29 | 1.3 min | 1.4 min | 0 | 1 |  |
| mypy shared/ (report only) | 1 | 1.2 min | 1.2 min | 0 | 0 |  |
| Dependency Lock Freshness | 29 | 0.7 min | 0.8 min | 0 | 1 |  |
| Security Audit nlp | 29 | 0.7 min | 0.8 min | 0 | 1 |  |
| Security Audit ingestion | 29 | 0.7 min | 0.8 min | 0 | 1 |  |
| Security Audit graph | 29 | 0.7 min | 0.8 min | 0 | 0 |  |
| Security Audit compliance | 29 | 0.6 min | 0.8 min | 0 | 1 |  |
| Security Audit scheduler | 29 | 0.6 min | 0.8 min | 0 | 1 |  |
| Security Audit admin | 29 | 0.6 min | 0.8 min | 0 | 1 |  |
| Lint graph | 29 | 0.2 min | 0.3 min | 0 | 1 |  |
| Lint compliance | 29 | 0.2 min | 0.2 min | 0 | 1 |  |
| Lint admin | 29 | 0.2 min | 0.3 min | 0 | 1 |  |
| Lint shared/ | 29 | 0.2 min | 0.2 min | 1 | 1 | Run linting (1) |
| Lint repo roots | 29 | 0.2 min | 0.2 min | 0 | 1 |  |
| Lint nlp | 29 | 0.2 min | 0.2 min | 0 | 0 |  |
| Lint scheduler | 29 | 0.2 min | 0.2 min | 0 | 0 |  |
| Lint ingestion | 29 | 0.2 min | 0.2 min | 0 | 0 |  |
| Dep version drift guard | 29 | 0.1 min | 0.2 min | 0 | 0 |  |
| tenant_id UUID-only guard | 29 | 0.1 min | 0.2 min | 0 | 0 |  |
| Alembic revision ID guard | 29 | 0.1 min | 0.2 min | 0 | 0 |  |
| RLS fail-open migration guard | 29 | 0.1 min | 0.2 min | 0 | 0 |  |
| Backend CI Status Gate | 29 | 0.1 min | 0.1 min | 3 | 5 | Check results (3) |
| Test ${{ matrix.service }} | 1 | 0.0 min | 0.0 min | 0 | 1 |  |

## `frontend-ci.yml` jobs

| Job | n | Median | p90 | Failures | Cancelled | Top failing step |
|---|--:|--:|--:|--:|--:|---|
| Passwordless Auth E2E (Chromium) | 26 | 3.1 min | 3.8 min | 1 | 3 | Prepare isolated PostgreSQL E2E fixture (1) |
| Unit Tests | 26 | 3.0 min | 3.4 min | 1 | 3 | Run Vitest (with coverage thresholds enforced) (1) |
| Build & Bundle Analysis | 26 | 1.3 min | 1.4 min | 0 | 1 |  |
| Lint & Format | 26 | 1.2 min | 1.3 min | 4 | 3 | Ban trust-and-safety outcome-promise copy (4) |
| Production Readiness Gate | 26 | 0.6 min | 0.7 min | 0 | 2 |  |
| Deterministic Smoke Tests | 26 | 0.5 min | 0.6 min | 0 | 2 |  |
| Promise Audit | 26 | 0.5 min | 0.6 min | 0 | 1 |  |
| Security Audit | 26 | 0.5 min | 0.6 min | 0 | 3 |  |
| Frontend CI Status Gate | 26 | 0.1 min | 0.1 min | 5 | 3 | Check results (5) |

## `security.yml` jobs

| Job | n | Median | p90 | Failures | Cancelled | Top failing step |
|---|--:|--:|--:|--:|--:|---|
| SAST (Semgrep) | 27 | 3.4 min | 3.6 min | 0 | 0 |  |
| Browser Storage PII Guard | 27 | 0.1 min | 0.2 min | 0 | 0 |  |
| security.txt Expiry Check | 27 | 0.1 min | 0.2 min | 0 | 0 |  |
| Privileged Workflow Tool Pinning | 27 | 0.1 min | 0.1 min | 0 | 0 |  |
| Security path changes | 27 | 0.1 min | 0.1 min | 0 | 0 |  |
| DAST preflight (ZAP_TARGET configured?) | 27 | 0.1 min | 0.1 min | 0 | 0 |  |
| Secrets Scan (gitleaks) | 27 | 0.0 min | 0.0 min | 0 | 0 |  |
| Secrets Audit (detect-secrets) | 27 | 0.0 min | 0.0 min | 0 | 0 |  |
| Audit Chain Integrity | 27 | 0.0 min | 0.0 min | 0 | 0 |  |
| Tenant Isolation & Auth Tests | 27 | 0.0 min | 2.0 min | 0 | 0 |  |
| Image provenance (SBOM + cosign) | 27 | 0.0 min | 0.0 min | 0 | 4 |  |
| Container Scan (Trivy) | 27 | 0.0 min | 0.0 min | 0 | 4 |  |
| Generate SBOM (SPDX) | 27 | 0.0 min | 0.0 min | 0 | 4 |  |
| Audit chain preflight (secrets configured?) | 27 | -0.0 min | 0.0 min | 0 | 0 |  |
| Dependency Audit | 27 | -0.0 min | 0.0 min | 0 | 0 |  |
| DAST (OWASP ZAP baseline) | 27 | -0.0 min | 0.0 min | 0 | 2 |  |

## Reading

- **The critical path is `backend-ci.yml` → `Test ingestion`** (median 20.2 min
  of a 24.1-minute median run; its job timeout is 25 minutes). Every other
  backend job finishes under 7 minutes. `PR Gate: Backend` in `pr-gate.yml` is a
  waiter on that run, which is why its p90 is 24.4 minutes with a 0.2-minute
  median: it only costs time when backend paths changed.
- **`pr-gate.yml` run p90 (24.6 min) is queue and waiting, not work.** The
  longest real job there is `PR Gate: Secrets` at 5.1 min (gitleaks over full
  history, `fetch-depth: 0`).
- **`pr-gate-frontend-rerun.yml` exists for a wait, not a flaky spec.** The four
  `PR Gate: Frontend` failures all end in `Wait for Frontend CI Status Gate`:
  the frontend run was still queued or had failed when the 12-minute wait
  expired. Among `frontend-ci.yml` jobs the failures are `Lint & Format` (4,
  all the trust-and-safety copy gate on SEO content PRs), `Unit Tests` (1) and
  `Passwordless Auth E2E` (1, the PostgreSQL fixture step). No single spec
  shows up as flaky in these 30 runs, so requirement 3 of WI-04 (fix the
  flaky spec, archive the rerun workflow) has nothing to fix yet; the rerun
  workflow stays until a spec is identified.
- **`pr-guards.yml` fails on 16 of 30 runs by design:** `Engine Review Pass` is
  red until a second engine posts its marker (17 of 27 job runs). `Commit
  Message Check` failed 8 times, each on a non-Conventional subject.
- **`security.yml` is cheap** (median 4.4 min, no failures); `SAST (Semgrep)`
  is its only job over a minute.

## Follow-up measurement

To be appended after the WI-04 changes have run on pull requests: the same
table, same command, and a one-line verdict on whether the median PR
wall-clock moved. The consolidation in this PR touches setup steps and
concurrency only; the ingestion test leg sets the floor until its suite is
sharded, which WI-04 does not do.
