#!/usr/bin/env bash
# Hand-run production deploy that stamps the commit the same way
# .github/workflows/deploy.yml does.
#
# Why this exists: the image has no .git (.dockerignore excludes it), so the
# only way /health can report which commit is serving is the build-sha.txt
# the Dockerfile copies to /app/build-sha.txt. The tracked file is the
# placeholder "unknown" so a plain checkout never carries a stale SHA. The
# workflow overwrites it with github.sha before `railway up`; a bare
# `railway up` from a laptop ships the placeholder and /health answers
# commit_sha: null (that is what the 2026-10-29 deploy did). This script
# closes that gap for manual deploys:
#
#   1. refuse to run with a dirty working tree
#   2. write `git rev-parse HEAD` into build-sha.txt
#   3. `railway up --ci` against the linked Railway service
#   4. restore the placeholder (also on failure, via trap)
#   5. poll /health until build.commit_sha equals the stamped SHA
#
# Usage:
#   scripts/railway/deploy_prod.sh            # real deploy
#   scripts/railway/deploy_prod.sh --dry-run  # everything except railway up
#                                             # and the health poll
#
# Environment (all optional):
#   BACKEND_URL           health base URL   (default https://api.regengine.co)
#   RAILWAY_SERVICE       passed as `railway up --service` when set
#   RAILWAY_ENVIRONMENT   passed as `railway up --environment` when set
#   DEPLOY_TIMEOUT_SECS   health poll budget (default 900, mirrors deploy.yml)
set -euo pipefail

PLACEHOLDER="unknown"
STAMP_FILE="build-sha.txt"
BACKEND_URL="${BACKEND_URL:-https://api.regengine.co}"
DEPLOY_TIMEOUT_SECS="${DEPLOY_TIMEOUT_SECS:-900}"
DRY_RUN=0

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help)
            sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "error: unknown argument: $arg (try --help)" >&2
            exit 2
            ;;
    esac
done

die() {
    echo "error: $*" >&2
    exit 1
}

command -v git >/dev/null 2>&1 || die "git is required but not found in PATH"

# Everything below runs from the repository root: the Dockerfile and the
# stamp file live there, and `railway up` uploads the current directory.
repo_root="$(git rev-parse --show-toplevel 2>/dev/null)" || die "not inside a git checkout"
cd "$repo_root"

# `railway up` indexes the upload relative to the git toplevel and fails with
# "Indexing... prefix not found" when `.git` is a worktree pointer file instead
# of a directory (observed 2026-10-29). Refuse here rather than after stamping.
if [ ! -d "$repo_root/.git" ]; then
    die "$repo_root is a git worktree (.git is a file). \`railway up\` cannot index a worktree; run this from the primary checkout."
fi

# --- Preconditions. Nothing is touched until all of these pass. -------------

dirty="$(git status --porcelain --untracked-files=all)"
if [ -n "$dirty" ]; then
    echo "error: working tree is not clean. A deploy must ship exactly one" >&2
    echo "commit, and \`railway up\` uploads whatever is on disk, tracked or not." >&2
    echo "Commit, discard, or move these first:" >&2
    printf '%s\n' "$dirty" >&2
    exit 1
fi

[ -f "$STAMP_FILE" ] || die "$STAMP_FILE is missing from the checkout"
if [ "$(cat "$STAMP_FILE")" != "$PLACEHOLDER" ]; then
    die "$STAMP_FILE is tracked as '$(cat "$STAMP_FILE")', expected the placeholder '$PLACEHOLDER'. Fix the tracked file before deploying."
fi

if [ "$DRY_RUN" -eq 0 ]; then
    for tool in railway curl jq; do
        command -v "$tool" >/dev/null 2>&1 || die "$tool is required but not found in PATH"
    done
fi

sha="$(git rev-parse HEAD)"
branch="$(git rev-parse --abbrev-ref HEAD)"

echo "checkout:  $repo_root"
echo "branch:    $branch"
echo "commit:    $sha"
if [ "$branch" != "main" ]; then
    echo "warning: HEAD is not on main. Production normally ships main; continuing because you asked." >&2
fi

