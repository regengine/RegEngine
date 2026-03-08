#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  bash scripts/railway/apply_sql_migrations.sh <database_url> <migrations_dir> [glob]

Examples:
  bash scripts/railway/apply_sql_migrations.sh "$ADMIN_DATABASE_URL" services/admin/migrations
  bash scripts/railway/apply_sql_migrations.sh "$DATABASE_URL" migrations "V*.sql"
EOF
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
    usage
    exit 1
fi

DATABASE_URL="$1"
MIGRATIONS_DIR="$2"
FILE_GLOB="${3:-V*.sql}"

if ! command -v psql >/dev/null 2>&1; then
    echo "psql is required but not found in PATH."
    exit 1
fi

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
    echo "Migration directory not found: $MIGRATIONS_DIR"
    exit 1
fi

mapfile -t MIGRATION_FILES < <(find "$MIGRATIONS_DIR" -maxdepth 1 -type f -name "$FILE_GLOB" -print | sort -V)

if [[ ${#MIGRATION_FILES[@]} -eq 0 ]]; then
    echo "No migration files matched '$FILE_GLOB' in $MIGRATIONS_DIR"
    exit 0
fi

echo "Applying ${#MIGRATION_FILES[@]} migration file(s) from $MIGRATIONS_DIR"
for file in "${MIGRATION_FILES[@]}"; do
    echo " -> $(basename "$file")"
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$file"
done

echo "Migration batch complete for $MIGRATIONS_DIR"
