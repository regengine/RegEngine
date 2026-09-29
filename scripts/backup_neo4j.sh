#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# backup_neo4j.sh — Offline Neo4j backup via neo4j-admin (#2939)
#
# Neo4j Community Edition has no online backup, so this takes the *offline*
# dump whose restore docs/operations/DISASTER_RECOVERY.md (Neo4j section)
# documents:
#
#     neo4j-admin database dump neo4j --to-path=<dir>
#     neo4j-admin database load neo4j --from-path=<dir> --overwrite-destination=true
#
# FORMAT CONTRACT: the artifact is a binary `neo4j-admin` dump named
# `<database>.dump`, written inside a per-run timestamped directory so the
# documented `--from-path=<dir>` restore finds it under the name it expects.
#
# This script previously hand-rolled a `.cypher.gz` export. Nothing could
# restore it: the documented consumer reads only a binary neo4j-admin dump,
# and the generated Cypher was itself unsound — node identity was discarded,
# so relationships were rebuilt by MATCHing non-unique properties
# (fabricating or dropping edges), and temporal values were emitted as bare
# unquoted literals, which is a Cypher syntax error. Do not reintroduce it.
#
# Requirements (either one):
#   - `neo4j-admin` on PATH (Neo4j installed on this host), or
#   - `docker` plus the Neo4j data volume (default: regengine_neo4j_data)
#
# Environment:
#   BACKUP_DIR        — local directory (default: ./backups/neo4j)
#   NEO4J_DATABASE    — database to dump (default: neo4j)
#   NEO4J_DATA_VOLUME — docker volume holding /data (default: regengine_neo4j_data)
#   NEO4J_IMAGE       — image used for the docker path (default: neo4j:5.24-community)
#   NEO4J_COMPOSE_SERVICE — compose service to stop/start (default: neo4j)
#   RETAIN_BACKUPS    — how many dumps to keep (default: 7)
#   SKIP_SERVICE_CONTROL — set to 1 if Neo4j is already stopped
#
# Usage:
#   ./scripts/backup_neo4j.sh
#   BACKUP_DIR=/mnt/backups ./scripts/backup_neo4j.sh
#
# Schedule via APScheduler, cron, or Railway cron job.
# ---------------------------------------------------------------------------
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups/neo4j}"
NEO4J_DATABASE="${NEO4J_DATABASE:-neo4j}"
NEO4J_DATA_VOLUME="${NEO4J_DATA_VOLUME:-regengine_neo4j_data}"
NEO4J_IMAGE="${NEO4J_IMAGE:-neo4j:5.24-community}"
NEO4J_COMPOSE_SERVICE="${NEO4J_COMPOSE_SERVICE:-neo4j}"
RETAIN_BACKUPS="${RETAIN_BACKUPS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# One directory per run, holding `<database>.dump` under the exact name the
# documented `--from-path` restore looks for.
DUMP_DIR="${BACKUP_DIR}/${TIMESTAMP}"
DUMP_FILE="${DUMP_DIR}/${NEO4J_DATABASE}.dump"

mkdir -p "${DUMP_DIR}"

# Community Edition dumps must be taken offline, so this script stops Neo4j
# before dumping. Restarting it therefore cannot live only on the success path:
# a failed dump would otherwise turn one missed nightly backup into an
# indefinite graph-database outage. The trap restarts the service on EVERY exit
# path, and only then cleans up a partial dump.
SERVICE_STOPPED=0

cleanup_failed_dump() {
    local status=$?
    if [ "${SERVICE_STOPPED}" -eq 1 ]; then
        echo "==> Restarting Neo4j (exit status ${status})" >&2
        service_control start || echo "ERROR: failed to restart Neo4j -- it is STILL DOWN." >&2
        SERVICE_STOPPED=0
    fi
    if [ "${status}" -ne 0 ] && [ -d "${DUMP_DIR}" ]; then
        rm -rf "${DUMP_DIR}"
        echo "==> Removed incomplete backup ${DUMP_DIR}" >&2
    fi
    return "${status}"
}
trap cleanup_failed_dump EXIT

echo "==> Starting Neo4j backup at ${TIMESTAMP}..."
echo "    Database: ${NEO4J_DATABASE}"
echo "    Target:   ${DUMP_FILE}"

service_control() {
    # $1 is "stop" or "start"
    if [ "${SKIP_SERVICE_CONTROL:-0}" = "1" ]; then
        return 0
    fi
    if command -v docker >/dev/null 2>&1; then
        echo "==> docker compose ${1} ${NEO4J_COMPOSE_SERVICE}"
        docker compose "${1}" "${NEO4J_COMPOSE_SERVICE}" || true
    fi
}

# Community Edition dumps must be taken offline for a consistent snapshot.
service_control stop
SERVICE_STOPPED=1

if command -v neo4j-admin >/dev/null 2>&1; then
    echo "==> Using local neo4j-admin"
    neo4j-admin database dump "${NEO4J_DATABASE}" --to-path="${DUMP_DIR}"
elif command -v docker >/dev/null 2>&1; then
    echo "==> Using ${NEO4J_IMAGE} against volume ${NEO4J_DATA_VOLUME}"
    docker run --rm \
        -v "${NEO4J_DATA_VOLUME}:/data" \
        -v "$(cd "${DUMP_DIR}" && pwd):/backups" \
        "${NEO4J_IMAGE}" \
        neo4j-admin database dump "${NEO4J_DATABASE}" --to-path=/backups
else
    echo "ERROR: neither neo4j-admin nor docker is available; cannot take a dump." >&2
    exit 1
fi

service_control start
SERVICE_STOPPED=0

# Verify the artifact before calling it a backup.
echo "==> Verifying backup..."
if [ ! -s "${DUMP_FILE}" ]; then
    echo "ERROR: expected a non-empty dump at ${DUMP_FILE}; none was produced." >&2
    exit 1
fi
echo "    Verified: ${DUMP_FILE} exists and is non-empty."

echo "==> Backup complete: ${DUMP_FILE}"
echo "    Size: $(du -h "${DUMP_FILE}" | cut -f1)"

# Cleanup old backups (keep the most recent RETAIN_BACKUPS run directories)
echo "==> Cleaning up old backups (keeping last ${RETAIN_BACKUPS})..."
# shellcheck disable=SC2012
ls -1d "${BACKUP_DIR}"/*/ 2>/dev/null \
    | sort -r \
    | tail -n "+$((RETAIN_BACKUPS + 1))" \
    | xargs -r rm -rf

echo "==> Restore with:"
echo "    neo4j-admin database load ${NEO4J_DATABASE} --from-path=${DUMP_DIR} --overwrite-destination=true"
