# Security workflow trim proposal

Issue: #2032

## Goal

Reduce GitHub Actions minutes in `.github/workflows/security.yml` without weakening the release gates that currently protect production.

Recent run data showed `security` as the largest workflow minute consumer:

- Last 30 days: 147 security runs, 1188 minutes total, 8 minutes average wall time.
- Last 50 security runs:
  - `pull_request`: 28 runs, 241 minutes total, 8 minutes average wall time.
  - `push`: 22 runs, 193 minutes total, 8 minutes average wall time.
- Representative successful run #25206597822 billable job sum:
  - `SAST (Semgrep)`: 5.97 minutes
  - `Container Scan (Trivy)`: 2.65 minutes
  - `Secrets Audit (detect-secrets)`: 2.12 minutes
  - `Dependency Audit`: 1.72 minutes
  - `Secrets Scan (gitleaks)`: 0.93 minutes
  - `Generate SBOM (SPDX)`: 0.25 minutes

## Implemented changes

### Workflow level

- Add `paths-ignore` for markdown, `docs/**`, and issue templates.
- Add workflow `concurrency` with `cancel-in-progress: true` so superseded branch pushes do not keep burning minutes.

### Semgrep

- Install Semgrep once instead of once per Semgrep step.
- Remove the separate artifact-only combined scan.
- Keep the existing blocking semantics:
  - OWASP Top Ten remains a hard gate on findings.
  - `p/security-audit` remains a hard gate on `ERROR` severity findings.
  - EPIC-A tenant-trust scan remains advisory.

The earlier one-scan idea was not applied because `--severity ERROR` would apply globally and weaken the OWASP Top Ten gate. The original OWASP gate used `--error` with no severity filter, so it failed on any OWASP finding. The corrected trim keeps two distinct Semgrep scans after one install.

### SBOM

- Skip SBOM generation/signing on `pull_request`.
- Keep SBOM on `push` to `main`, weekly schedule, and `workflow_dispatch`.

### Trivy

- Skip monolith Docker image build and Trivy scan on `pull_request`.
- Keep Trivy on `push` to `main`, weekly schedule, and `workflow_dispatch`.

This preserves the production-release signal while removing the largest PR-only minute sink.

## Expected impact

- Frontend/content PRs no longer run Docker build + Trivy.
- PRs no longer run SBOM generation/signing.
- Docs-only changes no longer run the full security workflow.
- Semgrep avoids repeated package installation and one redundant scan.
- Pushes that supersede earlier branch pushes cancel older security runs.

Measured per-run billable baseline is about 13.6 minutes for the representative security run.

- PR runs: about 8.7 minutes after trim, saving about 4.9 minutes per run:
  - Semgrep dedup: about 2.0 minutes saved.
  - Trivy + SBOM skipped: about 2.9 minutes saved.
- Push runs: about 11.6 minutes after trim, saving about 2.0 minutes per run from Semgrep dedup only.
- 30-day projection from recent data:
  - 28 PR runs x 4.9 minutes = about 137 minutes saved.
  - 22 push runs x 2.0 minutes = about 44 minutes saved.
  - Total: about 181 minutes/month saved on the security workflow, or roughly 15%.

Concurrency cancellation and `paths-ignore` add unmeasured savings on top. The earlier 40-60% estimate was too high because it conflated wall time with billable parallel-job sum.

## Operational gotchas

### Branch protection and `paths-ignore`

Workflow-level `paths-ignore` can block docs-only PRs if branch protection requires checks from this workflow, because GitHub may wait for a check that never runs. At implementation time, the classic branch protection endpoint reported `main` as not protected and repo rulesets returned no entries, so this is not currently blocking.

If required status checks are added later, move the skip logic to per-job `if:` clauses or add a stable always-pass stub job before requiring this workflow.

### Validation depth

YAML parsing catches syntax errors only. `actionlint` catches GitHub workflow schema/expression issues and ShellCheck findings in `run:` blocks.

This branch was validated with:

```bash
ruby -e 'require "yaml"; YAML.load_file(".github/workflows/security.yml"); puts "yaml ok"'
actionlint .github/workflows/security.yml
git diff --check
```

## Follow-up candidates

The next largest consumers after `security` are `Frontend CI/CD` and `QA Pipeline`, about 912 minutes/month combined in the latest aggregate. Audit those after this security trim ships.

## Validation

After billing is unblocked, validate operationally:

1. Open the PR and confirm docs-only changes do not trigger the security workflow.
2. Confirm a frontend-only PR skips `Generate SBOM (SPDX)` and `Container Scan (Trivy)`.
3. Confirm `SAST (Semgrep)`, secrets scans, dependency audit, and `security.txt` still run on code PRs.
4. Confirm a push to `main` still runs SBOM and Trivy.
