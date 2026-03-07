# RegEngine workspace instructions

## What this repository is

RegEngine is a monorepo with two main code surfaces:

- `services/` — Python FastAPI services and shared backend modules.
- `frontend/` — Next.js 15 App Router frontend.

The active product wedge in the checked-in docs is FSMA-first traceability. Prefer existing FSMA, auth, onboarding, and admin flows before inventing new vertical abstractions.

## Ground-truth files to read first

Use these files before making assumptions:

- `README.md`
- `docs/LOCAL_SETUP_GUIDE.md`
- `docs/ENV_SETUP_CHECKLIST.md`
- `docs/specs/FSMA_204_MVP_SPEC.md`
- `services/shared/paths.py`
- `scripts/test-all.sh`
- `frontend/package.json`

## Path and architecture rules

- Shared Python code lives in `services/shared/`, not in a repo-root `shared/` folder.
- Existing service directories are:
  - `services/admin/`
  - `services/billing/`
  - `services/compliance/`
  - `services/devops/`
  - `services/energy/`
  - `services/graph/`
  - `services/ingestion/`
  - `services/nlp/`
  - `services/opportunity/`
  - `services/scheduler/`
  - `services/shared/`
- Do not invent or rely on directories that are not present in the repo.
- The legacy `.agent/` directory is used by repo-local swarm scripts. The `.agents/` directory is the editor compatibility layer for Antigravity and Agent Skills style tooling.

## How to work in this monorepo

- Search first. Point to existing files before proposing changes.
- Make the smallest viable change.
- Keep docs and code in sync when behavior changes.
- If you touch Python service entrypoints, follow the existing bootstrap pattern built around `services/shared/paths.py` and `ensure_shared_importable()`.
- If you touch frontend files, follow current Next.js App Router patterns under `frontend/src/app/` and existing reusable components under `frontend/src/components/`.
- Prefer editing real specs and runbooks over creating speculative new documentation.

## Commands that match the checked-in repo

From repo root:

- `python -m pytest tests -q`
- `python -m pytest services/<service>/tests -q`
- `bash scripts/test-all.sh --quick`

From `frontend/`:

- `npm install`
- `npm run lint`
- `npm run test:run`
- `npm run build`

Use `npm` as the default frontend package manager because `frontend/package-lock.json` is committed.

## Avoid these bad assumptions

- Do not assume a `Makefile` exists.
- Do not assume a repo-root `conftest.py` exists.
- Do not assume `.gemini/settings.json` exists in the repository.
- Do not rely on absolute `file:///Users/...` links.
- Do not claim a path, command, or service exists until you have verified it in the repo.

## Output expectations

- Always list files changed.
- Always list verification commands actually run.
- If a command depends on missing local services, secrets, or containers, say that plainly instead of pretending it passed.
