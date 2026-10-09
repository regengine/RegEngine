#!/usr/bin/env bash
# check_repo_freshness.sh — CI-gate L0 preflight.
# Fails loudly when the working clone's main is >N commits behind origin/main,
# so nobody tests, guards, or merges against a stale tree (see ledger:
# the 22-test contaminated-baseline cluster came from exactly this).
#
# Usage: check_repo_freshness.sh [MAX_BEHIND] [--skip-fetch]
#   MAX_BEHIND   allowed commit gap (default 10; env FRESHNESS_MAX_BEHIND wins)
#   --skip-fetch use local refs only (offline)
# Exit: 0 fresh · 1 stale (prints pull instruction) · 2 usage/git error
set -euo pipefail
MAX_BEHIND="${FRESHNESS_MAX_BEHIND:-10}"
SKIP_FETCH=0
for a in "$@"; do
  case "$a" in
    --skip-fetch) SKIP_FETCH=1 ;;
    *[!0-9]*|'') echo "usage: $0 [MAX_BEHIND] [--skip-fetch]" >&2; exit 2 ;;
    *) MAX_BEHIND="$a" ;;
  esac
done
# Validate after parsing: the env default above bypasses the loop's digit
# check, so an unvalidated value would break the -gt comparison below.
case "$MAX_BEHIND" in
  ''|*[!0-9]*) echo "usage: $0 [MAX_BEHIND] [--skip-fetch]" >&2; echo "FRESHNESS FAIL: invalid MAX_BEHIND '$MAX_BEHIND': must be a non-negative integer" >&2; exit 2 ;;
esac
git rev-parse --git-dir >/dev/null 2>&1 || { echo "FRESHNESS FAIL: not a git repo" >&2; exit 2; }
if [ "$SKIP_FETCH" -eq 0 ]; then
  git fetch --quiet origin main || { echo "FRESHNESS FAIL: cannot fetch origin main (offline? use --skip-fetch)" >&2; exit 2; }
fi
LOCAL=$(git rev-parse --verify --quiet main) || { echo "FRESHNESS FAIL: no local main branch (cannot compare against origin/main)" >&2; exit 2; }
REMOTE=$(git rev-parse --verify --quiet origin/main) || { echo "FRESHNESS FAIL: no origin/main ref" >&2; exit 2; }
BEHIND=$(git rev-list --count "$LOCAL..$REMOTE")
if [ "$BEHIND" -gt "$MAX_BEHIND" ]; then
  echo "FRESHNESS FAIL: local main is $BEHIND commits behind origin/main (allowed $MAX_BEHIND)." >&2
  echo "  Fix: git pull --ff-only origin main   (then re-run your command)" >&2
  exit 1
fi
echo "FRESHNESS OK: $BEHIND behind origin/main (allowed $MAX_BEHIND)"
