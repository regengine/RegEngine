# Suggested RegEngine sections for `~/.claude/CLAUDE.md`

The user-level global CLAUDE.md is stale for this repo (old path, 6-microservice
topology, `uv`, overmind/direnv aliases). Below are drop-in replacement sections,
verified against `docs/CODEBASE_MAP.md` (project level) and the repo's CI/pre-commit
configs as of 2026-06-10. This file is a suggestion only — nothing here edits the
user's home directory.

---

## Who I am (RegEngine line — replace)

- Primary codebase: **RegEngine** (`~/Projects/RegEngine/repo`) — a single consolidated
  FastAPI monolith (`server/main.py`) deployed as one Docker image on Railway, plus a
  Next.js 16 frontend on Vercel. The `services/` directories are code-organization
  seams (router domains: ingestion, admin, graph, nlp, fsma_compliance), not separate
  deployments. `graph` and `nlp` routers are experimental-gated off in production;
  the scheduler runs embedded in the monolith lifespan
  (`server/workers/embedded_scheduler.py`, advisory-lock leader election; see
  `ASYNC_PROCESSES.md` lines 65+).

## Stack defaults (RegEngine — replace)

- Python deps: **pip-tools**, not `uv`. One venv at the repo root
  (`python3 -m venv venv && source venv/bin/activate`), install with
  `pip install --require-hashes -r requirements.lock`. Dependency edits go in
  `requirements.in`; regenerate with
  `pip-compile --allow-unsafe --generate-hashes --output-file=requirements.lock requirements.in`
  (CI fails on a stale lock). Per-service `requirements.txt` files are deprecated (#1429).
- Lint/format: `ruff` + `ruff-format` via pre-commit (`pre-commit install` once per
  clone). CI's hard lint gate is `ruff check --select E9,F63,F7,F82`.
- Tests: `pytest` from the repo root (root `conftest.py` handles per-service `app/`
  package switching). CI runs a per-service matrix with coverage floors plus a full
  ingestion suite under pytest-xdist. Some suites (tests/migrations/) self-provision
  Postgres via testcontainers — Docker required.
- Local Postgres: `docker compose -f docker-compose.dev.yml up -d` (port 5432).
- Local dev server: `uvicorn server.main:app --reload --port 8000`.
  There is **no Procfile.dev, no overmind, no `.envrc`/direnv** in this repo —
  the `regdev`/`regstop`/`reghealth` aliases and the "Procfile.dev uses `python`"
  design-decision note do not apply here.
- Migrations: alembic, single linear chain, run by `scripts/run-migrations.sh` under an
  advisory lock before the app starts in the Docker image.
- Async work: PostgreSQL task queue (`fsma.task_queue`, polled by workers started in
  the FastAPI lifespan). `EVENT_BACKBONE=pg` by default; Kafka is opt-in legacy.

## Deployment (replace)

- Backend: Railway, **one service** (monolith image from the repo-root Dockerfile,
  healthcheck `/readiness`). Deploys are manual: GitHub Actions `deploy.yml`
  (workflow_dispatch) waits for a green "CI Status Gate" check, then `railway up --ci`.
- Frontend: Vercel.
- Before pushing: `pre-commit run` on changed files + `pytest -x` on affected suites.

## Security (correction)

- Pre-commit hooks here are: ruff, ruff-format, standard hygiene hooks,
  `detect-private-key`, and `detect-secrets` (vs `.secrets.baseline`).
  **gitleaks is not a pre-commit hook in this repo** — it runs in CI
  (`.github/workflows/security.yml`).

## Skills caveat

- The `regengine-service-runner` skill (per-service ports/uvicorn commands) describes
  the retired multi-service topology; prefer the monolith commands above until the
  skill is updated.
