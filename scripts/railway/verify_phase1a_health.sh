#!/usr/bin/env bash
set -euo pipefail

if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required but not found in PATH."
    exit 1
fi

ADMIN_URL="${ADMIN_URL:-}"
INGESTION_URL="${INGESTION_URL:-}"
COMPLIANCE_URL="${COMPLIANCE_URL:-}"
GRAPH_URL="${GRAPH_URL:-}"

if [[ -z "$ADMIN_URL" || -z "$INGESTION_URL" || -z "$COMPLIANCE_URL" || -z "$GRAPH_URL" ]]; then
    cat <<'EOF'
Set all service URLs before running:
  export ADMIN_URL="https://<admin-service>.up.railway.app"
  export INGESTION_URL="https://<ingestion-service>.up.railway.app"
  export COMPLIANCE_URL="https://<compliance-service>.up.railway.app"
  export GRAPH_URL="https://<graph-service>.up.railway.app"
EOF
    exit 1
fi

check_health() {
    local service_name="$1"
    local base_url="$2"
    local endpoint="${base_url%/}/health"

    echo "Checking ${service_name} -> ${endpoint}"
    local response
    response="$(curl -fsS --max-time 15 "$endpoint")"
    echo "  OK: ${response}"
}

check_health "admin-service" "$ADMIN_URL"
check_health "ingestion-service" "$INGESTION_URL"
check_health "compliance-service" "$COMPLIANCE_URL"
check_health "graph-service" "$GRAPH_URL"

echo "All Phase 1A service health checks passed."
