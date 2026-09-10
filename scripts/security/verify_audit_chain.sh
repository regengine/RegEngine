#!/usr/bin/env bash
# ============================================================
# Audit Chain Integrity Verifier (CLI)
# ISO 27001: 12.7.1
#
# Usage:
#   AUDIT_API_BASE=https://api.regengine.com \
#   AUDIT_TOKEN=<bearer_token> \
#   bash scripts/security/verify_audit_chain.sh
#
# Exit codes:
#   0 = chain valid
#   1 = chain broken or API failure
# ============================================================

set -euo pipefail

AUDIT_API_BASE="${AUDIT_API_BASE:-http://localhost:8000}"
AUDIT_TOKEN="${AUDIT_TOKEN:-}"

if [ -z "$AUDIT_TOKEN" ]; then
    echo "ERROR: AUDIT_TOKEN not set"
    exit 1
fi

TMPFILE=$(mktemp)
trap "rm -f $TMPFILE" EXIT

echo "=== Audit Chain Integrity Verification ==="
echo "API: $AUDIT_API_BASE"
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# Export with verification enabled
HTTP_CODE=$(curl --connect-timeout 5 --max-time 60 -sS -o "$TMPFILE" -w "%{http_code}" \
    -H "Authorization: Bearer $AUDIT_TOKEN" \
    "${AUDIT_API_BASE}/v1/audit/export?include_verification=true&limit=50000")

if [ "$HTTP_CODE" != "200" ]; then
    echo "FAIL: API returned HTTP $HTTP_CODE"
    exit 1
fi

# Require explicit, complete verification; response bodies may contain private data.
python3 - "$TMPFILE" <<'PYVERIFY'
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as source:
        data = json.load(source)
    verification = data["integrity"]["chain_verification"]
    total = verification["total_entries"]
    verified = verification["verified"]
    if (
        verification["valid"] is not True
        or type(total) is not int
        or type(verified) is not int
        or total <= 0
        or verified != total
        or verification.get("errors") != []
        or verification.get("first_break") is not None
    ):
        raise ValueError("incomplete or invalid verification")
except (OSError, ValueError, KeyError, TypeError):
    print("FAIL: explicit, complete non-empty chain verification required")
    sys.exit(1)
print(f"Verified {verified} / {total} entries")
if verification.get("has_legacy_v1_rows"):
    print("WARNING: legacy rows lack actor-field tamper evidence")
PYVERIFY

echo ""
echo "=== Returned audit chain integrity verified ==="
