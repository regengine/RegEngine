#!/usr/bin/env bash
# Non-interactive bootstrap for Claude Code on the web sessions, whose
# containers start without dependencies. Runs on every SessionStart
# (startup / resume / clear). Local sessions skip it: see the guard below.
# For interactive local onboarding, use scripts/setup_dev.sh instead.

set -euo pipefail

# CI guard: this script is wired as a Claude Code SessionStart hook in
# .claude/settings.json. In GitHub Actions (e.g. .github/workflows/sentinel.yml)
# the job checks out untrusted PR-head code, so installing PR-controlled
# lockfiles (pip/npm lifecycle scripts) from a hook would execute that code
# with job secrets in the environment. The audit only reads git history and
# never needs dependencies installed, so bail out early.
if [ -n "${GITHUB_ACTIONS:-}" ] || [ "${REGENGINE_SKIP_SESSION_BOOTSTRAP:-0}" = "1" ]; then
    echo "==> RegEngine session bootstrap skipped (CI / REGENGINE_SKIP_SESSION_BOOTSTRAP=1)"
    exit 0
fi

# Local guard: Claude Code sets CLAUDE_CODE_REMOTE=true only in web (cloud)
# sessions. On a developer machine this hook would rerun `npm ci`, which
# deletes frontend/node_modules (and breaks a running `next dev`), on every
# session start, resume and /clear in every worktree. Set up once with
# scripts/setup_dev.sh, or opt in with REGENGINE_LOCAL_SESSION_BOOTSTRAP=1.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${REGENGINE_LOCAL_SESSION_BOOTSTRAP:-0}" != "1" ]; then
    echo "==> RegEngine session bootstrap skipped (local session; run scripts/setup_dev.sh once, or set REGENGINE_LOCAL_SESSION_BOOTSTRAP=1)"
    exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "==> RegEngine session bootstrap"

# --- Python ---
if [ ! -d "venv" ]; then
    echo "  [py] creating venv/"
    python3 -m venv venv
fi

# shellcheck source=/dev/null
source venv/bin/activate

pip install --quiet --upgrade pip
echo "  [py] installing requirements.lock"
pip install --quiet --require-hashes -r requirements.lock

# --- Frontend ---
if [ -d "frontend" ] && [ -f "frontend/package-lock.json" ]; then
    echo "  [web] installing frontend node_modules"
    # No fallback from locked (npm ci) to unlocked (npm install): an
    # unlocked install can pull dependency versions nobody reviewed.
    # Fail loudly so lockfile drift gets fixed instead of papered over.
    (cd frontend && npm ci --no-audit --no-fund --silent)
fi

# --- .env scaffold ---
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "  [env] copying .env.example -> .env"
    cp .env.example .env
fi

echo "==> bootstrap done"
echo "    next: docker compose -f docker-compose.dev.yml up -d   # requires POSTGRES_PASSWORD"
echo "          source venv/bin/activate && uvicorn server.main:app --reload --port 8000"
