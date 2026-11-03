#!/usr/bin/env bash
# Fail the secrets gate only on *new* findings (detect-secrets-hook exit 1).
# Exit 3 is baseline line-number/metadata drift with no new secrets — treat as pass.
# Filenames are forwarded after "--" so names like --version are scanned, not parsed.
set -euo pipefail

if [ "$#" -eq 0 ]; then
  # Probe first so a failing git ls-files never becomes an empty pass.
  set +e
  git ls-files >/dev/null
  git_status=$?
  set -e
  if [ "$git_status" -ne 0 ]; then
    echo "::error::check_secrets_baseline: git ls-files failed (exit ${git_status}); cannot build file list" >&2
    exit 2
  fi
  # NUL-delimited so non-ASCII / unusual pathnames reach the hook byte-for-byte.
  files=()
  while IFS= read -r -d '' f; do
    files+=("$f")
  done < <(git ls-files -z)
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
# Capture combined output so exit 1 can distinguish findings from baseline/setup errors.
hook_output="$(
  detect-secrets-hook \
    --baseline "$tmp" \
    --exclude-files ".*\.lock$" \
    --exclude-files ".*package-lock\.json$" \
    --exclude-files "\.secrets\.baseline$" \
    -- \
    "$@" 2>&1
)"
status=$?
set -e

if [ -n "$hook_output" ]; then
  printf '%s\n' "$hook_output"
fi

if [ "$status" -eq 0 ]; then
  exit 0
elif [ "$status" -eq 3 ]; then
  echo "detect-secrets: only baseline line-number/metadata drift, no new secrets"
  exit 0
elif [ "$status" -eq 1 ]; then
  # detect-secrets 1.5.0 also returns 1 for argparse/baseline ValueErrors before scanning.
  if printf '%s' "$hook_output" | grep -qiE \
    'baseline file .* is unstaged|not a valid baseline|Unable to load|Invalid baseline|Error loading baseline|baseline.*(invalid|error)'; then
    echo "::error::check_secrets_baseline: detect-secrets baseline/setup error (exit 1), not a new-secret finding" >&2
    exit 2
  fi
  echo "::error::detect-secrets found secrets not in .secrets.baseline"
  exit 1
else
  echo "::error::detect-secrets-hook failed with exit code ${status} (tool or setup error, not a new-secret finding)"
  exit "$status"
fi
