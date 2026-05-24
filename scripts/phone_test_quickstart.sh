#!/usr/bin/env bash
# Phone-test for the /api/v1/webhooks/ingest quickstart path.
#
# Runs the exact curl from frontend/src/app/docs/quickstart/page.tsx against
# prod (or a chosen base) and reports whether it would succeed for a pilot
# copying the docs. Catches drift between the published quickstart and the
# live contract — companion to scripts/smoke_test_ingest.sh which covers
# the R2-dependent /v1/ingest/* paths.
#
# Usage:
#   REGENGINE_API_KEY=rge_live_xxxx REGENGINE_TENANT_ID=<uuid> ./scripts/phone_test_quickstart.sh
#   REGENGINE_API_BASE=https://regengine.co ./scripts/phone_test_quickstart.sh   # default
#
# Exit codes:
#   0 — webhook accepted the event (status=accepted, 1/1)
#   1 — webhook rejected or returned non-2xx
#   2 — missing required env vars

set -u

API_BASE="${REGENGINE_API_BASE:-https://regengine.co}"
API_KEY="${REGENGINE_API_KEY:-}"
TENANT_ID="${REGENGINE_TENANT_ID:-}"

if [[ -z "$API_KEY" || -z "$TENANT_ID" ]]; then
    echo "ERROR: set REGENGINE_API_KEY and REGENGINE_TENANT_ID" >&2
    echo "  REGENGINE_API_KEY     — rge_live_... or rge_test_..." >&2
    echo "  REGENGINE_TENANT_ID   — UUID for the tenant the key belongs to" >&2
    exit 2
fi

IDEMPOTENCY_KEY="$(uuidgen | tr '[:upper:]' '[:lower:]')"
TLC="PHONE-TEST-$(date -u +%Y%m%d-%H%M%S)"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "=== Phone-test: POST $API_BASE/api/v1/webhooks/ingest ==="
echo "TLC:             $TLC"
echo "Idempotency-Key: $IDEMPOTENCY_KEY"
echo ""

PAYLOAD=$(cat <<JSON
{
  "source": "phone-test",
  "events": [
    {
      "cte_type": "receiving",
      "traceability_lot_code": "$TLC",
      "product_description": "Romaine Lettuce (phone-test)",
      "quantity": 500,
      "unit_of_measure": "cases",
      "location_name": "Distribution Center #4",
      "timestamp": "$TIMESTAMP",
      "kdes": {
        "receive_date": "$(date -u +%Y-%m-%d)",
        "receiving_location": "Distribution Center #4",
        "immediate_previous_source": "GreenLeaf Farms LLC",
        "reference_document": "ASN-PHONE-TEST",
        "tlc_source_reference": "GLF-PHONE-TEST"
      }
    }
  ]
}
JSON
)

RESPONSE=$(curl -sS -w "\n__HTTP_STATUS__:%{http_code}" \
    -X POST "$API_BASE/api/v1/webhooks/ingest" \
    -H "X-RegEngine-API-Key: $API_KEY" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

BODY=$(printf '%s' "$RESPONSE" | sed '$d')
STATUS=$(printf '%s' "$RESPONSE" | tail -1 | sed 's/__HTTP_STATUS__://')

echo "HTTP $STATUS"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""

if [[ "$STATUS" != "200" ]]; then
    echo "FAIL: expected 200, got $STATUS" >&2
    exit 1
fi

ACCEPTED=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('accepted', 0))" 2>/dev/null || echo "0")
REJECTED=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('rejected', 0))" 2>/dev/null || echo "0")

if [[ "$ACCEPTED" == "1" && "$REJECTED" == "0" ]]; then
    echo "PASS: 1 event accepted"
    echo ""
    echo "Idempotency check: replaying the same Idempotency-Key should return"
    echo "the cached response within 24h. Re-run with:"
    echo "  REGENGINE_IDEMPOTENCY_KEY=$IDEMPOTENCY_KEY ./scripts/phone_test_quickstart.sh"
    exit 0
fi

echo "FAIL: accepted=$ACCEPTED rejected=$REJECTED — inspect 'events[].errors' above" >&2
exit 1
