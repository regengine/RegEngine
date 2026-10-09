#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# backup_postgres.sh — Automated PostgreSQL backup with retention (#1003)
#
# Creates gzipped plain-SQL pg_dump backups with timestamped filenames and
# enforces configurable retention (default: 730 days / 24 months, matching the
# FSMA 204 retention requirement — also upload to S3/MinIO for off-site).
#
# FORMAT CONTRACT (#2937): this script emits **plain SQL piped through gzip**,
# so the restore procedure documented in docs/operations/DISASTER_RECOVERY.md
#   gunzip -c <backup>.sql.gz | psql -v ON_ERROR_STOP=1
# consumes it directly. Do not switch to `pg_dump --format=custom` without
# also updating that document — a
# custom-format archive is binary, is not gzip, and only `pg_restore` reads it.
#
# Environment:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE  (standard libpq vars)
#   BACKUP_DIR    — local directory (default: ./backups/postgres)
#   RETENTION_DAYS — days to keep local backups (default: 730)
#   S3_BUCKET     — optional S3/MinIO bucket for off-site archival
#   S3_ENDPOINT   — optional S3 endpoint URL (for MinIO)
#
# Usage:
#   ./scripts/backup_postgres.sh
#   PGDATABASE=regengine ./scripts/backup_postgres.sh
#
# Schedule via APScheduler, cron, or Railway cron job:
#   0 2 * * * /app/scripts/backup_postgres.sh >> /var/log/pg_backup.log 2>&1
# ---------------------------------------------------------------------------
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups/postgres}"
# FSMA 204 requires a 24-month retained record. Defaulting to 30 days meant the
# default configuration destroyed every copy well inside that window (#2937).
RETENTION_DAYS="${RETENTION_DAYS:-730}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_NAME="${PGDATABASE:-regengine}"
DUMP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# Never leave a plausibly-named partial or zero-byte file behind: an operator
# (or an S3 sync) would otherwise count a failed run as a good backup (#2937).
cleanup_failed_dump() {
    local status=$?
    if [ "${status}" -ne 0 ] && [ -e "${DUMP_FILE}" ]; then
        rm -f "${DUMP_FILE}"
        echo "==> Removed incomplete backup ${DUMP_FILE}" >&2
    fi
    return "${status}"
}
trap cleanup_failed_dump EXIT

echo "==> Starting PostgreSQL backup at ${TIMESTAMP}..."
echo "    Database: ${DB_NAME}"
echo "    Target:   ${DUMP_FILE}"

# Create compressed dump. Plain SQL + gzip, matching the documented restore.
# `set -o pipefail` above makes a pg_dump failure fail the whole pipeline.
pg_dump --no-owner --no-privileges "${DB_NAME}" | gzip -9 > "${DUMP_FILE}"

# Verify the artifact before calling it a backup: it must be readable gzip and
# must actually contain a pg_dump plain-SQL stream.
echo "==> Verifying backup integrity..."
if ! gzip -t "${DUMP_FILE}"; then
    echo "ERROR: ${DUMP_FILE} is not valid gzip; refusing to keep it." >&2
    exit 1
fi
# Read the header into a variable first. Piping `gunzip -c` straight into
# `head` breaks under `set -o pipefail` on any real-sized dump: head closes the
# pipe after 20 lines, gunzip is killed by SIGPIPE (exit 141), and pipefail
# propagates that status -- so verification would fail on every genuine backup
# and the EXIT trap would delete it. A tiny fixture never triggers it, because
# gunzip finishes before head exits, which is why the unit tests passed.
DUMP_HEADER="$(gunzip -c "${DUMP_FILE}" 2>/dev/null | head -n 20 || true)"
if ! printf '%s\n' "${DUMP_HEADER}" | grep -q "PostgreSQL database dump"; then
    echo "ERROR: ${DUMP_FILE} does not contain a pg_dump SQL stream." >&2
    exit 1
fi
echo "    Verified: readable gzip containing a pg_dump SQL stream."

FILESIZE=$(du -sh "${DUMP_FILE}" | cut -f1)
echo "==> Backup complete: ${DUMP_FILE} (${FILESIZE})"

# Upload to S3/MinIO if configured
if [ -n "${S3_BUCKET:-}" ]; then
    S3_KEY="postgres/${DB_NAME}_${TIMESTAMP}.sql.gz"
    echo "==> Uploading to s3://${S3_BUCKET}/${S3_KEY}..."

    S3_ARGS=()
    if [ -n "${S3_ENDPOINT:-}" ]; then
        S3_ARGS=(--endpoint-url "${S3_ENDPOINT}")
    fi

    aws s3 cp "${S3_ARGS[@]}" "${DUMP_FILE}" "s3://${S3_BUCKET}/${S3_KEY}"
    echo "==> Off-site upload complete."
else
    echo "==> S3_BUCKET unset: local-only retention of ${RETENTION_DAYS} days."
    echo "    FSMA 204 expects a 24-month off-site record; configure S3_BUCKET."
fi

# Prune old local backups
echo "==> Pruning local backups older than ${RETENTION_DAYS} days..."
PRUNED=$(find "${BACKUP_DIR}" -name "${DB_NAME}_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete | wc -l | tr -d ' ')
echo "    Removed ${PRUNED} old backup(s)."

echo "==> PostgreSQL backup finished successfully."
