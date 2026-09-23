---
description: Run Project Sentinel audit on the current branch — regression + interstitial checks, strict-mode GH issue filing
argument-hint: "[--loose] [--report-only] [--base=origin/main] [--scope=services/<name>]"
---

# /sentinel-check

You are running the Project Sentinel audit. This is **not** a generic code review — it is a targeted check for two specific failure modes:

1. **Regression**: a previously-shipped fix has been weakened or reverted.
2. **Interstitial**: a new vulnerability has appeared in the handoff between two services.

## Arguments

Parse `$ARGUMENTS` for:
- `--loose` — file issues even without strict evidence (default: strict, terminal-only for weak signals)
- `--report-only` — never run `gh issue create` / `gh issue comment`; list would-be issues under `Proposed Issues (not filed)` instead. Used by CI (`.github/workflows/sentinel.yml`), which runs with a read-only token and has a separate privileged job post the report.
- `--base=<ref>` — diff base, defaults to `origin/main`
- `--scope=<path>` — restrict to a service, e.g. `--scope=services/kernel`

## Step 1 — Establish the change set

Run in parallel:
```
git fetch origin main --quiet
git diff --name-only <base>...HEAD
git log --oneline <base>...HEAD
```

If the change set is empty, exit immediately: "No changes vs <base>; nothing to audit."

If `--scope` is set, filter the change set to that path before continuing.

## Step 2 — Delegate to sentinel-orchestrator

Spawn the `sentinel-orchestrator` subagent with a self-contained prompt that includes:
- The base ref and HEAD SHA
- The full list of changed files (one per line)
- The strict/loose mode flag
- The report-only flag (`report_only: true` when `--report-only` is set)
- The scope filter, if any

The orchestrator returns a structured report with three sections: `Regressions`, `Interstitial Findings`, `Deferred (terminal-only)` — plus `Proposed Issues (not filed)` in report-only mode.

## Step 3 — Surface results to the user

Print the orchestrator's report verbatim. Then summarize:
- Count of issues filed (with `gh issue` URLs), or count of proposed issues in report-only mode
- Count of deferred findings (printed in full, not filed)
- Recommended next action

**Do not** re-analyze, re-rank, or second-guess the orchestrator's output. The agents have already converged. Your job in this command is dispatch and presentation.

## Strict-mode invariants (do not violate)

- No issue is filed without (a) a concrete `file:line` and (b) either a closed-PR-diff reference (regression) or a cross-service taint/contract path (interstitial).
- Before filing, search open issues for fuzzy matches: `gh issue list --search "<key terms>" --state open --json number,title`. If a match exists, append a comment instead of filing new.
- Apply labels: `audit-regression`, `audit-interstitial`, or `audit-observability`. Never file without a label.
- In `--report-only` mode, no `gh` write command is ever run; every surviving finding is rendered as a proposed issue (title, label, body) for a maintainer to file.
