#!/bin/bash
# RegEngine Stack Startup Script
# FSMA-first startup wrapper
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🚀 Starting RegEngine FSMA stack..."
"$SCRIPT_DIR/start-fsma.sh"

echo ""
echo "✅ FSMA stack ready"
echo "   Frontend:  http://localhost:3000"
echo "   Admin API: http://localhost:8400/docs"
echo "   Ingestion: http://localhost:8002/health"
