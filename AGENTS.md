# RegEngine Agent Guide

## Mission

RegEngine is a pre-production FSMA 204 traceability application. Agent work should strengthen the production spine:

```text
ingest -> normalize -> validate -> persist evidence -> export
```

If a change does not protect or improve that spine, mark it as experimental, docs-only, or out of scope.

## Workspace Map

- `repo/` (`~/Projects/RegEngine/repo`) is the production RegEngine application
  repository and the default target for all work.
- The directories beside it under `~/Projects/RegEngine/` are **git worktrees off
  this same repo**, plus `_archive/` (snapshots and backups, reference only) and
  `docs/` (founder/investor material). Many live worktrees exist across five
  locations. Read `~/Projects/RegEngine/AGENTS.md` for the map, and run
  `git worktree list` before editing so you know which checkout you are in.
- The Inflow Lab simulator lives at `~/inflow-lab` (github.com/regengine/inflow-lab),
  **not** beside this repo. A second checkout sits at
  `~/Projects/conductor/repos/inflow-lab`. Do not mix Inflow Lab code into
  `repo/` unless the task explicitly asks for an integration.

## Source Of Truth

Read these before large changes:

- `README.md`
- `REPO_PURPOSE.md`
- `ARCHITECTURE.md`
- `CANONICAL_OWNERSHIP.md`
- `docs/specs/FSMA_204_MVP_SPEC.md`
- `frontend/package.json` for frontend commands
- `.github/copilot-instructions.md` for editor-agent guidance

## Agent Roles

Only three agent roles are supported:

- `planner`: read-only research, path checks, and implementation plans.
- `implementer`: small scoped code or documentation changes.
- `security_review`: review for auth, tenant isolation, secrets, database fallback, logging, and deploy risk.

Use plain work lanes such as backend, frontend, security, QA, infra, or docs when triaging tasks. These are labels, not bot identities.

## Working Rules

- Verify files and commands before acting. Do not follow stale paths from old audit docs.
- Do not invent `.agent/` or `.agents/` directories to satisfy old instructions. Current agent specs live in `.github/agents/`.
- Do not run the legacy `regengine.swarm` autonomous runtime unless a task explicitly approves `REGENGINE_ENABLE_LEGACY_SWARM=1`.
- Prefer existing patterns from nearby service/frontend code.
- Keep diffs small and tied to the assigned lane.
- Preserve tenant isolation, audit evidence, and schema validation on ingestion paths.
- Use `python3`, not `python`, in local commands unless a virtual environment explicitly provides `python`.
- Use `npm` in `frontend/`; `package-lock.json` is checked in.
- The repo has no `Makefile`, so do not suggest `make` commands.
- Agents do not decide product direction. They execute scoped engineering tasks against the FSMA production spine.

## Jev Sidecar

Consult TypeSafe Jev alongside the user's requests.

- When a request contains a judgment (which of these, is this true, how much), run `scripts/jev_ask.py` and report Jev's answer and confidence next to your own.
- Run it with a Python that has `requirements.lock` installed. In Claude Code sessions that is `venv/bin/python`.
- Follow `.claude/skills/jev-sidecar/SKILL.md` for when to ask, what never to send, and how to report.
- It needs `TYPESAFE_API_KEY` in the environment. Without the key the script exits 2 and sends nothing: say so once and continue.

## Verification

Choose the smallest useful verification for the changed surface:

```bash
python3 -m pytest tests/swarm -q
python3 -m pytest services/ingestion/tests -q --no-cov
python3 -m pytest services/admin/tests -q --no-cov
cd frontend && npm run lint
cd frontend && npm run test:run
cd frontend && npm run build
```

`frontend/` has no `typecheck` script. Use `npm run lint` (eslint + design-lint)
and `npm run build` for type errors. Full script list is in
`frontend/package.json`.

Some integration tests require PostgreSQL, Redis, Neo4j, Docker, or live services. If a command is blocked by local infrastructure or secrets, say so explicitly.
