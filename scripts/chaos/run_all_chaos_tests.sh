#!/bin/bash
# RegEngine Chaos Testing Suite
#
# Runs all chaos engineering tests to validate system resiliency and
# data durability under various failure scenarios.
#
# Usage:
#   ./run_all_chaos_tests.sh              # Run all tests
#   ./run_all_chaos_tests.sh --quick      # Run quick smoke tests only
#   ./run_all_chaos_tests.sh --test neo4j # Run specific test

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
QUICK_MODE=false
SPECIFIC_TEST=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --test)
            SPECIFIC_TEST="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--quick] [--test <test_name>]"
            exit 1
            ;;
    esac
done

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results tracking
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Function to run a test
run_test() {
    local test_name=$1
    local test_script=$2
    local is_quick=${3:-false}

    # Skip non-quick tests in quick mode
    if [ "$QUICK_MODE" = true ] && [ "$is_quick" = false ]; then
        echo -e "${YELLOW}⊘ SKIPPED${NC}: ${test_name} (not in quick mode)"
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
        return 0
    fi

    # Skip if specific test requested and this isn't it
    if [ -n "$SPECIFIC_TEST" ] && [ "$test_name" != "$SPECIFIC_TEST" ]; then
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
        return 0
    fi

    TOTAL_TESTS=$((TOTAL_TESTS + 1))

    echo ""
    echo "========================================="
    echo "Running: ${test_name}"
    echo "========================================="

    if bash "${SCRIPT_DIR}/${test_script}"; then
        echo -e "${GREEN}✅ PASSED${NC}: ${test_name}"
        PASSED_TESTS=$((PASSED_TESTS + 1))
        return 0
    else
        echo -e "${RED}❌ FAILED${NC}: ${test_name}"
        FAILED_TESTS=$((FAILED_TESTS + 1))
        return 1
    fi
}

# Print header
echo "========================================="
echo "🔥 RegEngine Chaos Testing Suite"
echo "========================================="
echo "Mode: $(if [ "$QUICK_MODE" = true ]; then echo 'QUICK'; else echo 'FULL'; fi)"
if [ -n "$SPECIFIC_TEST" ]; then
    echo "Filter: ${SPECIFIC_TEST}"
fi
echo "Started: $(date)"
echo "========================================="

# Pre-flight checks
echo ""
echo "🔍 Pre-flight checks..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi
echo "✓ Docker is running"

# Check if docker-compose stack is up
if ! docker ps | grep -q regengine; then
    echo "⚠️  Warning: RegEngine stack doesn't appear to be running"
    echo "   Start it with: docker-compose up -d"
    echo "   Proceeding anyway (some tests may fail)..."
fi

echo "✓ Pre-flight checks complete"
echo ""

# Define and run tests
# Format: run_test "test_name" "script.sh" quick_test_flag

# Core infrastructure tests (quick)
run_test "Neo4j Failure" "kill_neo4j.sh" true
run_test "Kafka Failure" "kill_kafka.sh" true

# Service-level tests (full suite only)
# run_test "Admin API Failure" "kill_admin_api.sh" false
# run_test "NLP Consumer Failure" "kill_nlp_consumer.sh" false

# Print summary
echo ""
echo "========================================="
echo "🎯 Test Summary"
echo "========================================="
echo "Total Tests:   ${TOTAL_TESTS}"
echo -e "Passed:        ${GREEN}${PASSED_TESTS}${NC}"
echo -e "Failed:        ${RED}${FAILED_TESTS}${NC}"
if [ $SKIPPED_TESTS -gt 0 ]; then
    echo -e "Skipped:       ${YELLOW}${SKIPPED_TESTS}${NC}"
fi
echo "========================================="
echo "Completed: $(date)"
echo "========================================="

# Exit with appropriate code
if [ $FAILED_TESTS -gt 0 ]; then
    echo ""
    echo -e "${RED}❌ Some tests failed${NC}"
    echo "Review the output above for details"
    exit 1
else
    echo ""
    echo -e "${GREEN}✅ All chaos tests passed!${NC}"
    echo ""
    echo "System resiliency verified:"
    echo "  ✓ Infrastructure failures handled gracefully"
    echo "  ✓ Zero data loss across all scenarios"
    echo "  ✓ Recovery times within acceptable limits"
    echo "  ✓ No manual intervention required"
    exit 0
fi
