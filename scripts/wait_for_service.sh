#!/bin/bash
# Poll a service's health endpoints until healthy or a deadline expires.
#
# Usage: wait_for_service.sh <base-url>
#
# Polls <base-url>/health and <base-url>/readiness until both return
# HTTP 200, or until the deadline expires. Exits 0 once healthy,
# exits 1 when the deadline expires first. Every probe uses a short
# per-request timeout so one stuck probe cannot hang the whole wait.
#
# Environment overrides (all optional):
#   WAIT_TIMEOUT_SECS   total deadline in seconds (default 300)
#   WAIT_INTERVAL_SECS  pause between rounds in seconds (default 10)
#   WAIT_CURL_MAX_SECS  per-request timeout in seconds (default 10)

set -euo pipefail

BASE_URL="${1:?Usage: wait_for_service.sh <base-url>}"
TIMEOUT_SECS="${WAIT_TIMEOUT_SECS:-300}"
INTERVAL_SECS="${WAIT_INTERVAL_SECS:-10}"
CURL_MAX_SECS="${WAIT_CURL_MAX_SECS:-10}"

deadline=$((SECONDS + TIMEOUT_SECS))
while true; do
  all_ok=1
  for endpoint in health readiness; do
    status=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$CURL_MAX_SECS" "$BASE_URL/$endpoint" 2>/dev/null || echo "000")
    if [ "$status" = "200" ]; then
      echo "  GET /$endpoint ... $status OK"
    else
      echo "  GET /$endpoint ... $status (retrying)"
      all_ok=0
    fi
  done
  if [ "$all_ok" = "1" ]; then
    echo "Service is healthy: $BASE_URL"
    exit 0
  fi
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "ERROR: service not healthy within ${TIMEOUT_SECS}s: $BASE_URL" >&2
    exit 1
  fi
  sleep "$INTERVAL_SECS"
done
