#!/bin/bash
# RegEngine Railway Deployment Script (Monolith)
# Run from repo root: ./scripts/deploy_railway.sh
#
# The monolith (server/main.py) runs all 6 service domains in a single container.
# Migrations run automatically on startup via scripts/run-migrations.sh.
#
# Prerequisites:
#   1. Set DATABASE_URL from Railway Postgres or Supabase
#   2. Optionally set NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD (graph features)
#
# Usage:
#   export DATABASE_URL="postgresql://postgres:xxx@db.xxx.supabase.co:6543/postgres"
#   ./scripts/deploy_railway.sh

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Default monolith URL — override with MONOLITH_URL env var
MONOLITH_URL="${MONOLITH_URL:-https://regengine-production.up.railway.app}"

echo "========================================"
echo " RegEngine Railway Deploy (Monolith)"
echo "========================================"
echo ""

# ── Step 0: Check prereqs ───────────────────────────────────
if [ -z "${DATABASE_URL:-}" ]; then
  echo -e "${RED}ERROR: DATABASE_URL not set${NC}"
  echo "Get it from Supabase > Settings > Database > Connection string"
  exit 1
fi

echo -e "${GREEN}✓${NC} DATABASE_URL set"

# ── Step 1: Push to GitHub ──────────────────────────────────
echo ""
echo "── Step 1: Push to GitHub ──"
git -C "$REPO_ROOT" push origin main
echo -e "${GREEN}✓${NC} Pushed — Railway will auto-deploy"
echo ""
echo "  Monolith builds from root Dockerfile."
echo "  Migrations run automatically on startup (Alembic + advisory lock)."

# ── Step 2: Neo4j constraints (optional) ────────────────────
echo ""
echo "── Step 2: Neo4j constraints (optional) ──"
if [ -z "${NEO4J_URI:-}" ]; then
  echo -e "${YELLOW}SKIP: NEO4J_URI not set — graph features disabled${NC}"
else
  echo -e "${GREEN}✓${NC} NEO4J_URI set"
  cd "$REPO_ROOT"
  pip install neo4j --quiet 2>/dev/null || pip install neo4j --quiet --break-system-packages 2>/dev/null
  python3 services/graph/scripts/init_db_constraints.py
fi

# ── Step 3: Verify monolith ────────────────────────────────
echo ""
echo "── Step 3: Verify monolith (waiting 30s for redeploy) ──"
sleep 30

for endpoint in "health" "readiness"; do
  url="$MONOLITH_URL/$endpoint"
  echo -n "  GET /$endpoint ... "
  status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$url" 2>/dev/null || echo "000")
  if [ "$status" = "200" ]; then
    echo -e "${GREEN}$status OK${NC}"
  else
    echo -e "${YELLOW}$status (may still be deploying)${NC}"
  fi
done

# Check feature flags
echo ""
echo -n "  Features: "
features=$(curl -s --max-time 10 "$MONOLITH_URL/api/v1/features" 2>/dev/null || echo "{}")
echo "$features" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    enabled = d.get('enabled', [])
    disabled = d.get('disabled', [])
    print(f'{len(enabled)} enabled, {len(disabled)} disabled')
except:
    print('(could not parse)')
" 2>/dev/null || echo "(unavailable)"

echo ""
echo "========================================"
echo -e "${GREEN} Deploy complete!${NC}"
echo "========================================"
echo ""
echo "  Monolith: $MONOLITH_URL"
echo "  Docs:     $MONOLITH_URL/docs  (dev only)"
echo "  Health:   $MONOLITH_URL/health"
echo ""
echo "  Disable specific routers: DISABLED_ROUTERS=graph,nlp"
echo "  Scale workers:            WEB_CONCURRENCY=2"
