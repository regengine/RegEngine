#!/bin/bash
# RegEngine Stack Shutdown Script
# Gracefully stops all services

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🛑 Stopping RegEngine Stack..."

# Stop in reverse order
docker-compose stop \
    kafka-ui schema-registry \
    opportunity-api compliance-api \
    ingestion-service nlp-service graph-service \
    admin-api \
    redpanda neo4j redis localstack postgres \
    2>/dev/null

echo "✅ All services stopped."
echo ""
echo "To remove containers and volumes:"
echo "  docker-compose down -v"
