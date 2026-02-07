#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------
# Secrets Scan Script (gitleaks)
# Scans the repository for hardcoded secrets and credentials.
# For CI usage, see .github/workflows/security.yml
# ---------------------------------------------------

echo "=========================================="
echo "  RegEngine Secrets Scan (gitleaks)"
echo "=========================================="

if ! command -v gitleaks &> /dev/null; then
  echo "gitleaks not installed."
  echo "Install via: brew install gitleaks  (macOS)"
  echo "         or: go install github.com/gitleaks/gitleaks/v8@latest"
  exit 1
fi

REPORT_FILE="${1:-gitleaks-report.json}"

set +e
gitleaks detect \
  --source . \
  --report-path "$REPORT_FILE" \
  --report-format json \
  --verbose

EXIT_CODE=$?
set -e

echo "Results written to: $REPORT_FILE"

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "FAIL: gitleaks found secrets in the repository. Review $REPORT_FILE"
  exit 1
fi

echo "PASS: No secrets detected."
exit 0
