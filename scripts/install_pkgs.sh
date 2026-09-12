#!/usr/bin/env bash
# Non-interactive bootstrap for Claude Code sessions.
# Idempotent: safe to run on every SessionStart (startup / resume / clear).
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
    if ! (cd frontend && npm ci --no-audit --no-fund --silent); then
        echo "  [web] npm ci failed (lockfile drift?); falling back to npm install"
        (cd frontend && npm install --no-audit --no-fund --silent)
    fi
fi

# --- .env scaffold ---
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    echo "  [env] copying .env.example -> .env"
    cp .env.example .env
fi

echo "==> bootstrap done"
echo "    next: docker compose -f docker-compose.dev.yml up -d   # requires POSTGRES_PASSWORD"
echo "          source venv/bin/activate && uvicorn server.main:app --reload --port 8000"
