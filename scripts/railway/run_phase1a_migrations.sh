#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APPLY_SQL="$SCRIPT_DIR/apply_sql_migrations.sh"

if [[ ! -x "$APPLY_SQL" ]]; then
    echo "Making migration helper executable: $APPLY_SQL"
    chmod +x "$APPLY_SQL"
fi

ADMIN_DB_URL="${ADMIN_DATABASE_URL:-${DATABASE_URL:-}}"
INGESTION_DB_URL="${INGESTION_DATABASE_URL:-${DATABASE_URL:-}}"
COMPLIANCE_DB_URL="${COMPLIANCE_DATABASE_URL:-${DATABASE_URL:-}}"

if [[ -z "$ADMIN_DB_URL" ]]; then
    echo "ADMIN_DATABASE_URL or DATABASE_URL must be set."
    exit 1
fi

if [[ -z "$INGESTION_DB_URL" ]]; then
    echo "INGESTION_DATABASE_URL or DATABASE_URL must be set."
    exit 1
fi

if [[ -z "$COMPLIANCE_DB_URL" ]]; then
    echo "COMPLIANCE_DATABASE_URL or DATABASE_URL must be set."
    exit 1
fi

echo "=== Phase 1A SQL Migration Run ==="
echo "Repo root: $REPO_ROOT"

echo
echo "[1/4] Admin migrations"
bash "$APPLY_SQL" "$ADMIN_DB_URL" "$REPO_ROOT/services/admin/migrations"

echo
echo "[2/4] Ingestion service migrations"
bash "$APPLY_SQL" "$INGESTION_DB_URL" "$REPO_ROOT/services/ingestion/migrations"

echo
echo "[3/4] Root FSMA migrations"
bash "$APPLY_SQL" "$INGESTION_DB_URL" "$REPO_ROOT/migrations"

echo
echo "[4/4] Compliance service migrations"
bash "$APPLY_SQL" "$COMPLIANCE_DB_URL" "$REPO_ROOT/services/compliance/migrations"

echo
echo "All Phase 1A SQL migration batches completed."
echo "If NEO4J_* vars are set, run:"
echo "  python services/graph/scripts/init_db_constraints.py"
