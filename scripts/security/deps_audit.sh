#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------
# Dependency Audit Script
# Runs npm audit (Node) and pip-audit (Python) locally.
# For CI usage, see .github/workflows/security.yml
# ---------------------------------------------------

echo "=========================================="
echo "  RegEngine Dependency Audit"
echo "=========================================="

EXIT_CODE=0

# ---- Node (if present) ----
if [ -f package-lock.json ] || [ -f package.json ]; then
  echo ""
  echo "--- npm audit ---"
  npm audit --audit-level=moderate || EXIT_CODE=1
else
  echo "No Node project detected. Skipping npm audit."
fi

# ---- Python (if present) ----
if command -v pip-audit &> /dev/null; then
  echo ""
  echo "--- pip-audit ---"
  # Prefer the pip-compile lockfile (pinned + hashed, #1139). Fall back to
  # legacy requirements.txt if a branch predates the migration, then pyproject.
  if [ -f requirements.lock ]; then
    pip-audit -r requirements.lock || EXIT_CODE=1
  elif [ -f requirements.txt ]; then
    pip-audit -r requirements.txt || EXIT_CODE=1
  elif [ -f pyproject.toml ]; then
    pip-audit || EXIT_CODE=1
  else
    echo "No Python deps file detected. Skipping pip-audit."
  fi
else
  echo "pip-audit not installed. Run: pip install pip-audit"
fi

if [ "$EXIT_CODE" -ne 0 ]; then
  echo ""
  echo "FAIL: Dependency audit found issues. Review output above."
  exit 1
fi

echo ""
echo "PASS: Dependency audit completed with no issues."
exit 0
