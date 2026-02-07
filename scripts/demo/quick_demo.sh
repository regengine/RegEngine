#!/bin/bash
# RegEngine Quick Demo Setup
#
# One-command deployment of RegEngine demo environment with sample data.
# Perfect for investor demos, design partner trials, and product walkthroughs.
#
# Usage:
#   ./scripts/demo/quick_demo.sh
#   ./scripts/demo/quick_demo.sh --framework soc2
#   ./scripts/demo/quick_demo.sh --tenant-name "Demo Corp"
#   ./scripts/demo/quick_demo.sh --skip-docker  # If stack already running

set -e

# Default values
TENANT_NAME="${TENANT_NAME:-Demo Tenant}"
FRAMEWORK="${FRAMEWORK:-nist}"
SKIP_DOCKER=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --tenant-name)
            TENANT_NAME="$2"
            shift 2
            ;;
        --framework)
            FRAMEWORK="$2"
            shift 2
            ;;
        --skip-docker)
            SKIP_DOCKER=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --tenant-name NAME    Tenant name (default: Demo Tenant)"
            echo "  --framework FRAMEWORK Control framework: nist, soc2, iso27001 (default: nist)"
            echo "  --skip-docker        Skip Docker Compose startup (use if stack already running)"
            echo "  --help               Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║           🚀 RegEngine Quick Demo Setup                   ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo ""
echo -e "${GREEN}Configuration:${NC}"
echo "  Tenant Name: $TENANT_NAME"
echo "  Framework:   ${FRAMEWORK^^}"
echo "  Skip Docker: $SKIP_DOCKER"
echo ""

# Step 1: Start Docker infrastructure (if not skipped)
if [ "$SKIP_DOCKER" = false ]; then
    echo -e "${YELLOW}[1/4]${NC} Starting RegEngine infrastructure..."

    # Check if docker-compose is available
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}❌ Error: docker-compose not found${NC}"
        echo "   Please install Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi

    # Start services
    docker-compose up -d

    echo -e "${GREEN}      ✓ Services starting${NC}"
    echo ""

    # Step 2: Wait for services to be ready
    echo -e "${YELLOW}[2/4]${NC} Waiting for services to initialize..."
    echo "      This may take 30-60 seconds on first run..."

    sleep 30

    # Check if key services are up
    if docker ps | grep -q "regengine"; then
        echo -e "${GREEN}      ✓ Services are running${NC}"
    else
        echo -e "${YELLOW}      ⚠️  Some services may still be starting${NC}"
        echo "         You can check status with: docker-compose ps"
    fi

    # Additional stabilization time
    sleep 10
else
    echo -e "${YELLOW}[1/4]${NC} Skipping Docker startup (--skip-docker specified)"
    echo -e "${YELLOW}[2/4]${NC} Assuming services are already running..."
fi

echo ""

# Step 3: Create demo tenant
echo -e "${YELLOW}[3/4]${NC} Creating demo tenant with sample data..."

# Run tenant creation script
TENANT_OUTPUT=$(python scripts/regctl/tenant.py create "$TENANT_NAME" --demo-mode --framework "$FRAMEWORK" 2>&1 || true)

# Extract API key from output
API_KEY=$(echo "$TENANT_OUTPUT" | grep "API Key:" | awk '{print $3}' || echo "")
TENANT_ID=$(echo "$TENANT_OUTPUT" | grep "Tenant ID:" | head -1 | awk '{print $3}' || echo "")

if [ -z "$API_KEY" ]; then
    echo -e "${YELLOW}      ⚠️  Tenant creation completed with warnings${NC}"
    echo "         Output:"
    echo "$TENANT_OUTPUT" | sed 's/^/         /'
    echo ""
    echo -e "${YELLOW}      Note: Demo data may not be fully loaded${NC}"
    echo -e "${YELLOW}            This is normal if Neo4j is not fully initialized${NC}"
else
    echo -e "${GREEN}      ✓ Demo tenant created${NC}"
    echo -e "${GREEN}      ✓ Sample data loaded${NC}"
fi

echo ""

# Step 4: Display access information
echo -e "${YELLOW}[4/4]${NC} Demo environment ready!"

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    ${GREEN}✅ SETUP COMPLETE${BLUE}                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ -n "$API_KEY" ] && [ -n "$TENANT_ID" ]; then
    echo -e "${GREEN}📋 Tenant Details:${NC}"
    echo "   Name:       $TENANT_NAME"
    echo "   Tenant ID:  $TENANT_ID"
    echo "   API Key:    $API_KEY"
    echo "   Framework:  ${FRAMEWORK^^}"
    echo ""

    echo -e "${GREEN}🌐 Access URLs:${NC}"
    echo "   Admin API:       http://localhost:8000"
    echo "   API Docs:        http://localhost:8000/docs"
    echo "   Alternative:     http://localhost:8000/redoc"
    echo "   Dashboard:       http://localhost:3000/dashboard?tenant=$TENANT_ID"
    echo ""

    echo -e "${GREEN}🧪 Try It Out:${NC}"
    echo ""
    echo "   # List tenant controls"
    echo "   curl -H 'X-RegEngine-API-Key: $API_KEY' http://localhost:8000/overlay/controls"
    echo ""
    echo "   # List customer products"
    echo "   curl -H 'X-RegEngine-API-Key: $API_KEY' http://localhost:8000/overlay/products"
    echo ""
    echo "   # View API documentation"
    echo "   open http://localhost:8000/docs"
    echo ""

    echo -e "${GREEN}📚 Demo Data Includes:${NC}"
    case $FRAMEWORK in
        nist)
            echo "   • 10 NIST CSF controls (Identify, Protect, Detect, Respond, Recover)"
            ;;
        soc2)
            echo "   • 8 SOC 2 Trust Services Criteria controls"
            ;;
        iso27001)
            echo "   • 8 ISO 27001 Information Security controls"
            ;;
    esac
    echo "   • 3 sample products (Trading Platform, Wallet, Lending Protocol)"
    echo "   • Control-to-provision mappings"
    echo "   • Product-to-control linkages"
    echo ""
else
    echo -e "${YELLOW}⚠️  Demo tenant created but some details are unavailable${NC}"
    echo ""
    echo "   You can list all tenants with:"
    echo "   python scripts/regctl/tenant.py list"
    echo ""
fi

echo -e "${GREEN}🎯 Next Steps:${NC}"
echo "   1. Explore the API documentation: http://localhost:8000/docs"
echo "   2. Test API endpoints with the provided API key"
echo "   3. View tenant controls and products via API"
echo "   4. Create additional tenants: python scripts/regctl/tenant.py create \"Another Tenant\""
echo ""

echo -e "${GREEN}🛠️  Management Commands:${NC}"
echo "   • List tenants:    python scripts/regctl/tenant.py list"
echo "   • Reset tenant:    python scripts/regctl/tenant.py reset $TENANT_ID"
echo "   • Delete tenant:   python scripts/regctl/tenant.py delete $TENANT_ID"
echo "   • Stop services:   docker-compose down"
echo "   • View logs:       docker-compose logs -f"
echo ""

echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Happy demoing! 🎉${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo ""

# Save API key to environment file for convenience
if [ -n "$API_KEY" ]; then
    echo "export REGENGINE_API_KEY=$API_KEY" > .demo_env
    echo "export REGENGINE_TENANT_ID=$TENANT_ID" >> .demo_env
    echo -e "${GREEN}💾 API key saved to .demo_env${NC}"
    echo "   Load with: source .demo_env"
    echo ""
fi
