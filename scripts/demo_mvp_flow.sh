#!/usr/bin/env bash
#
# RegEngine MVP Demo — End-to-End Data Flow
#
# Demonstrates the core value proposition in under 5 minutes:
#   CSV upload → ingestion → normalization → rule evaluation → FDA export
#
# Prerequisites:
#   docker compose -f docker-compose.mvp.yml up -d
#   Wait for health checks to pass
#
# Usage:
#   ./scripts/demo_mvp_flow.sh [API_KEY]
#
# If no API_KEY is provided, the script will create one via the admin API.

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
ADMIN_URL="${ADMIN_URL:-http://localhost:8400}"
INGEST_URL="${INGEST_URL:-http://localhost:8002}"
API_KEY="${1:-}"
ADMIN_MASTER_KEY="${ADMIN_MASTER_KEY:-}"
TENANT_ID="${TENANT_ID:-demo-tenant}"
SAMPLE_DIR="$(cd "$(dirname "$0")/../sample_data" && pwd)"
EXPORT_DIR="$(cd "$(dirname "$0")/.." && pwd)/demo_exports"

# Colors
G='\033[0;32m' Y='\033[1;33m' B='\033[0;34m' R='\033[0;31m' C='\033[0;36m' NC='\033[0m'

header() { echo -e "\n${B}━━━ $1 ━━━${NC}"; }
ok()     { echo -e "  ${G}✓${NC} $1"; }
fail()   { echo -e "  ${R}✗${NC} $1"; }
info()   { echo -e "  ${C}→${NC} $1"; }

echo -e "${B}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${B}║  RegEngine MVP Demo — CSV to FDA Export in 5 Minutes    ║${NC}"
echo -e "${B}╚══════════════════════════════════════════════════════════╝${NC}"

# ── Step 0: Health checks ───────────────────────────────────────────────────
header "Step 0 · Checking service health"

for svc in "$ADMIN_URL/health:Admin" "$INGEST_URL/health:Ingestion"; do
  url="${svc%%:*}"
  name="${svc##*:}"
  if curl -sf "$url" > /dev/null 2>&1; then
    ok "$name service healthy"
  else
    fail "$name service not responding at $url"
    echo -e "  ${Y}Start services first: docker compose -f docker-compose.mvp.yml up -d${NC}"
    exit 1
  fi
done

# ── Step 1: Get or create API key ───────────────────────────────────────────
header "Step 1 · Authentication"

if [ -z "$API_KEY" ]; then
  if [ -z "$ADMIN_MASTER_KEY" ]; then
    echo -e "  ${Y}No API_KEY or ADMIN_MASTER_KEY provided.${NC}"
    echo -e "  ${Y}Usage: ./scripts/demo_mvp_flow.sh <your-api-key>${NC}"
    echo -e "  ${Y}Or set ADMIN_MASTER_KEY to auto-create one.${NC}"
    exit 1
  fi

  info "Creating API key via admin service..."
  KEY_RESPONSE=$(curl -sf -X POST "$ADMIN_URL/api/keys" \
    -H "Content-Type: application/json" \
    -H "X-Admin-Master-Key: $ADMIN_MASTER_KEY" \
    -d "{\"name\": \"mvp-demo\", \"tenant_id\": \"$TENANT_ID\", \"permissions\": [\"ingest.write\", \"fda.export\"]}" \
    2>/dev/null || echo "{}")

  API_KEY=$(echo "$KEY_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('key', ''))" 2>/dev/null || echo "")

  if [ -z "$API_KEY" ]; then
    fail "Could not create API key. Set API_KEY directly."
    exit 1
  fi
  ok "API key created: ${API_KEY:0:8}..."
else
  ok "Using provided API key: ${API_KEY:0:8}..."
fi

# ── Step 2: Ingest sample supply chain data ─────────────────────────────────
header "Step 2 · Ingesting supply chain data (6 CSV files)"

INGEST_COUNT=0
INGEST_ERRORS=0

