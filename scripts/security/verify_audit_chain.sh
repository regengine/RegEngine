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
HTTP_CODE=$(curl -s -o "$TMPFILE" -w "%{http_code}" \
    -H "Authorization: Bearer $AUDIT_TOKEN" \
    "${AUDIT_API_BASE}/v1/audit/export?include_verification=true&limit=50000")

if [ "$HTTP_CODE" != "200" ]; then
    echo "FAIL: API returned HTTP $HTTP_CODE"
    cat "$TMPFILE"
    exit 1
fi

# Extract verification result
VALID=$(python3 -c "
import json, sys
data = json.load(open('$TMPFILE'))
v = data.get('integrity', {}).get('chain_verification', {})
if not v:
    print('NO_VERIFICATION')
    sys.exit(0)
print('VALID' if v.get('valid') else 'INVALID')
if not v.get('valid'):
    print(f\"First break at entry: {v.get('first_break')}\")
    for e in v.get('errors', []):
        print(f\"  - Entry {e['id']}: {e['error']}\")
    sys.exit(1)
print(f\"Verified {v['verified']} / {v['total_entries']} entries\")
")

echo "$VALID"

if echo "$VALID" | grep -q "INVALID"; then
    exit 1
fi

echo ""
echo "=== Chain integrity verified ==="
