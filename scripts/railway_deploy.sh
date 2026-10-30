#!/usr/bin/env bash
#
# Deploy the RegEngine backend to Railway by CLI, carrying commit identity.
#
# Why this exists: the Railway service has no GitHub source and the GitHub
# Actions deploy workflow (.github/workflows/deploy.yml) is disabled, so
# production is deployed by running `railway up` from a checkout. A bare
# `railway up` ships an image that cannot say which commit it is: the upload
# carries no RAILWAY_GIT_COMMIT_SHA, and build-sha.txt (the stamp that
# services/shared/build_info.py reads) still holds its tracked placeholder.
# /health then answers `build.commit_sha: null` and nobody can tell from
# production which code is serving.
#
# This script:
#   1. refuses a dirty working tree, and refuses a HEAD that is not on
#      origin/main unless --allow-unmerged is passed;
#   2. stamps the full HEAD SHA into build-sha.txt for the upload only, and
#      restores the tracked placeholder afterwards, also on failure;
#   3. runs `railway up --ci` with an explicit service and environment and a
#      deployment message of the form "<commit subject> @<short sha>";
#   4. polls ${BACKEND_URL}/health until .build.commit_sha equals the SHA it
#      shipped, and exits non-zero if that does not happen within the budget.
#
# Usage:
#   scripts/railway_deploy.sh [--allow-unmerged]
#
# Environment:
#   RAILWAY_SERVICE_ID, RAILWAY_ENVIRONMENT_ID
#       Deploy target. When either is unset it is read from `railway status`,
#       which needs a linked project (`railway link`, `railway service`).
#   BACKEND_URL
#       Where to verify. Default https://regengine-production.up.railway.app
#   RAILWAY_DEPLOY_TIMEOUT_SECONDS
#       Rollout budget for the /health check. Default 900, matching deploy.yml.
#   RAILWAY_DEPLOY_POLL_SECONDS
#       Seconds between /health polls. Default 15, matching deploy.yml.
#
# Nothing here prints a token or the value of a Railway variable.

set -euo pipefail

usage() {
  cat <<'EOF'
usage: scripts/railway_deploy.sh [--allow-unmerged]

Deploy the current checkout to Railway with its commit SHA stamped into
build-sha.txt, then wait until /health reports that commit.

  --allow-unmerged   deploy a HEAD that is not on origin/main
  -h, --help         show this help
EOF
}

ALLOW_UNMERGED=0
for arg in "$@"; do
  case "$arg" in
    --allow-unmerged) ALLOW_UNMERGED=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument '$arg'" >&2; usage >&2; exit 2 ;;
  esac
done

for tool in git railway curl jq; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "error: '$tool' is required but not on PATH" >&2
    exit 1
  fi
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
STAMP_FILE="build-sha.txt"
BACKEND_URL="${BACKEND_URL:-https://regengine-production.up.railway.app}"
TIMEOUT_SECONDS="${RAILWAY_DEPLOY_TIMEOUT_SECONDS:-900}"
POLL_SECONDS="${RAILWAY_DEPLOY_POLL_SECONDS:-15}"

# ── 1. Preconditions ─────────────────────────────────────────────────────────
if ! git ls-files --error-unmatch "$STAMP_FILE" >/dev/null 2>&1; then
  echo "error: ${STAMP_FILE} is not tracked. The Dockerfile copies it and build_info.py reads it." >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "error: working tree is dirty. Commit or discard these changes before deploying;" >&2
  echo "       railway up uploads the directory as it is, not the last commit." >&2
  git status --short >&2
  exit 1
fi

HEAD_SHA="$(git rev-parse --verify HEAD)"
SHORT_SHA="$(git rev-parse --short HEAD)"
SUBJECT="$(git log -1 --format=%s HEAD)"

if [ "$ALLOW_UNMERGED" -eq 0 ]; then
  if ! git fetch --quiet origin main; then
    echo "error: could not fetch origin/main to confirm HEAD is merged (pass --allow-unmerged to skip this check)." >&2
    exit 1
  fi
  if ! git merge-base --is-ancestor "$HEAD_SHA" origin/main; then
    echo "error: HEAD ${SHORT_SHA} is not on origin/main." >&2
    echo "       Merge first, or pass --allow-unmerged to deploy an unmerged commit on purpose." >&2
    exit 1
  fi
  if [ "$HEAD_SHA" != "$(git rev-parse origin/main)" ]; then
    echo "note: HEAD ${SHORT_SHA} is on origin/main but behind its tip; deploying the older commit."
  fi
else
  echo "note: --allow-unmerged set; not checking HEAD against origin/main."
fi

