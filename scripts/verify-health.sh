#!/bin/bash
# RegEngine Health Verification Script
# Checks all service health endpoints and reports status

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Service definitions: "url|name|required"
# required=1 means failure is critical, required=0 means it's optional
SERVICES=(
    "http://localhost:8400/health|Admin API|1"
    "http://localhost:8000/health|Ingestion|1"
    "http://localhost:8100/health|NLP|0"
    "http://localhost:8200/health|Graph|1"
    "http://localhost:8300/health|Opportunity|1"
    "http://localhost:8500/health|Compliance|1"
    "http://localhost:8600/health|Scheduler|1"
)

INFRASTRUCTURE=(
    "http://localhost:7474|Neo4j|1"
    "http://localhost:9092|Redpanda|0"
)

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  RegEngine Health Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

FAILED=0
WARNINGS=0

check_service() {
    local url=$1
    local name=$2
    local required=$3
    local timeout=${4:-5}
    
    if curl -sf --max-time $timeout "$url" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✅${NC} $name"
        return 0
    else
        if [ "$required" == "1" ]; then
            echo -e "  ${RED}❌${NC} $name (FAILED: $url)"
            return 1
        else
            echo -e "  ${YELLOW}⚠️${NC}  $name (optional, not responding)"
            return 2
        fi
    fi
}

echo "Infrastructure:"
for entry in "${INFRASTRUCTURE[@]}"; do
    IFS='|' read -r url name required <<< "$entry"
    check_service "$url" "$name" "$required" 3
    result=$?
    if [ $result -eq 1 ]; then
        FAILED=$((FAILED + 1))
    elif [ $result -eq 2 ]; then
        WARNINGS=$((WARNINGS + 1))
    fi
done

echo ""
echo "Application Services:"
for entry in "${SERVICES[@]}"; do
    IFS='|' read -r url name required <<< "$entry"
    check_service "$url" "$name" "$required" 5
    result=$?
    if [ $result -eq 1 ]; then
        FAILED=$((FAILED + 1))
    elif [ $result -eq 2 ]; then
        WARNINGS=$((WARNINGS + 1))
    fi
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ $FAILED -gt 0 ]; then
    echo -e "  ${RED}Status: $FAILED critical service(s) unhealthy${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "  ${YELLOW}Status: Operational ($WARNINGS optional service(s) down)${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
else
    echo -e "  ${GREEN}Status: All systems operational${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 0
fi
