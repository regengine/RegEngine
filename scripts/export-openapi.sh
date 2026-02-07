#!/bin/bash
# Export OpenAPI specifications from all RegEngine services
# Usage: ./scripts/export-openapi.sh

set -e

DOCS_DIR="docs/openapi"
mkdir -p "$DOCS_DIR"

echo "Exporting OpenAPI specifications..."

# Export Admin API
if curl -sf http://localhost:8400/openapi.json > /dev/null 2>&1; then
    curl -s http://localhost:8400/openapi.json | python3 -m json.tool > "$DOCS_DIR/admin-api.json"
    echo "✓ Admin API exported to $DOCS_DIR/admin-api.json"
else
    echo "✗ Admin API not available at http://localhost:8400"
fi

# Export Ingestion API
if curl -sf http://localhost:8002/openapi.json > /dev/null 2>&1; then
    curl -s http://localhost:8002/openapi.json | python3 -m json.tool > "$DOCS_DIR/ingestion-api.json"
    echo "✓ Ingestion API exported to $DOCS_DIR/ingestion-api.json"
else
    echo "✗ Ingestion API not available at http://localhost:8002"
fi

# Export Compliance API
if curl -sf http://localhost:8500/openapi.json > /dev/null 2>&1; then
    curl -s http://localhost:8500/openapi.json | python3 -m json.tool > "$DOCS_DIR/compliance-api.json"
    echo "✓ Compliance API exported to $DOCS_DIR/compliance-api.json"
else
    echo "✗ Compliance API not available at http://localhost:8500"
fi

# Export Graph API
if curl -sf http://localhost:8200/openapi.json > /dev/null 2>&1; then
    curl -s http://localhost:8200/openapi.json | python3 -m json.tool > "$DOCS_DIR/graph-api.json"
    echo "✓ Graph API exported to $DOCS_DIR/graph-api.json"
else
    echo "✗ Graph API not available at http://localhost:8200"
fi

# Export Opportunity API
if curl -sf http://localhost:8300/openapi.json > /dev/null 2>&1; then
    curl -s http://localhost:8300/openapi.json | python3 -m json.tool > "$DOCS_DIR/opportunity-api.json"
    echo "✓ Opportunity API exported to $DOCS_DIR/opportunity-api.json"
else
    echo "✗ Opportunity API not available at http://localhost:8300"
fi

echo ""
echo "OpenAPI export complete. Files in $DOCS_DIR:"
ls -la "$DOCS_DIR"