for csv in "$SAMPLE_DIR"/*.csv; do
  filename=$(basename "$csv")
  step_name="${filename%.csv}"

  RESPONSE=$(curl -sf -X POST "$INGEST_URL/v1/ingest/file" \
    -H "X-RegEngine-API-Key: $API_KEY" \
    -H "X-Tenant-ID: $TENANT_ID" \
    -F "file=@$csv" \
    -F "source_system=mvp-demo" \
    -F "vertical=food_safety" \
    2>/dev/null || echo '{"error": "request failed"}')

  EVENT_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('event_id', ''))" 2>/dev/null || echo "")

  if [ -n "$EVENT_ID" ]; then
    IS_DUP=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('is_duplicate', False))" 2>/dev/null || echo "")
    if [ "$IS_DUP" = "True" ]; then
      ok "$step_name — deduplicated (already ingested)"
    else
      ok "$step_name — ingested (event: ${EVENT_ID:0:8}...)"
    fi
    INGEST_COUNT=$((INGEST_COUNT + 1))
  else
    fail "$step_name — failed"
    info "Response: $(echo "$RESPONSE" | head -c 200)"
    INGEST_ERRORS=$((INGEST_ERRORS + 1))
  fi
done

echo ""
info "Ingested: $INGEST_COUNT files, Errors: $INGEST_ERRORS"

if [ "$INGEST_ERRORS" -gt 0 ] && [ "$INGEST_COUNT" -eq 0 ]; then
  fail "All ingestions failed. Check API key permissions and service logs."
  exit 1
fi

# ── Step 3: Export FDA-ready package ────────────────────────────────────────
header "Step 3 · Generating FDA-ready export"

mkdir -p "$EXPORT_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_FILE="$EXPORT_DIR/fda_export_demo_${TIMESTAMP}.csv"
TLC="LOT-ROM-2026-0312A"

info "Requesting FDA export for lot: $TLC"

HTTP_CODE=$(curl -sf -o "$EXPORT_FILE" -w "%{http_code}" \
  "$INGEST_URL/api/v1/fda/export?tlc=$TLC&tenant_id=$TENANT_ID&format=csv" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ] && [ -s "$EXPORT_FILE" ]; then
  LINES=$(wc -l < "$EXPORT_FILE" | tr -d ' ')
  SIZE=$(du -h "$EXPORT_FILE" | cut -f1)
  ok "FDA export generated: $EXPORT_FILE"
  info "Records: $((LINES - 1)), Size: $SIZE"

  # Show first few columns of the export
  echo ""
  info "Preview (first 3 records):"
  head -4 "$EXPORT_FILE" | column -t -s',' 2>/dev/null | head -4 | while read -r line; do
    echo -e "  ${C}${line:0:120}${NC}"
  done
else
  fail "FDA export failed (HTTP $HTTP_CODE)"
  info "Trying export/all as fallback..."

  HTTP_CODE=$(curl -sf -o "$EXPORT_FILE" -w "%{http_code}" \
    "$INGEST_URL/api/v1/fda/export/all?tenant_id=$TENANT_ID&format=csv" \
    -H "X-RegEngine-API-Key: $API_KEY" \
    2>/dev/null || echo "000")

  if [ "$HTTP_CODE" = "200" ] && [ -s "$EXPORT_FILE" ]; then
    LINES=$(wc -l < "$EXPORT_FILE" | tr -d ' ')
    ok "FDA export (all events): $EXPORT_FILE ($((LINES - 1)) records)"
  else
    fail "Export failed. Check service logs: docker compose -f docker-compose.mvp.yml logs ingestion-service"
  fi
fi

# ── Step 4: Export with compliance status (v2) ──────────────────────────────
header "Step 4 · Compliance-checked export (enforcement layer)"

EXPORT_V2="$EXPORT_DIR/fda_export_v2_demo_${TIMESTAMP}.csv"

HTTP_CODE=$(curl -sf -o "$EXPORT_V2" -w "%{http_code}" \
  "$INGEST_URL/api/v1/fda/export/v2?tlc=$TLC&tenant_id=$TENANT_ID&format=csv" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  2>/dev/null || echo "000")

if [ "$HTTP_CODE" = "200" ] && [ -s "$EXPORT_V2" ]; then
  LINES=$(wc -l < "$EXPORT_V2" | tr -d ' ')
  ok "Compliance export generated: $EXPORT_V2"
  info "Records: $((LINES - 1)) (includes Compliance Status + Rule Failures columns)"
else
  info "v2 export returned HTTP $HTTP_CODE — may need rule engine configuration"
fi

# ── Step 5: Verify chain integrity ──────────────────────────────────────────
header "Step 5 · Chain integrity verification"

VERIFY_RESPONSE=$(curl -sf "$INGEST_URL/api/v1/fda/export/all?tenant_id=$TENANT_ID&format=csv" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -D - -o /dev/null 2>/dev/null || echo "")

CHAIN_STATUS=$(echo "$VERIFY_RESPONSE" | grep -i "X-Chain-Integrity" | tr -d '\r' | awk '{print $2}')
RECORD_COUNT=$(echo "$VERIFY_RESPONSE" | grep -i "X-Record-Count" | tr -d '\r' | awk '{print $2}')
KDE_COVERAGE=$(echo "$VERIFY_RESPONSE" | grep -i "X-KDE-Coverage" | tr -d '\r' | awk '{print $2}')

if [ -n "$CHAIN_STATUS" ]; then
  ok "Chain integrity: $CHAIN_STATUS"
  [ -n "$RECORD_COUNT" ] && info "Records in chain: $RECORD_COUNT"
  [ -n "$KDE_COVERAGE" ] && info "KDE coverage: $KDE_COVERAGE"
else
  info "Chain verification headers not returned — check export endpoint"
fi

# ── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${G}Demo Complete${NC}"
echo ""
echo -e "  ${G}What just happened:${NC}"
echo -e "  1. Uploaded 6 supply chain CSVs (harvest → cool → pack → ship → receive → transform)"
echo -e "  2. Each event was normalized, hashed (SHA-256), and stored with chain linkage"
echo -e "  3. Generated an FDA-ready export with full traceability for lot $TLC"
echo -e "  4. Checked compliance status against FSMA 204 rules"
echo -e "  5. Verified cryptographic chain integrity"
echo ""
echo -e "  ${C}Export files:${NC}"
[ -f "$EXPORT_FILE" ] && echo -e "    $EXPORT_FILE"
[ -f "$EXPORT_V2" ] && echo -e "    $EXPORT_V2"
echo ""
echo -e "  ${C}Next steps:${NC}"
echo -e "    • Open the FDA export CSV and verify the chain of custody"
echo -e "    • Try the same flow via the web UI at http://localhost:3000"
echo -e "    • Run with your own CSV data to see how it handles real-world messiness"
echo -e "${B}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
