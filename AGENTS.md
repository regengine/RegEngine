# RegEngine Agent Guide

## Mission

RegEngine is a pre-production FSMA 204 traceability application. Agent work should strengthen the production spine:

```text
ingest -> normalize -> validate -> persist evidence -> export
```

If a change does not protect or improve that spine, mark it as experimental, docs-only, or out of scope.

## Workspace Map

- `repo/` is the production RegEngine application repository.
- `inflow-lab/` and `inflow-lab-fork/` are simulator/demo workspaces. Do not mix their code into `repo/` unless the task explicitly asks for an integration.
- `petrefied-fork-android/`, `snapshots/`, and `_archive/` are local forks, extracted snapshots, or backups. Treat them as reference material only.

## Source Of Truth

Read these before large changes:

- `README.md`
- `REPO_PURPOSE.md`
- `CURRENT_SYSTEM_MAP.md`
- `CANONICAL_OWNERSHIP.md`
- `docs/specs/FSMA_204_MVP_SPEC.md`
- `frontend/package.json` for frontend commands
- `.github/copilot-instructions.md` for editor-agent guidance

## Bot Teams

Use these lanes when assigning work:

- Bot-FSMA: FSMA 204 CTE/KDE contracts, rules, FDA export, traceability evidence.
- Bot-Inflow: Inflow Workbench, supplier portal, CSV/webhook/EPCIS/EDI ingest, readiness scoring.
- Bot-Backend: FastAPI routers, `services/shared/`, Alembic migrations, server wiring, persistence.
- Bot-Frontend: Next.js App Router, dashboard tools, auth UX, design-system consistency.
- Bot-Security: auth, API keys, tenant isolation, RLS assumptions, audit logs, secrets, PII.
- Bot-Infra: Docker, Railway, GitHub Actions, deployment config, health checks, observability.
- Bot-QA: pytest/vitest/playwright coverage, fixtures, smoke scripts, regression harnesses.
- Bot-Docs-Janitor: stale paths, obsolete non-FSMA docs, duplicated handoffs, agent instructions.

## Working Rules

- Verify files and commands before acting. Do not follow stale paths from old audit docs.
- Do not invent `.agent/` or `.agents/` directories to satisfy old instructions. Current editor agents live in `.github/agents/`.
- Prefer existing patterns from nearby service/frontend code.
- Keep diffs small and tied to the assigned lane.
- Preserve tenant isolation, audit evidence, and schema validation on ingestion paths.
- Use `python3`, not `python`, in local commands unless a virtual environment explicitly provides `python`.
- Use `npm` in `frontend/`; `package-lock.json` is checked in.
- The repo has no `Makefile`, so do not suggest `make` commands.

## Verification

Choose the smallest useful verification for the changed surface:

```bash
python3 -m pytest tests/swarm -q
python3 -m pytest services/ingestion/tests -q --no-cov
python3 -m pytest services/admin/tests -q --no-cov
cd frontend && npm run lint
cd frontend && npm run test:run
```

Some integration tests require PostgreSQL, Redis, Neo4j, Docker, or live services. If a command is blocked by local infrastructure or secrets, say so explicitly.
