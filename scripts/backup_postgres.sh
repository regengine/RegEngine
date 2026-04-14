#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# backup_postgres.sh — Automated PostgreSQL backup with retention (#1003)
#
# Creates compressed pg_dump backups with timestamped filenames and enforces
# configurable retention (default: 30 days local, FSMA 204 requires 24-month
# off-site — upload to S3/MinIO for compliance).
#
# Environment:
#   PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE  (standard libpq vars)
#   BACKUP_DIR    — local directory (default: ./backups/postgres)
#   RETENTION_DAYS — days to keep local backups (default: 30)
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
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_NAME="${PGDATABASE:-regengine}"
DUMP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql.gz"

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

echo "==> Starting PostgreSQL backup at ${TIMESTAMP}..."
echo "    Database: ${DB_NAME}"
echo "    Target:   ${DUMP_FILE}"

# Create compressed dump
pg_dump --format=custom --compress=9 --no-owner --no-privileges \
    "${DB_NAME}" > "${DUMP_FILE}"

FILESIZE=$(du -sh "${DUMP_FILE}" | cut -f1)
echo "==> Backup complete: ${DUMP_FILE} (${FILESIZE})"

# Upload to S3/MinIO if configured
if [ -n "${S3_BUCKET:-}" ]; then
    S3_KEY="postgres/${DB_NAME}_${TIMESTAMP}.sql.gz"
    echo "==> Uploading to s3://${S3_BUCKET}/${S3_KEY}..."

    S3_ARGS=""
    if [ -n "${S3_ENDPOINT:-}" ]; then
        S3_ARGS="--endpoint-url ${S3_ENDPOINT}"
    fi

    aws s3 cp ${S3_ARGS} "${DUMP_FILE}" "s3://${S3_BUCKET}/${S3_KEY}"
    echo "==> Off-site upload complete."
fi

# Prune old local backups
echo "==> Pruning local backups older than ${RETENTION_DAYS} days..."
PRUNED=$(find "${BACKUP_DIR}" -name "${DB_NAME}_*.sql.gz" -mtime "+${RETENTION_DAYS}" -print -delete | wc -l | tr -d ' ')
echo "    Removed ${PRUNED} old backup(s)."

echo "==> PostgreSQL backup finished successfully."
