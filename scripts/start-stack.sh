#!/bin/bash
# RegEngine Stack Startup Script
# Starts services in dependency order with health verification
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🚀 Starting RegEngine Infrastructure..."
echo "   Project root: $PROJECT_ROOT"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Phase 1: Core Infrastructure (databases, messaging, storage)
log_info "Phase 1/3: Starting core infrastructure..."
docker-compose up -d postgres redis neo4j redpanda localstack

log_info "Waiting for infrastructure to initialize (15s)..."
sleep 15

# Verify Postgres
if docker-compose exec -T postgres pg_isready -U regengine > /dev/null 2>&1; then
    log_info "✅ Postgres is ready"
else
    log_error "❌ Postgres failed to start"
    docker-compose logs --tail 20 postgres
    exit 1
fi

# Verify Redis
if docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; then
    log_info "✅ Redis is ready"
else
    log_warn "⚠️  Redis not responding (non-blocking)"
fi

# Verify Neo4j (may take longer)
log_info "Waiting for Neo4j to initialize (may take 30s)..."
for i in {1..10}; do
    if curl -sf http://localhost:7474 > /dev/null 2>&1; then
        log_info "✅ Neo4j is ready"
        break
    fi
    if [ $i -eq 10 ]; then
        log_warn "⚠️  Neo4j not responding yet (continuing anyway)"
    fi
    sleep 3
done

# Phase 2: Core API Services
log_info "Phase 2/3: Starting API services..."
docker-compose up -d admin-api
sleep 5

docker-compose up -d ingestion-service nlp-service graph-service
sleep 5

docker-compose up -d opportunity-api compliance-api scheduler
sleep 3

# Phase 3: Supporting Services
log_info "Phase 3/3: Starting supporting services..."
docker-compose up -d kafka-ui schema-registry 2>/dev/null || true

echo ""
log_info "Stack startup complete. Running health verification..."
echo ""

# Run health check script
if [ -f "$SCRIPT_DIR/verify-health.sh" ]; then
    bash "$SCRIPT_DIR/verify-health.sh"
else
    log_warn "Health verification script not found. Skipping."
fi

echo ""
log_info "🎉 RegEngine stack is ready!"
echo ""
echo "   Frontend:    http://localhost:3000"
echo "   Admin API:   http://localhost:8400/docs"
echo "   Neo4j:       http://localhost:7474"
echo "   Kafka UI:    http://localhost:8080"
echo ""
