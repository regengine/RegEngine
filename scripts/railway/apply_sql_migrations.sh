#!/usr/bin/env bash
set -euo pipefail

LEDGER_TABLE="public.schema_migration_files"

usage() {
    cat <<'EOF'
Usage:
  MIGRATIONS_DATABASE_URL=<database_url> bash scripts/railway/apply_sql_migrations.sh <migrations_dir> [glob]

Examples:
  MIGRATIONS_DATABASE_URL="$MIGRATIONS_DATABASE_URL" bash scripts/railway/apply_sql_migrations.sh services/admin/migrations
  MIGRATIONS_DATABASE_URL="$MIGRATIONS_DATABASE_URL" bash scripts/railway/apply_sql_migrations.sh migrations "V*.sql"

The database URL comes from the MIGRATIONS_DATABASE_URL (or DATABASE_URL)
environment variable so it never travels as a process argument. Every applied
file is recorded in public.schema_migration_files; a rerun skips files that
are already recorded, so a batch interrupted halfway can be resumed without
reapplying history.
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
    usage
    exit 1
fi

if [[ "$1" == *"://"* ]]; then
    echo "Pass the database URL with the MIGRATIONS_DATABASE_URL environment variable, not as a command-line argument." >&2
    usage
    exit 1
fi

MIGRATIONS_DIR="$1"
FILE_GLOB="${2:-V*.sql}"

DATABASE_URL="${MIGRATIONS_DATABASE_URL:-${DATABASE_URL:-}}"
if [[ -z "$DATABASE_URL" ]]; then
    echo "MIGRATIONS_DATABASE_URL (or DATABASE_URL) must be set in the environment." >&2
    usage
    exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "psql is required but not found in PATH."
    exit 1
fi

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
    echo "Migration directory not found: $MIGRATIONS_DIR"
    exit 1
fi

CURRENT_ROLE="$(psql "$DATABASE_URL" -XAt -v ON_ERROR_STOP=1 -c 'SELECT current_user')"
if [[ "$CURRENT_ROLE" == "regengine" || "$CURRENT_ROLE" == "regengine_sysadmin" ]]; then
    echo "Refusing DDL with runtime database role: $CURRENT_ROLE" >&2
    exit 1
fi

mapfile -t MIGRATION_FILES < <(find "$MIGRATIONS_DIR" -maxdepth 1 -type f -name "$FILE_GLOB" -print | sort -V)

if [[ ${#MIGRATION_FILES[@]} -eq 0 ]]; then
    echo "No migration files matched '$FILE_GLOB' in $MIGRATIONS_DIR" >&2
    exit 1
fi

psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -c "CREATE TABLE IF NOT EXISTS $LEDGER_TABLE (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"

echo "Applying ${#MIGRATION_FILES[@]} migration file(s) from $MIGRATIONS_DIR"
applied_count=0
skipped_count=0
for file in "${MIGRATION_FILES[@]}"; do
    name="$(basename "$file")"
    already_applied="$(psql "$DATABASE_URL" -XAt -v ON_ERROR_STOP=1 -v ledger_file="$name" -c "SELECT 1 FROM $LEDGER_TABLE WHERE filename = :'ledger_file'")"
    if [[ "$already_applied" == "1" ]]; then
        echo " -- $name (already applied, skipping)"
        skipped_count=$((skipped_count + 1))
        continue
    fi
    echo " -> $name"
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$file"
    psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -v ledger_file="$name" -c "INSERT INTO $LEDGER_TABLE (filename, applied_at) VALUES (:'ledger_file', now()) ON CONFLICT (filename) DO NOTHING"
    applied_count=$((applied_count + 1))
done

echo "Migration batch complete for $MIGRATIONS_DIR (applied: $applied_count, skipped: $skipped_count)"
