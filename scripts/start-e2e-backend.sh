#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python runtime not found at $PYTHON_BIN" >&2
  exit 1
fi

shared_db_path="${PLAYWRIGHT_SHARED_DB_PATH:-/tmp/regengine-playwright-shared.db}"
admin_db_path="${PLAYWRIGHT_ADMIN_DB_PATH:-/tmp/regengine-playwright-admin.db}"

if [[ "${PLAYWRIGHT_PRESERVE_LOCAL_DB:-0}" != "1" ]]; then
  rm -f "$shared_db_path" "$admin_db_path"
fi

export REGENGINE_ENV="${REGENGINE_ENV:-development}"
export AUTH_SECRET_KEY="${AUTH_SECRET_KEY:-playwright-local-jwt-signing-key-2026}"
export JWT_SIGNING_KEY="${JWT_SIGNING_KEY:-$AUTH_SECRET_KEY}"
export ADMIN_MASTER_KEY="${ADMIN_MASTER_KEY:-playwright-local-admin-master-key-2026}"
export DATABASE_URL="${DATABASE_URL:-sqlite:///$shared_db_path}"
export ADMIN_FALLBACK_SQLITE="${ADMIN_FALLBACK_SQLITE:-sqlite:///$admin_db_path}"
export DISABLE_TASK_WORKER="${DISABLE_TASK_WORKER:-true}"
export ALLOW_INMEMORY_SESSION_STORE="${ALLOW_INMEMORY_SESSION_STORE:-true}"
export ALLOW_BILLING_STATE_READ_FALLBACK="${ALLOW_BILLING_STATE_READ_FALLBACK:-true}"
export INVITE_BASE_URL="${INVITE_BASE_URL:-http://localhost:3001}"

cd "$ROOT_DIR"
exec "$PYTHON_BIN" -m uvicorn server.main:app --host 127.0.0.1 --port "${PORT:-8000}"
