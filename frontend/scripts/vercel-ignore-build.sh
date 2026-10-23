#!/bin/sh

if [ "${VERCEL_ENV:-}" = "production" ]; then
  echo "Production build, building"
  exit 1
fi

BASE=""

if [ -n "${VERCEL_GIT_PREVIOUS_SHA:-}" ]; then
  if git cat-file -e "${VERCEL_GIT_PREVIOUS_SHA}^{commit}" 2>/dev/null; then
    BASE="$VERCEL_GIT_PREVIOUS_SHA"
  fi
fi

if [ -z "$BASE" ]; then
  git fetch --quiet --depth=100 origin main 2>/dev/null || true
  BASE="$(git merge-base HEAD FETCH_HEAD 2>/dev/null || true)"
  if [ -z "$BASE" ]; then
    if git cat-file -e origin/main^{commit} 2>/dev/null; then
      BASE="origin/main"
    elif git rev-parse --verify origin/main >/dev/null 2>&1; then
      BASE="origin/main"
    fi
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