# ── 2. Deploy target ─────────────────────────────────────────────────────────
SERVICE_ID="${RAILWAY_SERVICE_ID:-}"
ENVIRONMENT_ID="${RAILWAY_ENVIRONMENT_ID:-}"
SERVICE_SOURCE="RAILWAY_SERVICE_ID"
ENVIRONMENT_SOURCE="RAILWAY_ENVIRONMENT_ID"
if [ -z "$SERVICE_ID" ] || [ -z "$ENVIRONMENT_ID" ]; then
  status_text="$(railway status)" || {
    echo "error: 'railway status' failed. Link the project (railway link) or set RAILWAY_SERVICE_ID and RAILWAY_ENVIRONMENT_ID." >&2
    exit 1
  }
  # `railway status` prints "Environment ID:  <id>" for the linked environment
  # and, under "Linked service", "    service ID:    <id>".
  if [ -z "$ENVIRONMENT_ID" ]; then
    ENVIRONMENT_ID="$(printf '%s\n' "$status_text" | sed -n 's/^Environment ID:[[:space:]]*//p' | head -n 1 | tr -d '[:space:]')"
    ENVIRONMENT_SOURCE="railway status"
  fi
  if [ -z "$SERVICE_ID" ]; then
    SERVICE_ID="$(printf '%s\n' "$status_text" | sed -n 's/^[[:space:]]*service ID:[[:space:]]*//p' | head -n 1 | tr -d '[:space:]')"
    SERVICE_SOURCE="railway status"
  fi
fi
if [ -z "$SERVICE_ID" ] || [ -z "$ENVIRONMENT_ID" ]; then
  echo "error: could not determine the Railway service and environment." >&2
  echo "       Set RAILWAY_SERVICE_ID and RAILWAY_ENVIRONMENT_ID, or link a service with 'railway service'." >&2
  exit 1
fi
echo "target: service from ${SERVICE_SOURCE}, environment from ${ENVIRONMENT_SOURCE}"

# ── 3. Stamp and upload ──────────────────────────────────────────────────────
# The stamp is for the upload only. The tracked file keeps its placeholder so
# a real SHA is never committed; the trap restores it on every exit path.
# shellcheck disable=SC2329  # invoked by the EXIT trap below
restore_stamp() {
  local rc=$?
  if ! git checkout --quiet -- "$STAMP_FILE"; then
    echo "warning: could not restore ${STAMP_FILE}; run: git checkout -- ${STAMP_FILE}" >&2
  fi
  exit "$rc"
}
trap restore_stamp EXIT

printf '%s\n' "$HEAD_SHA" > "$STAMP_FILE"
echo "stamped ${STAMP_FILE} with ${HEAD_SHA}"

MESSAGE="${SUBJECT} @${SHORT_SHA}"
echo "uploading: railway up --ci --message '${MESSAGE}'"
railway up --ci --service "$SERVICE_ID" --environment "$ENVIRONMENT_ID" --message "$MESSAGE"

git checkout --quiet -- "$STAMP_FILE"
echo "restored ${STAMP_FILE} to its tracked placeholder"

# ── 4. Verify the deployed commit is the one we shipped ──────────────────────
# Mirrors the "Verify the deployed commit is the one we shipped" step in
# .github/workflows/deploy.yml. `railway up --ci` returns once the build is
# done, not once the new image is serving. railway.toml sets
# restartPolicyType = "ON_FAILURE" with a /readiness healthcheck, so a rollout
# that fails its healthcheck reverts to the previous image after the upload
# already looked fine. Asserting identity (the served commit) instead of
# behaviour is what closes that hole.
EXPECTED_SHA="$HEAD_SHA"
deadline=$(( SECONDS + TIMEOUT_SECONDS ))
attempt=0
last_sha=""
last_code=""

echo "waiting up to ${TIMEOUT_SECONDS}s for ${BACKEND_URL}/health to report ${EXPECTED_SHA}"
while [ "$SECONDS" -lt "$deadline" ]; do
  attempt=$(( attempt + 1 ))
  body=$(mktemp)
  last_code=$(curl -sS --max-time 20 -o "$body" -w '%{http_code}' "${BACKEND_URL}/health" || true)
  last_code="${last_code:-000}"

  if [ "$last_code" = "200" ]; then
    # `// empty` also covers a payload with no build key at all, which is
    # what an image predating build stamping returns.
    last_sha=$(jq -r '.build.commit_sha // empty' "$body" 2>/dev/null || true)
    if [ "$last_sha" = "$EXPECTED_SHA" ]; then
      rm -f "$body"
      echo "Deployed commit matches: ${EXPECTED_SHA}"
      exit 0
    fi
  fi
  rm -f "$body"

  echo "attempt ${attempt}: status=${last_code} deployed_sha=${last_sha:-(none)} expected=${EXPECTED_SHA}"
  sleep "$POLL_SECONDS"
done

echo "error: deploy did not converge within ${TIMEOUT_SECONDS}s. /health last reported status=${last_code} commit_sha=${last_sha:-(none)}, expected ${EXPECTED_SHA}." >&2
# Three distinct causes, three distinct messages, as in deploy.yml.
if [ "$last_code" != "200" ]; then
  echo "error: /health never returned 200 (last status ${last_code}). The service is not serving; check the Railway deploy logs for a crashed or unhealthy rollout." >&2
elif [ -z "$last_sha" ]; then
  echo "error: /health answered but carried no commit_sha. Either the rollout reverted to an image predating build stamping, or build-sha.txt did not reach the image." >&2
else
  echo "error: a different commit is serving. The rollout reverted (railway.toml restartPolicyType=ON_FAILURE) or another deploy raced this one." >&2
fi
exit 1
