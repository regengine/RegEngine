#!/bin/bash
# RegEngine Railway Deployment Script (Monolith)
# Run from repo root: ./scripts/deploy_railway.sh
#
# The monolith (server/main.py) runs all 6 service domains in a single container.
# Migrations run automatically on startup via scripts/run-migrations.sh.
#
# Prerequisites:
#   1. Set DATABASE_URL to the NOBYPASSRLS regengine runtime role
#   2. Set ADMIN_DATABASE_URL to the NOBYPASSRLS regengine_sysadmin role
#   3. Set MIGRATIONS_DATABASE_URL to the schema-owner migration credential
#   4. Set the exact production ENABLED_ROUTERS allowlist
#
# Usage:
#   export DATABASE_URL="postgresql://regengine:...@db.example/regengine"
#   export ADMIN_DATABASE_URL="postgresql://regengine_sysadmin:...@db.example/regengine"
#   export MIGRATIONS_DATABASE_URL="postgresql://schema_owner:...@db.example/regengine"
#   export ENABLED_ROUTERS="inflow_workbench,..."
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
for required_var in DATABASE_URL ADMIN_DATABASE_URL MIGRATIONS_DATABASE_URL ENABLED_ROUTERS; do
  if [ -z "${!required_var:-}" ]; then
    echo -e "${RED}ERROR: ${required_var} not set${NC}"
    exit 1
  fi
  echo -e "${GREEN}✓${NC} ${required_var} set"
done

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
  # Pinned to the versions in requirements.lock, with hashes from that lock
  # file (pip-compile --generate-hashes). The pins live in a requirements
  # file because pip only accepts --hash there, not on the command line.
  # --require-hashes turns this into a verified install: an artifact that
  # does not match fails instead of installing. pytz is listed because it
  # is neo4j's only unconditional runtime dependency, and hash mode
  # requires every installed distribution to carry a hash. No
  # --break-system-packages fallback: that flag bypasses system-package
  # protection, so a failed install must stop the deploy instead of
  # retrying unprotected.
  req_file="$(mktemp)"
  trap 'rm -f "$req_file"' EXIT
  cat > "$req_file" <<'EOF'
neo4j==6.3.1 \
    --hash=sha256:a1b702d356f88885c27bdcf7dcd56af76423dbff4e26064e5bf5dbf47af53044 \
    --hash=sha256:e75530ca0691d69916c56acdb7401df4ee9e1d5084cfcfb3ede796db38667dcd
pytz==2026.3.post1 \
    --hash=sha256:2211d3fcf9a797d3405cac96ac7f61d80e6a644f72a3309607282fe8a2010c5d \
    --hash=sha256:dd95840dd199baea12d9cc096a1d452caa6596a1c1e4b5f3dbd1541855d5e815
EOF
  pip install --require-hashes --quiet -r "$req_file"
  rm -f "$req_file"
  trap - EXIT
  python3 services/graph/scripts/init_db_constraints.py
fi

# ── Step 3: Verify monolith ────────────────────────────────
echo ""
echo "── Step 3: Verify monolith (polling health, deadline ${MONOLITH_WAIT_SECS:-300}s) ──"
# Polls /health and /readiness until both return 200 or the deadline
# expires. A fixed sleep cannot know when Railway finishes the redeploy,
# and the old single-shot check reported still-deploying as success.
# wait_for_service.sh exits nonzero past the deadline, and set -e above
# stops the deploy there instead of printing a false all-clear.
WAIT_TIMEOUT_SECS="${MONOLITH_WAIT_SECS:-300}" "$SCRIPT_DIR/wait_for_service.sh" "$MONOLITH_URL"

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
echo "  Enabled routers: ${ENABLED_ROUTERS}"
echo "  Scale workers:   WEB_CONCURRENCY=2"
