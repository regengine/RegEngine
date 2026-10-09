#!/usr/bin/env bash
# Phone-test for the /api/v1/webhooks/ingest quickstart path.
#
# Runs the exact curl from frontend/src/app/docs/quickstart/page.tsx against
# a local backend (or a chosen base) and reports whether it would succeed
# for a pilot copying the docs. Catches drift between the published
# quickstart and the live contract — companion to
# scripts/smoke_test_ingest.sh which covers the R2-dependent /v1/ingest/*
# paths.
#
# Usage:
#   REGENGINE_API_KEY=rge_test_xxxx REGENGINE_TENANT_ID=<uuid> ./scripts/phone_test_quickstart.sh
#   REGENGINE_API_BASE=http://localhost:8000 ./scripts/phone_test_quickstart.sh   # default
#   ./scripts/phone_test_quickstart.sh --allow-production   # non-localhost targets only
#
# Localhost is the default target. Pointing REGENGINE_API_BASE at anything
# else requires the explicit --allow-production flag (or
# REGENGINE_ALLOW_PRODUCTION=1). Every run writes one synthetic event into
# the target tenant, so a non-localhost target must be a deliberate choice.
#
# Exit codes:
#   0 — webhook accepted the event (status=accepted, 1/1)
#   1 — webhook rejected or returned non-2xx
#   2 — missing required env vars or a refused non-localhost target

set -u

ALLOW_PRODUCTION="${REGENGINE_ALLOW_PRODUCTION:-0}"
for arg in "$@"; do
    if [[ "$arg" == "--allow-production" ]]; then
        ALLOW_PRODUCTION=1
    fi
done

API_BASE="${REGENGINE_API_BASE:-http://localhost:8000}"
API_KEY="${REGENGINE_API_KEY:-}"
TENANT_ID="${REGENGINE_TENANT_ID:-}"

if [[ -z "$API_KEY" || -z "$TENANT_ID" ]]; then
    echo "ERROR: set REGENGINE_API_KEY and REGENGINE_TENANT_ID" >&2
    echo "  REGENGINE_API_KEY     — rge_test_... (read from the environment, never a CLI arg)" >&2
    echo "  REGENGINE_TENANT_ID   — UUID for the tenant the key belongs to" >&2
    exit 2
fi

# Parse API_BASE: require http/https, reject userinfo/malformed, exact loopback host.
# (Same guard as scripts/smoke_test_ingest.sh: lookalike hosts such as
# localhost.attacker.example must not pass as local.)
_PHONE_REST=""
if [[ "$API_BASE" == "http://"* ]]; then
    _PHONE_REST="${API_BASE#http://}"
elif [[ "$API_BASE" == "https://"* ]]; then
    _PHONE_REST="${API_BASE#https://}"
fi
_PHONE_VALID=0
_PHONE_HOST=""
if [[ -n "$_PHONE_REST" ]]; then
    _PHONE_AUTH="${_PHONE_REST%%[/?#]*}"
    if [[ -n "$_PHONE_AUTH" && "$_PHONE_AUTH" != *"@"* ]]; then
        if [[ "$_PHONE_AUTH" == "["* ]]; then
            if [[ "$_PHONE_AUTH" == *"]"* ]]; then
                _PHONE_HOST="${_PHONE_AUTH#\[}"
                _PHONE_HOST="${_PHONE_HOST%%\]*}"
                _PHONE_AFTER="${_PHONE_AUTH#*\]}"
                if [[ -n "$_PHONE_HOST" ]]; then
                    if [[ -z "$_PHONE_AFTER" ]]; then
                        _PHONE_VALID=1
                    elif [[ "$_PHONE_AFTER" =~ ^:[0-9]+$ ]]; then
                        _PHONE_VALID=1
                    fi
                fi
            fi
        else
            if [[ "$_PHONE_AUTH" == *":"* ]]; then
                _PHONE_HOST="${_PHONE_AUTH%%:*}"
                _PHONE_PORT="${_PHONE_AUTH#*:}"
                if [[ -n "$_PHONE_HOST" && "$_PHONE_PORT" =~ ^[0-9]+$ ]]; then
                    if [[ "$_PHONE_HOST" != *":"* && "$_PHONE_PORT" != *":"* ]]; then
                        _PHONE_VALID=1
                    fi
                fi
            else
                _PHONE_HOST="$_PHONE_AUTH"
                if [[ -n "$_PHONE_HOST" ]]; then
                    _PHONE_VALID=1
                fi
            fi
        fi
    fi
fi
if [[ "$_PHONE_VALID" != "1" ]]; then
    echo "ERROR: refusing to probe malformed or non-http(s) target ($API_BASE)." >&2
    exit 2
fi
if [[ "$_PHONE_HOST" != "localhost" && "$_PHONE_HOST" != "127.0.0.1" && "$_PHONE_HOST" != "::1" ]]; then
    if [[ "$ALLOW_PRODUCTION" != "1" ]]; then
        echo "ERROR: refusing to write a synthetic event to non-localhost target ($API_BASE) without --allow-production." >&2
        exit 2
    fi
fi

IDEMPOTENCY_KEY="${REGENGINE_IDEMPOTENCY_KEY:-$(uuidgen | tr '[:upper:]' '[:lower:]')}"
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
