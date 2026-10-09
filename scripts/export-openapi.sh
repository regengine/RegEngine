#!/bin/bash
# Legacy helper retained only for local inspection of non-production services.
# It must never overwrite public or archived specs.

set -euo pipefail

OUTPUT_DIR="${REGENGINE_OPENAPI_OUTPUT_DIR:-/tmp/regengine-openapi}"
mkdir -p "$OUTPUT_DIR"
FAILED=0

echo "Exporting OpenAPI specifications..."

# Export Ingestion API
if curl -sf http://localhost:8002/openapi.json > /dev/null 2>&1; then
    curl -sf http://localhost:8002/openapi.json | python3 -m json.tool > "$OUTPUT_DIR/ingestion-api.json"
    echo "✓ Ingestion API exported to $OUTPUT_DIR/ingestion-api.json"
else
    echo "✗ Ingestion API not available at http://localhost:8002" >&2
    FAILED=1
fi

# Export Compliance API
if curl -sf http://localhost:8500/openapi.json > /dev/null 2>&1; then
    curl -sf http://localhost:8500/openapi.json | python3 -m json.tool > "$OUTPUT_DIR/compliance-api.json"
    echo "✓ Compliance API exported to $OUTPUT_DIR/compliance-api.json"
else
    echo "✗ Compliance API not available at http://localhost:8500" >&2
    FAILED=1
fi

# Export Graph API
if curl -sf http://localhost:8200/openapi.json > /dev/null 2>&1; then
    curl -sf http://localhost:8200/openapi.json | python3 -m json.tool > "$OUTPUT_DIR/graph-api.json"
    echo "✓ Graph API exported to $OUTPUT_DIR/graph-api.json"
else
    echo "✗ Graph API not available at http://localhost:8200" >&2
    FAILED=1
fi

if [ "$FAILED" -ne 0 ]; then
    echo "OpenAPI export incomplete: one or more endpoints were unreachable." >&2
    exit 1
fi

echo ""
echo "OpenAPI export complete. Files in $OUTPUT_DIR:"
ls -la "$OUTPUT_DIR"
