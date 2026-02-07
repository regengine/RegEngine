#!/bin/bash
# Deployment Script for RLS Security Layer
# Run this to deploy V27 and V28 to Supabase
#
# Usage:
#   ./deploy_rls.sh local    # Test on local Supabase
#   ./deploy_rls.sh staging  # Deploy to staging
#   ./deploy_rls.sh prod     # Deploy to production

set -e  # Exit on error

ENVIRONMENT=${1:-local}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATIONS_DIR="$SCRIPT_DIR/../services/admin/migrations"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}RLS Security Layer Deployment${NC}"
echo -e "${GREEN}Environment: $ENVIRONMENT${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Load environment-specific config
case $ENVIRONMENT in
  local)
    echo "Using local Supabase connection..."
    DB_URL=${LOCAL_SUPABASE_DB_URL:-postgresql://postgres:postgres@localhost:54322/postgres}
    ;;
  staging)
    echo "Using staging Supabase connection..."
    if [ -z "$STAGING_SUPABASE_DB_URL" ]; then
      echo -e "${RED}Error: STAGING_SUPABASE_DB_URL not set${NC}"
      echo "Set it with: export STAGING_SUPABASE_DB_URL='postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres'"
      exit 1
    fi
    DB_URL=$STAGING_SUPABASE_DB_URL
    ;;
  prod)
    echo -e "${YELLOW}⚠️  WARNING: Deploying to PRODUCTION${NC}"
    echo "Press ENTER to continue or Ctrl+C to abort..."
    read
    if [ -z "$PROD_SUPABASE_DB_URL" ]; then
      echo -e "${RED}Error: PROD_SUPABASE_DB_URL not set${NC}"
      exit 1
    fi
    DB_URL=$PROD_SUPABASE_DB_URL
    ;;
  *)
    echo -e "${RED}Invalid environment: $ENVIRONMENT${NC}"
    echo "Usage: $0 [local|staging|prod]"
    exit 1
    ;;
esac

# Function to run SQL file
run_migration() {
  local migration_file=$1
  local migration_name=$(basename "$migration_file")
  
  echo -e "${YELLOW}Running: $migration_name${NC}"
  
  if psql "$DB_URL" -f "$migration_file" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ $migration_name completed${NC}"
    return 0
  else
    echo -e "${RED}❌ $migration_name failed${NC}"
    echo "Check the error above and fix before continuing."
    return 1
  fi
}

# Pre-flight checks
echo "Step 1: Pre-flight checks..."
echo "----------------------------------------"

# Check if psql is installed
if ! command -v psql &> /dev/null; then
  echo -e "${RED}Error: psql not found. Install PostgreSQL client tools.${NC}"
  exit 1
fi

# Check database connection
echo "Testing database connection..."
if psql "$DB_URL" -c "SELECT 1" > /dev/null 2>&1; then
  echo -e "${GREEN}✅ Database connection successful${NC}"
else
  echo -e "${RED}❌ Database connection failed${NC}"
  exit 1
fi

# Check if migrations exist
if [ ! -f "$MIGRATIONS_DIR/V27__rls_core_security_tables.sql" ]; then
  echo -e "${RED}Error: V27 migration not found${NC}"
  exit 1
fi

if [ ! -f "$MIGRATIONS_DIR/V28__rls_pcos_vertical_tables.sql" ]; then
  echo -e "${RED}Error: V28 migration not found${NC}"
  exit 1
fi

echo -e "${GREEN}✅ All pre-flight checks passed${NC}"
echo

# Backup reminder
echo "Step 2: Backup (RECOMMENDED)"
echo "----------------------------------------"
if [ "$ENVIRONMENT" != "local" ]; then
  echo -e "${YELLOW}⚠️  Create a database backup before proceeding${NC}"
  echo "1. Go to Supabase Dashboard → Database → Backups"
  echo "2. Click 'Create Backup'"
  echo "3. Wait for backup to complete"
  echo
  echo "Press ENTER when backup is complete (or Ctrl+C to abort)..."
  read
fi

# Run migrations
echo "Step 3: Running RLS Migrations"
echo "----------------------------------------"

echo "Deploying V27: Core Security Tables (15 tables)..."
if ! run_migration "$MIGRATIONS_DIR/V27__rls_core_security_tables.sql"; then
  echo -e "${RED}Deployment failed at V27${NC}"
  exit 1
fi

echo
echo "Deploying V28: PCOS & Vertical Tables (40+ tables)..."
if ! run_migration "$MIGRATIONS_DIR/V28__rls_pcos_vertical_tables.sql"; then
  echo -e "${RED}Deployment failed at V28${NC}"
  echo -e "${YELLOW}V27 was applied successfully. You may need to rollback.${NC}"
  exit 1
fi

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ RLS Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Post-deployment verification
echo "Step 4: Verification"
echo "----------------------------------------"
echo "Running post-deployment checks..."

# Verify RLS is enabled
TOTAL_RLS_TABLES=$(psql "$DB_URL" -t -c "
  SELECT COUNT(*) 
  FROM pg_tables t
  JOIN pg_class c ON c.relname = t.tablename
  WHERE t.schemaname = 'public' 
    AND c.relrowsecurity = true;
" | tr -d ' ')

echo "Tables with RLS enabled: $TOTAL_RLS_TABLES"

if [ "$TOTAL_RLS_TABLES" -lt 50 ]; then
  echo -e "${YELLOW}⚠️  Expected ~60 tables with RLS, found $TOTAL_RLS_TABLES${NC}"
  echo "This may be normal if some tables don't exist yet."
else
  echo -e "${GREEN}✅ RLS enabled on $TOTAL_RLS_TABLES tables${NC}"
fi

echo
echo -e "${GREEN}Next Steps:${NC}"
echo "1. Test tenant isolation (see verify_rls_isolation.sql)"
echo "2. Test PostgREST API with proper JWT"
echo "3. Monitor application logs for RLS errors"
echo "4. Run full integration tests"
echo

if [ "$ENVIRONMENT" = "local" ]; then
  echo -e "${YELLOW}This was a LOCAL deployment.${NC}"
  echo "Test thoroughly before deploying to staging/production."
fi

exit 0
