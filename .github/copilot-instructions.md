---
applyTo: "**"
---

# RegEngine coding instructions

Read [AGENTS.md](../AGENTS.md) first.

## Fast repo facts

- Python shared modules live in `services/shared/`, not a repo-root `shared/` directory.
- The repository is a Python services monorepo plus a Next.js frontend in `frontend/`.
- `frontend/package-lock.json` is checked in, so default to `npm` for frontend commands.
- The repo does not contain a `Makefile` or a repo-root `conftest.py`.
- The repo-local swarm scripts still use `.agent/`; editor-facing rules, workflows, and skills live in `.agents/`.

## Prefer these sources of truth

- [README.md](../README.md)
- [Local setup guide](../docs/LOCAL_SETUP_GUIDE.md)
- [Environment setup checklist](../docs/ENV_SETUP_CHECKLIST.md)
- [FSMA 204 MVP spec](../docs/specs/FSMA_204_MVP_SPEC.md)
- [Shared path bootstrap helpers](../services/shared/paths.py)
- [Repo smoke test script](../scripts/test-all.sh)
- [Frontend package.json](../frontend/package.json)

## Working rules

- Verify paths and commands before using them.
- Prefer minimal edits over broad refactors.
- Reuse existing patterns from nearby files.
- If you touch Python service code, keep it compatible with `ensure_shared_importable()` patterns.
- If you touch frontend code, stay within current App Router and component conventions.
- Say clearly when verification is blocked by missing services, env vars, or secrets.
