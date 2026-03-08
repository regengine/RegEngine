#!/bin/bash
# RegEngine Railway Deployment Script
# Run from repo root: ./scripts/deploy_railway.sh
#
# Prerequisites:
#   1. Set DATABASE_URL from Railway Postgres service (Connection tab > Public URL)
#   2. Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD from Railway Neo4j service
#
# Usage:
#   export DATABASE_URL="postgresql://postgres:xxx@xxx.railway.app:5432/railway"
#   export NEO4J_URI="neo4j+s://xxx.railway.app:7687"
#   export NEO4J_USER="neo4j"
#   export NEO4J_PASSWORD="xxx"
#   ./scripts/deploy_railway.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================"
echo " RegEngine Railway Deploy"
echo "========================================"
echo ""

# ── Step 0: Check prereqs ───────────────────────────────────
if [ -z "${DATABASE_URL:-}" ]; then
  echo -e "${RED}ERROR: DATABASE_URL not set${NC}"
  echo "Get it from Railway > Postgres service > Variables tab > DATABASE_URL"
  exit 1
fi

echo -e "${GREEN}✓${NC} DATABASE_URL set"

# ── Step 1: Push to GitHub ──────────────────────────────────
echo ""
echo "── Step 1: Push to GitHub ──"
git -C "$REPO_ROOT" push origin main
echo -e "${GREEN}✓${NC} Pushed — Railway will auto-deploy"

# ── Step 2: Run PostgreSQL migrations (admin) ───────────────
echo ""
echo "── Step 2: PostgreSQL migrations (admin, 34 files) ──"

ADMIN_MIGRATIONS="$REPO_ROOT/services/admin/migrations"
MIGRATION_COUNT=0
MIGRATION_FAIL=0

# Sort by version number (V1, V3, V4, ... V23, V23_5, V24, ...)
for f in $(ls "$ADMIN_MIGRATIONS"/V*.sql | sort -t'V' -k2 -V); do
  fname=$(basename "$f")
  echo -n "  $fname ... "
  if psql "$DATABASE_URL" -f "$f" -q 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
    ((MIGRATION_COUNT++))
  else
    echo -e "${YELLOW}SKIP (already applied or error)${NC}"
    ((MIGRATION_FAIL++))
  fi
done

echo -e "${GREEN}✓${NC} Admin migrations: $MIGRATION_COUNT applied, $MIGRATION_FAIL skipped"

# ── Step 3: Run ingestion migration ─────────────────────────
echo ""
echo "── Step 3: Ingestion schema migration ──"
INGESTION_SQL="$REPO_ROOT/services/ingestion/migrations/V001__ingestion_schema.sql"
if [ -f "$INGESTION_SQL" ]; then
  echo -n "  V001__ingestion_schema.sql ... "
  if psql "$DATABASE_URL" -f "$INGESTION_SQL" -q 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
  else
    echo -e "${YELLOW}SKIP${NC}"
  fi
fi

# ── Step 4: Run compliance migration ────────────────────────
echo ""
echo "── Step 4: Compliance schema migration ──"
COMPLIANCE_SQL="$REPO_ROOT/services/compliance/migrations/V1__fair_lending_compliance_os.sql"
if [ -f "$COMPLIANCE_SQL" ]; then
  echo -n "  V1__fair_lending_compliance_os.sql ... "
  if psql "$DATABASE_URL" -f "$COMPLIANCE_SQL" -q 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
  else
    echo -e "${YELLOW}SKIP${NC}"
  fi
fi

# ── Step 5: Run app user setup ──────────────────────────────
echo ""
echo "── Step 5: App user setup ──"
SETUP_SQL="$ADMIN_MIGRATIONS/setup_app_user.sql"
if [ -f "$SETUP_SQL" ]; then
  echo -n "  setup_app_user.sql ... "
  if psql "$DATABASE_URL" -f "$SETUP_SQL" -q 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
  else
    echo -e "${YELLOW}SKIP${NC}"
  fi
fi

# ── Step 6: Neo4j constraints ───────────────────────────────
echo ""
echo "── Step 6: Neo4j constraints ──"
if [ -z "${NEO4J_URI:-}" ]; then
  echo -e "${YELLOW}SKIP: NEO4J_URI not set — set it to run constraints${NC}"
else
  echo -e "${GREEN}✓${NC} NEO4J_URI set"
  cd "$REPO_ROOT"
  pip install neo4j --quiet 2>/dev/null || pip install neo4j --quiet --break-system-packages 2>/dev/null
  python3 services/graph/scripts/init_db_constraints.py
fi

# ── Step 7: Verify services ────────────────────────────────
echo ""
echo "── Step 7: Verify services (waiting 30s for redeploy) ──"
sleep 30

ADMIN_URL="https://regengine-production.up.railway.app/health"
INGESTION_URL="https://believable-respect-production-2fb3.up.railway.app/health"
COMPLIANCE_URL="https://intelligent-essence-production.up.railway.app/health"

for svc_label_url in "Admin|$ADMIN_URL" "Ingestion|$INGESTION_URL" "Compliance|$COMPLIANCE_URL"; do
  IFS='|' read -r label url <<< "$svc_label_url"
  echo -n "  $label ... "
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
  if [ "$status" = "200" ]; then
    echo -e "${GREEN}$status OK${NC}"
  else
    echo -e "${YELLOW}$status (may still be deploying)${NC}"
  fi
done

echo ""
echo "========================================"
echo -e "${GREEN} Deploy complete!${NC}"
echo "========================================"
echo ""
echo "Remaining manual steps:"
echo "  1. Stripe: Create products in dashboard, add keys to Railway ingestion service"
echo "  2. Resend: Verify domain DNS records"
echo "  3. Optional: Rename Railway services to meaningful names"
echo "  4. Optional: Set up api.regengine.co custom domain on admin service"
