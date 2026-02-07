#!/usr/bin/env bash
set -euo pipefail

mkdir -p artifacts/tenant-isolation

echo "=========================================="
echo "  RegEngine Tenant Isolation Test Suite"
echo "=========================================="

# ---------------------------------------------------
# This script runs the existing tenant isolation and
# security test suite located in tests/security/.
#
# Tests cover:
#   1. Cross-tenant data access (Tenant A cannot read Tenant B's data)
#   2. API key scoping (key for Tenant A rejects Tenant B endpoints)
#   3. Input validation (SQL injection, XSS, oversized requests)
#   4. Session/token isolation (JWT tenant claim validation)
#   5. IDOR checks on all entity endpoints
#   6. Error handling (no stack trace / path leakage)
# ---------------------------------------------------

TEST_DIR="tests/security"
RESULTS_FILE="artifacts/tenant-isolation/results.json"

if [ ! -d "$TEST_DIR" ]; then
  echo "ERROR: Test directory '$TEST_DIR' not found."
  echo "Expected tests at: $TEST_DIR/test_tenant_isolation.py"
  exit 1
fi

echo "Running tenant isolation tests from $TEST_DIR ..."
python -m pytest "$TEST_DIR" \
  -v \
  --tb=short \
  --json-report \
  --json-report-file="$RESULTS_FILE" \
  2>&1 | tee artifacts/tenant-isolation/output.log

EXIT_CODE=${PIPESTATUS[0]}

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "FAIL: Tenant isolation tests failed. See $RESULTS_FILE"
  exit 1
fi

echo "PASS: All tenant isolation tests passed."
exit 0
