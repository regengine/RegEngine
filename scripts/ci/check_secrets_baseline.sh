#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -eq 0 ]; then
  set +e
  file_list="$(git ls-files)"
  git_status=$?
  set -e
  if [ "$git_status" -ne 0 ]; then
    echo "::error::check_secrets_baseline: git ls-files failed (exit ${git_status}); cannot build file list" >&2
    exit 2
  fi
  if [ -z "$file_list" ]; then
    echo "::error::check_secrets_baseline: git ls-files returned no files; refusing to pass an empty scan" >&2
    exit 2
  fi
  files=()
  while IFS= read -r f || [ -n "$f" ]; do
    [ -n "$f" ] && files+=("$f")
  done <<< "$file_list"
  if [ "${#files[@]}" -eq 0 ]; then
    echo "::error::check_secrets_baseline: git ls-files returned no files; refusing to pass an empty scan" >&2
    exit 2
  fi
  set -- "${files[@]}"
fi

if ! command -v detect-secrets-hook >/dev/null 2>&1; then
  echo "::error::check_secrets_baseline: detect-secrets-hook not found; install detect-secrets==1.5.0" >&2
  exit 127
fi

if [ ! -f .secrets.baseline ] || [ ! -r .secrets.baseline ]; then
  echo "::error::check_secrets_baseline: setup-error in step '.secrets.baseline': .secrets.baseline is missing or unreadable (setup error)" >&2
  exit 2
fi

if ! tmp="$(mktemp 2>/dev/null)" || [ -z "$tmp" ]; then
  echo "::error::check_secrets_baseline: setup-error in step 'mktemp': mktemp failed (setup error)" >&2
  exit 2
fi
trap 'rm -f "$tmp"' EXIT

if ! cp .secrets.baseline "$tmp" 2>/dev/null; then
  echo "::error::check_secrets_baseline: setup-error in step 'cp': cp failed (setup error)" >&2
  exit 2
fi

set +e
detect-secrets-hook --baseline "$tmp" --exclude-files ".*\.lock$" --exclude-files ".*package-lock\.json$" --exclude-files "\.secrets\.baseline$" "$@"
status=$?
set -e

if [ "$status" -eq 0 ]; then
  exit 0
elif [ "$status" -eq 3 ]; then
  echo "detect-secrets: only baseline line-number/metadata drift, no new secrets"
  exit 0
elif [ "$status" -eq 1 ]; then
  echo "::error::detect-secrets found secrets not in .secrets.baseline"
  exit 1
else
  echo "::error::detect-secrets-hook failed with exit code ${status} (tool or setup error, not a new-secret finding)"
  exit "$status"
fi
