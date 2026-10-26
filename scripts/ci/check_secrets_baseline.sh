#!/usr/bin/env bash
set -euo pipefail

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

cp .secrets.baseline "$tmp"

if [ "$#" -eq 0 ]; then
  if type mapfile >/dev/null 2>&1; then
    mapfile -t files < <(git ls-files)
  else
    files=()
    while IFS= read -r f; do
      [ -n "$f" ] && files+=("$f")
    done < <(git ls-files)
  fi
  if [ "${#files[@]}" -gt 0 ]; then
    set -- "${files[@]}"
  fi
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
else
  echo "::error::detect-secrets found secrets not in .secrets.baseline"
  exit "$status"
fi
