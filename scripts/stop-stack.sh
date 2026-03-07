#!/bin/bash
# RegEngine Stack Shutdown Script
# FSMA-first shutdown wrapper
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "🛑 Stopping RegEngine FSMA stack..."
"$SCRIPT_DIR/stop-fsma.sh"

echo "✅ FSMA stack stopped."
