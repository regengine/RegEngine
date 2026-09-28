#!/usr/bin/env bash
# One-command bootstrap of a FRESH RegEngine staging database on Railway.
#
#   bash scripts/railway/bootstrap_staging_database.sh            # dry run (default)
#   bash scripts/railway/bootstrap_staging_database.sh --apply    # execute
#   bash scripts/railway/bootstrap_staging_database.sh --apply --redeploy
#   ... --rotate-passwords        set new passwords for existing roles (then redeploy)
#   ... --adopt-existing-roles    change pre-existing roles used outside the target DB
#
# Requires: Railway CLI >= 5.47.2 (logged in), psql, python3 (stdlib only).
# Refuses any environment other than exactly `staging`.
# Thin wrapper: the logic and its docs live in bootstrap_staging_database.py;
# the procedure is described in docs/operations/DATABASE_ROLE_CUTOVER.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "python3 is required but not found in PATH." >&2
    exit 69  # EX_UNAVAILABLE
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/bootstrap_staging_database.py" "$@"
