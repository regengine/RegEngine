# Startup Engineering Operating Model

This is the task map for agent-assisted engineering cleanup and launch preparation. It keeps work tied to the FSMA production spine instead of letting parallel work drift into unrelated features.

## Ground Truth

- Active production repo: this repository.
- Product spine: `ingest -> normalize -> validate -> persist evidence -> export`
- Current wedge: Inflow Workbench plus FSMA 204 supplier/ERP evidence readiness
- Canonical simulator repo: `regengine/inflow-lab`
- Local snapshots, forks, and archives are reference-only unless a task explicitly imports a specific change.

## Work Lanes

| Team | Owns | First task |
| --- | --- | --- |
| Bot-Docs-Janitor | Agent guidance, stale docs, path drift | Keep `AGENTS.md`, `.github/agents/`, and docs redirects aligned. Remove `.agent/` assumptions unless that legacy layer is restored. |
| Bot-FSMA | FSMA contracts, CTE/KDE, FDA export | Verify every proposed feature strengthens the FSMA production spine before implementation. |
| Bot-Inflow | Workbench, supplier portal, ingest demos | Compare any reference simulator fork to canonical `regengine/inflow-lab`; port only useful deltas and archive runtime debris. |
| Bot-Backend | FastAPI, persistence, Alembic, service wiring | Add monolith route parity coverage with an allowlist for intentionally excluded standalone routes. |
| Bot-Security | Auth, tenant isolation, audit, secrets | Make production database fallbacks fail closed and inventory secrets before archive cleanup. |
| Bot-Frontend | Next.js, proxy, CSP, operator UX | Fix CSP coverage and config validation; keep Vercel installs deterministic with `npm ci`. |
| Bot-Infra | CI, deploy, archives, observability | Add release gates for manual deploys and draft a deletion manifest for large archived clones. |
| Bot-QA | Test harnesses, smoke paths, regression gates | Repair documented test commands so local setup matches CI, especially ingestion xdist usage. |

## Priority Queue

1. Agent guidance hygiene
   - Root `AGENTS.md` is the source of truth.
   - `.github/copilot-instructions.md` must point agents at real paths only.
   - `scripts/summon_agent.py` must keep discovering checked-in `.github/agents/*.agent.md` specs.
   - Docs redirects should point to the current guide, not removed legacy agent directories.

2. Backend test and route health
   - Decide whether `pytest-xdist` belongs in canonical dev dependencies and `requirements.lock`, or document the explicit install step for the ingestion hard gate.
   - Fail closed for `ADMIN_DATABASE_URL` outside explicit local/test fallback mode.
   - Stop global test defaults from making DB e2e tests look configured when they are not.
   - Add monolith route parity tests against standalone service routers.

3. Frontend and deploy safety
   - Expand CSP coverage and add tests for fonts, Sentry, Supabase, Vercel analytics, and Railway endpoints.
   - Add production URL validation for frontend service proxies.
   - Promote at least one protected-route Playwright smoke path from advisory to blocking.
   - Require the selected SHA to have passing frontend/backend CI before manual Railway deploy.

4. Workspace cleanup
   - Treat `regengine/inflow-lab` as canonical simulator code.
   - Treat local forks and extracted snapshots as archaeology unless a task explicitly imports a change.
   - Build a secret-aware deletion manifest before removing archived material.
   - Keep investor/legal collateral out of code triage unless a docs task needs it.

## Dispatch Rules

- One team owns a task until it hands off.
- Every implementation task names files, tests, and production-spine impact.
- Security reviews are required for auth, tenant isolation, database fallback, archive movement, and deploy changes.
- QA reviews are required before closing changes to ingestion, persistence, FDA export, CI, or protected frontend flows.
