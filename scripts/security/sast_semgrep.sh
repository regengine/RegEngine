#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------
# SAST Script (Semgrep)
# Runs Semgrep with OWASP Top 10 and security audit rulesets.
# For CI usage, see .github/workflows/security.yml
# ---------------------------------------------------

echo "=========================================="
echo "  RegEngine SAST Scan (Semgrep)"
echo "=========================================="

if ! command -v semgrep &> /dev/null; then
  echo "semgrep not installed. Run: pip install semgrep"
  exit 1
fi

OUTPUT_FILE="${1:-semgrep-results.json}"

set +e
semgrep \
  --config p/owasp-top-ten \
  --config p/security-audit \
  --json --output "$OUTPUT_FILE" \
  --error

EXIT_CODE=$?
set -e

echo "Results written to: $OUTPUT_FILE"

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "FAIL: Semgrep found security issues. Review $OUTPUT_FILE"
  exit 1
fi

echo "PASS: Semgrep scan completed with no findings."
exit 0
