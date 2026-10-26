#!/bin/sh

case "${VERCEL_GIT_COMMIT_REF:-}" in dependabot/*) echo 'Dependabot branch, skipping preview'; exit 0;; esac

if [ "${VERCEL_ENV:-}" = "production" ]; then
  echo "Production build, building"
  exit 1
fi

BASE=""

git fetch --quiet --depth=200 origin main 2>/dev/null || true
BASE="$(git merge-base HEAD FETCH_HEAD 2>/dev/null || true)"
if [ -z "$BASE" ]; then
  if git cat-file -e origin/main^{commit} 2>/dev/null; then
    BASE="origin/main"
  elif git rev-parse --verify origin/main >/dev/null 2>&1; then
    BASE="origin/main"
  fi
fi

if [ -z "$BASE" ]; then
  echo "No base commit found, building"
  exit 1
fi

git diff --quiet "$BASE" HEAD -- .
STATUS=$?

if [ "$STATUS" -eq 0 ]; then
  echo "No frontend changes, skipping"
  exit 0
elif [ "$STATUS" -eq 1 ]; then
  echo "frontend changed, building"
  exit 1
else
  echo "Diff failed, building"
  exit 1
fi
