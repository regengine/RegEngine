# RegEngine agent compatibility audit

I inspected the uploaded repository and found a few structural problems that explain why editor agents feel unreliable.

## High-impact problems

### 1. VS Code sees the workspace instructions file, but the checked-in instructions are stale

The repo already has `.github/copilot-instructions.md`, so VS Code will auto-apply it. The problem is that this file currently teaches the agent several things that are not true in the checked-in repo.

Examples from the current file:

- references a repo-root `/shared/` directory even though the actual shared code is in `services/shared/`
- tells agents to run `make up`, `make init-local`, and `make fmt`, but the repo has no `Makefile`
- references `scripts/init-demo-keys.sh`, which is not present
- references a repo-root `conftest.py`, which is not present
- references `industry_plugins/...`, which is not present in this checkout

When an always-on instruction file contains false paths or commands, agents spend their budget following ghosts.

### 2. The repo has a legacy `.agent/` structure, but editor tools look for different locations

The checked-in repo stores personas and workflows under `.agent/`. That works for repo-local scripts like `scripts/swarm_orchestrator.py`, but it is not the default discovery layout for modern VS Code custom agents or Antigravity workspace customizations.

Result: your repo-local swarm layer and your editor agent layer are not aligned.

### 3. Several personas point at non-existent paths or personal absolute file links

Examples in `.agent/personas/`:

- `security.md` points to `shared/auth.py` and `shared/middleware/`, but the repo uses `services/shared/...`
- `qa.md` points to a repo-root `conftest.py`
- `devops.md` points to `.github/workflows/main.yml` and `scripts/release/`, which are not present
- multiple personas include `file:///Users/christophersellers/...` links that only work on one machine

These are fine as historical notes, but they are bad always-on context for editor agents.

## What this fix pack does

### For VS Code

- adds a root `AGENTS.md` with repo-true instructions
- rewrites `.github/copilot-instructions.md` to a short, accurate file
- adds `.github/instructions/` for backend and frontend file-specific guidance
- adds `.github/agents/` so custom agents show up in the editor without extra settings

### For Antigravity / Agent Skills style tools

- adds `.agents/rules/`
- adds `.agents/workflows/`
- adds `.agents/skills/`
- keeps the legacy `.agent/` directory untouched so existing swarm scripts still work

## Recommended next step after applying the patch

1. Open the repo in VS Code and check Chat Diagnostics.
2. Confirm the new `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/*`, and `.github/agents/*` are discovered.
3. In Antigravity, open Customizations and verify the `.agents/rules/`, `.agents/workflows/`, and `.agents/skills/` entries appear.
4. For a trial run, use the planner agent or the `plan_then_implement` workflow on one tiny task in either `frontend/` or one backend service.
