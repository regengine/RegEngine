#!/usr/bin/env bash
# Smoke test for /v1/ingest/* endpoints.
#
# Codifies step 5 of #2351's R2 provisioning checklist: after Railway
# OBJECT_STORAGE_* env vars are set, every `/v1/ingest/*` endpoint should
# return 200. Before R2 is provisioned, every endpoint should return 503
# with detail 'Document storage is not configured for this environment.'
# Anything else (404, 500, timeout) means something is wrong with auth,
# routing, or the service itself.
#
# Usage:
#   REGENGINE_API_KEY=rge_live_xxxx ./scripts/smoke_test_ingest.sh
#   REGENGINE_API_KEY=rge_live_xxxx REGENGINE_API_BASE=http://localhost:8000 ./scripts/smoke_test_ingest.sh
#   REGENGINE_API_BASE=https://regengine.co/api/ingestion REGENGINE_API_KEY=rge_live_xxxx ./scripts/smoke_test_ingest.sh --allow-production
#
# Localhost is the default target. Pointing REGENGINE_API_BASE at anything
# else requires the explicit --allow-production flag (or
# REGENGINE_ALLOW_PRODUCTION=1). A localhost pass only proves the local
# stack works; only a pass with an explicit production REGENGINE_API_BASE
# plus --allow-production speaks for production R2.
#
# Exits 0 if all endpoints return a coherent state (all 200 OR all 503).
# Exits 1 on any unexpected status (404, 500, mixed states).
# Exits 2 on missing credentials or a refused non-localhost target.

set -u

ALLOW_PRODUCTION="${REGENGINE_ALLOW_PRODUCTION:-0}"
for arg in "$@"; do
    if [[ "$arg" == "--allow-production" ]]; then
        ALLOW_PRODUCTION=1
    fi
done

API_BASE="${REGENGINE_API_BASE:-http://localhost:8000}"
API_KEY="${REGENGINE_API_KEY:-}"

if [[ -z "$API_KEY" ]]; then
    echo "ERROR: set REGENGINE_API_KEY environment variable (e.g. rge_live_...)"
    exit 2
fi

# Parse API_BASE: require http/https, reject userinfo/malformed, exact loopback host.
_SMOKE_REST=""
if [[ "$API_BASE" == "http://"* ]]; then
    _SMOKE_REST="${API_BASE#http://}"
elif [[ "$API_BASE" == "https://"* ]]; then
    _SMOKE_REST="${API_BASE#https://}"
fi
_SMOKE_VALID=0
_SMOKE_HOST=""
if [[ -n "$_SMOKE_REST" ]]; then
    _SMOKE_AUTH="${_SMOKE_REST%%[/?#]*}"
    if [[ -n "$_SMOKE_AUTH" && "$_SMOKE_AUTH" != *"@"* ]]; then
        if [[ "$_SMOKE_AUTH" == "["* ]]; then
            if [[ "$_SMOKE_AUTH" == *"]"* ]]; then
                _SMOKE_HOST="${_SMOKE_AUTH#\[}"
                _SMOKE_HOST="${_SMOKE_HOST%%\]*}"
                _SMOKE_AFTER="${_SMOKE_AUTH#*\]}"
                if [[ -n "$_SMOKE_HOST" ]]; then
                    if [[ -z "$_SMOKE_AFTER" ]]; then
                        _SMOKE_VALID=1
                    elif [[ "$_SMOKE_AFTER" =~ ^:[0-9]+$ ]]; then
                        _SMOKE_VALID=1
                    fi
                fi
            fi
        else
            if [[ "$_SMOKE_AUTH" == *":"* ]]; then
                _SMOKE_HOST="${_SMOKE_AUTH%%:*}"
                _SMOKE_PORT="${_SMOKE_AUTH#*:}"
                if [[ -n "$_SMOKE_HOST" && "$_SMOKE_PORT" =~ ^[0-9]+$ ]]; then
                    if [[ "$_SMOKE_HOST" != *":"* && "$_SMOKE_PORT" != *":"* ]]; then
                        _SMOKE_VALID=1
                    fi
                fi
            else
                _SMOKE_HOST="$_SMOKE_AUTH"
                if [[ -n "$_SMOKE_HOST" ]]; then
                    _SMOKE_VALID=1
                fi
            fi
        fi
    fi
fi
if [[ "$_SMOKE_VALID" != "1" ]]; then
    echo "ERROR: refusing to probe malformed or non-http(s) target ($API_BASE)." >&2
    exit 2
