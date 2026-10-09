#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_PYTHON_BIN="$ROOT_DIR/venv/bin/python"

resolve_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if [[ -x "$PYTHON_BIN" ]] || command -v "$PYTHON_BIN" >/dev/null 2>&1; then
      printf '%s\n' "$PYTHON_BIN"
      return 0
    fi

    echo "Python runtime not found at $PYTHON_BIN" >&2
    return 1
  fi

  if [[ -x "$DEFAULT_PYTHON_BIN" ]]; then
    printf '%s\n' "$DEFAULT_PYTHON_BIN"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi

  echo "Python runtime not found at $DEFAULT_PYTHON_BIN and python3 is not on PATH" >&2
  return 1
}

PYTHON_BIN="$(resolve_python_bin)" || {
  exit 1
}

shared_db_path="${PLAYWRIGHT_SHARED_DB_PATH:-/tmp/regengine-playwright-shared.db}"
admin_db_path="${PLAYWRIGHT_ADMIN_DB_PATH:-/tmp/regengine-playwright-admin.db}"

if [[ "${PLAYWRIGHT_PRESERVE_LOCAL_DB:-0}" != "1" ]]; then
  echo "warning: start-e2e-backend.sh deleting fixture databases: $shared_db_path $admin_db_path (set PLAYWRIGHT_PRESERVE_LOCAL_DB=1 to keep them)" >&2
  rm -f "$shared_db_path" "$admin_db_path"
fi

export REGENGINE_ENV="${REGENGINE_ENV:-development}"

case "${REGENGINE_ENV}" in
  development|test)
    ;;
  *)
    if [[ -z "${AUTH_SECRET_KEY:-}" && -z "${JWT_SIGNING_KEY:-}" ]]; then
      echo "error: REGENGINE_ENV=${REGENGINE_ENV} requires an explicit AUTH_SECRET_KEY or JWT_SIGNING_KEY; refusing to start with the local fixture default" >&2
      exit 1
    fi
    ;;
esac

if [[ "${REGENGINE_ENV}" == "development" || "${REGENGINE_ENV}" == "test" ]]; then
  export AUTH_SECRET_KEY="${AUTH_SECRET_KEY:-playwright-local-jwt-signing-key-2026}"
  export JWT_SIGNING_KEY="${JWT_SIGNING_KEY:-$AUTH_SECRET_KEY}"
else
  export AUTH_SECRET_KEY="${AUTH_SECRET_KEY:-$JWT_SIGNING_KEY}"
  export JWT_SIGNING_KEY="${JWT_SIGNING_KEY:-$AUTH_SECRET_KEY}"
fi
export DATABASE_URL="${DATABASE_URL:-sqlite:///$shared_db_path}"
export ADMIN_FALLBACK_SQLITE="${ADMIN_FALLBACK_SQLITE:-sqlite:///$admin_db_path}"
export DISABLE_TASK_WORKER="${DISABLE_TASK_WORKER:-true}"
export ALLOW_INMEMORY_SESSION_STORE="${ALLOW_INMEMORY_SESSION_STORE:-true}"
export ALLOW_BILLING_STATE_READ_FALLBACK="${ALLOW_BILLING_STATE_READ_FALLBACK:-true}"
export INVITE_BASE_URL="${INVITE_BASE_URL:-http://localhost:3001}"

cd "$ROOT_DIR"
exec "$PYTHON_BIN" -m uvicorn server.main:app --host 127.0.0.1 --port "${PORT:-8000}"