# --- Stamp, with a trap so the placeholder always comes back. ----------------

restore_stamp() {
    # `git checkout --` restores the exact tracked bytes, which is what keeps
    # `git status` clean afterwards. The printf fallback covers a checkout
    # whose index is unreadable mid-failure.
    git checkout --quiet -- "$STAMP_FILE" 2>/dev/null || printf '%s\n' "$PLACEHOLDER" > "$STAMP_FILE"
}
trap restore_stamp EXIT

printf '%s\n' "$sha" > "$STAMP_FILE"
echo "stamped:   $STAMP_FILE = $(cat "$STAMP_FILE")"

# --- Deploy. -----------------------------------------------------------------

up_args=(up --ci)
[ -n "${RAILWAY_SERVICE:-}" ] && up_args+=(--service "$RAILWAY_SERVICE")
[ -n "${RAILWAY_ENVIRONMENT:-}" ] && up_args+=(--environment "$RAILWAY_ENVIRONMENT")

if [ "$DRY_RUN" -eq 1 ]; then
    echo "dry run:   would run: railway ${up_args[*]}"
    echo "dry run:   would poll ${BACKEND_URL}/health for build.commit_sha == $sha (budget ${DEPLOY_TIMEOUT_SECS}s)"
    restore_stamp
    trap - EXIT
    if [ -n "$(git status --porcelain --untracked-files=all)" ]; then
        die "dry run left the tree dirty; this is a bug in $0"
    fi
    echo "restored:  $STAMP_FILE = $(cat "$STAMP_FILE"); git status clean"
    exit 0
fi

echo "target:"
railway status || die "railway status failed. Run \`railway login\` and \`railway link\` first."

railway "${up_args[@]}"

# Restore as soon as the upload is accepted; the trap is only the safety net.
restore_stamp
trap - EXIT
echo "restored:  $STAMP_FILE = $(cat "$STAMP_FILE")"

# --- Verify identity, not behaviour (mirrors deploy.yml). --------------------
#
# `railway up --ci` returns once the upload is accepted, not once the new
# image is serving. railway.toml sets restartPolicyType = "ON_FAILURE" with a
# /readiness healthcheck, so a rollout that fails its healthcheck reverts to
# the previous image after this script would otherwise have exited 0. The
# only check that cannot be satisfied by an older image is the commit itself.

deadline=$(( SECONDS + DEPLOY_TIMEOUT_SECS ))
attempt=0
last_sha=""
last_code=""

while [ "$SECONDS" -lt "$deadline" ]; do
    attempt=$(( attempt + 1 ))
    body="$(mktemp)"
    last_code="$(curl -sS --max-time 20 -o "$body" -w '%{http_code}' "${BACKEND_URL}/health" || true)"
    last_code="${last_code:-000}"

    if [ "$last_code" = "200" ]; then
        # `// empty` also covers a payload with no build key at all, which is
        # what an image predating build stamping returns.
        last_sha="$(jq -r '.build.commit_sha // empty' "$body" 2>/dev/null || true)"
        if [ "$last_sha" = "$sha" ]; then
            rm -f "$body"
            echo "deployed:  ${BACKEND_URL}/health reports commit_sha $sha"
            exit 0
        fi
    fi
    rm -f "$body"

    echo "attempt ${attempt}: status=${last_code} deployed_sha=${last_sha:-(none)} expected=${sha}"
    sleep 15
done

echo "error: deploy did not converge within ${DEPLOY_TIMEOUT_SECS}s. /health last reported status=${last_code} commit_sha=${last_sha:-(none)}, expected ${sha}." >&2
if [ "$last_code" != "200" ]; then
    echo "error: /health never returned 200 (last status ${last_code}). The service is not serving; check the Railway deploy logs for a crashed or unhealthy rollout." >&2
elif [ -z "$last_sha" ]; then
    echo "error: /health answered but carried no commit_sha. Either the rollout reverted to an image predating build stamping, or build-sha.txt did not reach the image." >&2
else
    echo "error: a different commit is serving. The rollout reverted (railway.toml restartPolicyType=ON_FAILURE) or another deploy raced this one." >&2
fi
exit 1
