#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---source}"
case "$MODE" in
  --staging)
    shift
    exec python3 scripts/security/staging_release_gate.py "$@"
    ;;
  --source)
    shift
    ;;
  *)
    echo "Usage: $0 [--source | --staging --plan PLAN.json --confirm-staging-deployment ID --evidence-out FILE]"
    exit 2
    ;;
esac

if [ "$#" -ne 0 ]; then
  echo "ERROR: --source accepts no additional arguments."
  exit 2
fi

mkdir -p artifacts/tenant-isolation

echo "=========================================="
echo "  RegEngine Source Tenant-Boundary Suite"
echo "=========================================="

# ---------------------------------------------------
# This script runs the existing tenant isolation and
# security test suite located in tests/security/.
#
# Source tests cover:
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

echo "Running source tenant-boundary tests from $TEST_DIR ..."
python3 -m pytest "$TEST_DIR" \
  -v \
  --tb=short \
  -rs \
  --json-report \
  --json-report-file="$RESULTS_FILE" \
  2>&1 | tee artifacts/tenant-isolation/output.log

EXIT_CODE=${PIPESTATUS[0]}

if [ "$EXIT_CODE" -ne 0 ]; then
  echo "FAIL: Tenant isolation tests failed. See $RESULTS_FILE"
  exit 1
fi

SKIPPED=$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("summary", {}).get("skipped", 0))' "$RESULTS_FILE")
if [ "$SKIPPED" -ne 0 ]; then
  echo "FAIL: $SKIPPED security test(s) skipped. Release-gate tests must execute."
  exit 1
fi

echo "PASS: Source tenant-boundary tests passed."
echo "NOTE: This is not the manifest-bound two-tenant staging gate; run this script with --staging for release evidence."
exit 0