fi
if [[ "$_SMOKE_HOST" == "localhost" || "$_SMOKE_HOST" == "127.0.0.1" || "$_SMOKE_HOST" == "::1" ]]; then
    _IS_LOOPBACK=1
else
    _IS_LOOPBACK=0
    if [[ "$ALLOW_PRODUCTION" != "1" ]]; then
        echo "ERROR: refusing to probe non-localhost target ($API_BASE) without --allow-production." >&2
        exit 2
    fi
fi

# Loopback probes must never leave the machine: bypass any configured
# http_proxy/https_proxy so the API key cannot be sent to a proxy.
smoke_curl() {
    if [[ "$_IS_LOOPBACK" == "1" ]]; then
        curl --noproxy '*' "$@"
    else
        curl "$@"
    fi
}

echo "=== Smoke test: /v1/ingest/* ==="
echo "Base: $API_BASE"
echo ""

declare -a RESULTS=()

probe() {
    local label="$1"
    local method="$2"
    local path="$3"
    local data_flag="$4"
    local data_arg="$5"
    local content_type="$6"

    local code
    if [[ "$method" == "POST_MULTIPART" ]]; then
        # Multipart upload for /v1/ingest/file
        code=$(smoke_curl -s -o /tmp/smoke_ingest_body -w "%{http_code}" \
            -X POST "$API_BASE$path" \
            -H "X-RegEngine-API-Key: $API_KEY" \
            -F "$data_arg" 2>/dev/null)
    else
        code=$(smoke_curl -s -o /tmp/smoke_ingest_body -w "%{http_code}" \
            -X "$method" "$API_BASE$path" \
            -H "X-RegEngine-API-Key: $API_KEY" \
            -H "Content-Type: $content_type" \
            "$data_flag" "$data_arg" 2>/dev/null)
    fi

    local body
    body=$(cat /tmp/smoke_ingest_body 2>/dev/null | head -c 200)

    local interpretation
    case "$code" in
        200|202)
            if [[ "$_IS_LOOPBACK" == "1" ]]; then
                interpretation="OK (local)"
            else
                interpretation="OK (R2 wired)"
            fi
            ;;
        503)
            if echo "$body" | grep -q "Document storage is not configured"; then
                interpretation="EXPECTED 503 (R2 not yet provisioned; gate working)"
            else
                interpretation="503 but unexpected body"
            fi
            ;;
        401|403) interpretation="AUTH FAILURE — check REGENGINE_API_KEY" ;;
        404)     interpretation="ROUTING FAILURE — endpoint not mounted" ;;
        429)     interpretation="rate-limited (retry)" ;;
        *)       interpretation="UNEXPECTED" ;;
    esac

    printf "  %-30s %s  %s\n" "$label" "$code" "$interpretation"
    RESULTS+=("$code")
}

probe "POST /v1/ingest/url"        POST            "/v1/ingest/url"        --data '{"url":"https://example.com/test.pdf"}' application/json
probe "POST /v1/ingest"            POST            "/v1/ingest"            --data '{"content":"test","content_type":"text/plain","source_url":"smoke-test"}' application/json
probe "POST /v1/ingest/file"       POST_MULTIPART  "/v1/ingest/file"       file "file=@/dev/null;filename=smoke.txt" multipart/form-data
probe "POST /v1/ingest/regulation" POST_MULTIPART  "/v1/ingest/regulation?name=smoke" file "file=@/dev/null;filename=smoke.txt" multipart/form-data

rm -f /tmp/smoke_ingest_body

echo ""
# Coherent state: all 200/202 OR all 503. Mixed = something wrong.
all_ok=true
all_503=true
for code in "${RESULTS[@]}"; do
    [[ "$code" == "200" || "$code" == "202" ]] || all_ok=false
    [[ "$code" == "503" ]] || all_503=false
done

if $all_ok; then
    if [[ "$_IS_LOOPBACK" == "1" ]]; then
        echo "RESULT: ✓ Local endpoints functional ($API_BASE only; not a production R2 check)."
    else
        echo "RESULT: ✓ R2 wired and all endpoints functional."
    fi
    exit 0
elif $all_503; then
    echo "RESULT: ✓ Gate working as expected (R2 not yet provisioned)."
    echo "        See #2351 for the provisioning checklist."
    exit 0
else
    echo "RESULT: ✗ Mixed or unexpected states. Investigate."
    exit 1
fi
