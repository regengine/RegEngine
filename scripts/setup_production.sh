#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}RegEngine Railway Preflight${NC}"

echo -e "\n${GREEN}[1/3] Checking prerequisites...${NC}"
command -v railway >/dev/null 2>&1 || { echo "Railway CLI required."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 required for Alembic migrations."; exit 1; }

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
1) Deploy the consolidated monolith from the Railway dashboard:
   - Single service built from the repo-root Dockerfile.
   - Entry point: server.main:app (all service domains in one container).
   - See scripts/deploy_railway.sh, which pushes main for Railway
     auto-deploy and then verifies the monolith.

2) Apply database migrations (automatic on startup):
   scripts/run-migrations.sh (Alembic, needs MIGRATIONS_DATABASE_URL).
   Do NOT use the retired Phase 1A per-service SQL batch runner
   (scripts/railway/run_phase1a_migrations.sh).

3) Apply Neo4j constraints (optional, only if NEO4J_URI is set):
   python services/graph/scripts/init_db_constraints.py

4) Verify monolith health:
   curl https://<monolith>.up.railway.app/health
   curl https://<monolith>.up.railway.app/readiness
   (scripts/railway/verify_phase1a_health.sh probes the retired
   four-service topology; do not use it for the monolith.)

Runbook: docs/operations/FSMA_RAILWAY_DEPLOYMENT.md
EOF
