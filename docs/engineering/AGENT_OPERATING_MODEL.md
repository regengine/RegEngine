# Agent Operating Model

This is the small-scale operating model for agent-assisted engineering. It is intentionally boring: one guide, three roles, one task template, and explicit verification.

## Ground Truth

- Active production repo: this repository.
- Product spine: `ingest -> normalize -> validate -> persist evidence -> export`
- Current wedge: Inflow Workbench plus FSMA 204 supplier/ERP evidence readiness.
- Canonical simulator repo: `regengine/inflow-lab`.
- Local snapshots, forks, and archives are reference-only unless a task explicitly imports a specific change.

## Supported Roles

| Role | Scope | May edit files |
| --- | --- | --- |
| `planner` | Verify paths, inspect existing patterns, write a concrete plan. | No |
| `implementer` | Make the smallest useful diff for an approved task. | Yes |
| `security_review` | Review risky diffs for auth, tenant isolation, secrets, database fallback, logging, and deploy risk. | No |

No other agent role is part of the operating model.

## Work Lanes

Use these as task labels, not bot identities:

- backend
- frontend
- security
- QA
- infra
- docs
- FSMA domain
- Inflow Workbench

## Task Requirements

Every task must name:

- Goal
- Files likely touched
- Out of scope
- Tests required
- Risk level: low, medium, or high
- Production-spine impact: ingest, normalize, validate, persist evidence, export, admin/operator workflow, infra/CI, or docs

## Hard Gates

A task is not complete until the final note lists:

- Files changed
- Verification commands run
- Blocked tests, if any, with the reason
- Production-spine impact
- Follow-up risks

Security review is required for auth, tenant isolation, database fallback, archive movement, secrets, audit logging, and deploy changes.

QA review is required before closing changes to ingestion, persistence, FDA export, CI gates, or protected frontend flows.

## Banned Drift

Do not add new agent frameworks, role directories, autonomous chains, or broad cleanup missions without a specific issue and owner. The legacy `regengine.swarm` runtime is disabled by default and requires an explicit `REGENGINE_ENABLE_LEGACY_SWARM=1` opt-in for approved recovery or compatibility work. The `.github/workflows/agent-sweep.yml` audit workflow is manual-only; do not add scheduled or cron triggers. Keep the system small enough that a new engineer can understand it in one page.
