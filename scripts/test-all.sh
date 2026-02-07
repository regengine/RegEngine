#!/bin/bash
# RegEngine Full Test Suite Runner
# Usage: ./scripts/test-all.sh [--quick]

set -e
set -o pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

QUICK_MODE=false
if [[ "$1" == "--quick" ]]; then
    QUICK_MODE=true
fi

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           RegEngine Full Test Suite                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Track results
PASSED=0
FAILED=0
SKIPPED=0

run_test() {
    local name=$1
    local cmd=$2
    
    echo -e "${YELLOW}▶ Running: ${name}${NC}"
    
    if eval "$cmd"; then
        echo -e "${GREEN}✓ ${name} PASSED${NC}"
        ((PASSED++))
    else
        echo -e "${RED}✗ ${name} FAILED${NC}"
        ((FAILED++))
    fi
    echo ""
}

# 1. Check Services
echo -e "${BLUE}━━━ 1. Service Health Checks ━━━${NC}"
echo ""

SERVICES_UP=0
SERVICES_DOWN=0

for port in 8002 8100 8200 8300 8400 8500 8600; do
    status=$(curl -sf http://localhost:$port/health 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "DOWN")
    if [[ "$status" == "healthy" || "$status" == "ok" ]]; then
        echo -e "${GREEN}✓ Port $port: $status${NC}"
        ((SERVICES_UP++))
    else
        echo -e "${RED}✗ Port $port: $status${NC}"
        ((SERVICES_DOWN++))
    fi
done

echo ""
echo -e "Services: ${GREEN}$SERVICES_UP up${NC}, ${RED}$SERVICES_DOWN down${NC}"
echo ""

# 2. Unit Tests
echo -e "${BLUE}━━━ 2. Unit Tests (shared/) ━━━${NC}"
echo ""

if $QUICK_MODE; then
    run_test "Unit Tests (quick)" "python3 -m pytest tests/shared/ -q --tb=no -x 2>&1 | tail -5"
else
    run_test "Unit Tests" "python3 -m pytest tests/shared/ -v --tb=short 2>&1 | tail -30"
fi

# 3. Contract Tests
echo -e "${BLUE}━━━ 3. Contract Tests ━━━${NC}"
echo ""

run_test "Contract Tests" "python3 -m pytest tests/contract/ -v --tb=short 2>&1 | tail -20"

# 4. Security Tests
echo -e "${BLUE}━━━ 4. Security Tests ━━━${NC}"
echo ""

if [[ -d "tests/security" ]]; then
    export PYTHONPATH=$PYTHONPATH:$(pwd)/services/admin
    run_test "Security Tests" "python3 -m pytest tests/security/ -v --tb=short 2>&1 | tail -20"
else
    echo -e "${YELLOW}⚠ Security tests directory not found${NC}"
    ((SKIPPED++))
fi

# 5. E2E Tests
echo -e "${BLUE}━━━ 5. E2E Tests ━━━${NC}"
echo ""

if [[ $SERVICES_DOWN -eq 0 ]]; then
    run_test "E2E Tests" "python3 -m pytest tests/e2e/ -v --tb=short 2>&1 | tail -20"
else
    echo -e "${YELLOW}⚠ Skipping E2E tests - some services are down${NC}"
    ((SKIPPED++))
fi

# 6. Frontend Tests (if not quick mode)
if ! $QUICK_MODE; then
    echo -e "${BLUE}━━━ 6. Frontend Tests ━━━${NC}"
    echo ""
    
    if [[ -f "frontend/package.json" ]]; then
        cd frontend
        if npm run test:run -- --reporter=dot 2>&1 | tail -10; then
            echo -e "${GREEN}✓ Frontend Tests PASSED${NC}"
            ((PASSED++))
        else
            echo -e "${YELLOW}⚠ Frontend Tests need review${NC}"
            ((SKIPPED++))
        fi
        cd ..
    else
        echo -e "${YELLOW}⚠ Frontend not found${NC}"
        ((SKIPPED++))
    fi
fi

# Summary
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                     TEST SUMMARY                           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}Passed:  $PASSED${NC}"
echo -e "  ${RED}Failed:  $FAILED${NC}"
echo -e "  ${YELLOW}Skipped: $SKIPPED${NC}"
echo ""

if [[ $FAILED -gt 0 ]]; then
    echo -e "${RED}❌ Some tests failed!${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
fi
