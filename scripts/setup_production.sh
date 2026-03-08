#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}RegEngine Railway Preflight${NC}"

echo -e "\n${GREEN}[1/3] Checking prerequisites...${NC}"
command -v railway >/dev/null 2>&1 || { echo "Railway CLI required."; exit 1; }
command -v psql >/dev/null 2>&1 || { echo "psql required for SQL migrations."; exit 1; }

echo -e "\n${GREEN}[2/3] Verifying Railway auth...${NC}"
railway whoami >/dev/null 2>&1 || railway login

if [[ -n "${RAILWAY_PROJECT_ID:-}" ]]; then
    echo "Linking Railway project: ${RAILWAY_PROJECT_ID}"
    railway link --id "${RAILWAY_PROJECT_ID}"
else
    echo -e "${YELLOW}RAILWAY_PROJECT_ID not set. Skipping railway link step.${NC}"
fi

echo -e "\n${GREEN}[3/3] Next commands${NC}"
cat <<'EOF'
1) Deploy backend services from Railway dashboard using these roots:
   - services/admin
   - services/ingestion
   - services/compliance
   - services/graph

2) Apply SQL migrations:
   bash scripts/railway/run_phase1a_migrations.sh

3) Apply Neo4j constraints:
   python services/graph/scripts/init_db_constraints.py

4) Verify service health:
   bash scripts/railway/verify_phase1a_health.sh

Runbook: docs/FSMA_RAILWAY_DEPLOYMENT.md
EOF
