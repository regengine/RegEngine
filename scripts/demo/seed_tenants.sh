#!/bin/bash
# Seed tenants with FSMA 204 target market companies & Generate Frontend Mocks
# This creates tenants, seeds data, and syncs IDs to the frontend

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
FRONTEND_MOCKS="$PROJECT_ROOT/frontend/src/lib/mock-tenants.ts"

cd "$PROJECT_ROOT"

echo "🏢 Seeding tenants & Syncing Frontend..."

# Get admin master key from .env
source .env 2>/dev/null || true
ADMIN_KEY=${ADMIN_MASTER_KEY:-regengine-admin-secret}

# Check if admin-api is up
if ! curl -sf http://localhost:8400/health > /dev/null 2>&1; then
    echo "❌ Admin API is not running. Please start the stack first."
    exit 1
fi

echo "   Admin API is ready."

# Initialize Frontend Mocks File
echo "export interface Tenant {" > "$FRONTEND_MOCKS"
echo "    id: string;" >> "$FRONTEND_MOCKS"
echo "    name: string;" >> "$FRONTEND_MOCKS"
echo "}" >> "$FRONTEND_MOCKS"
echo "" >> "$FRONTEND_MOCKS"
echo "export const MOCK_TENANTS: Tenant[] = [" >> "$FRONTEND_MOCKS"
echo "    { id: '00000000-0000-0000-0000-000000000001', name: 'System Admin' }," >> "$FRONTEND_MOCKS"

# Define Retailers and Suppliers
declare -a RETAILERS=(
    "National Foods Corp"
    "MegaMart Inc"
    "Premier Grocery Co"
    "Fresh Market Group"
    "ValueMart Corp"
)

declare -a SUPPLIERS=(
    "Taylor Farms"
    "Fresh Express"
    "Dole Fresh Vegetables"
    "Earthbound Farm"
    "Ready Pac Foods"
    "Trident Seafoods"
    "High Liner Foods"
    "Bumble Bee Foods"
    "Thai Union Group"
    "Ocean Beauty Seafoods"
    "Pacific Seafood"
    "Chicken of the Sea"
    "Clearwater Seafoods"
    "Red Chamber Co"
    "Mann Packing"
    "Tanimura & Antle"
    "Church Brothers Farms"
    "Boskovich Farms"
    "D'Arrigo California"
    "Sunset Produce"
)

create_and_seed() {
    local company=$1
    local profile=$2
    
    echo "   Processing: $company ($profile)"
    
    # Create Tenant
    response=$(curl -s -X POST "http://localhost:8400/v1/admin/tenants" \
        -H "Content-Type: application/json" \
        -H "X-Admin-Key: $ADMIN_KEY" \
        -d "{\"name\": \"$company\"}")
    
    if echo "$response" | grep -q "tenant_id"; then
        tenant_id=$(echo "$response" | grep -o '"tenant_id":"[^"]*"' | cut -d'"' -f4)
        
        # Add to Frontend Mocks
        # Use double quotes to handle names with apostrophes (e.g., D'Arrigo)
        echo "    { id: '$tenant_id', name: \"$company\" }," >> "$FRONTEND_MOCKS"
        
        # Create API key (silently)
        curl -s -X POST "http://localhost:8400/v1/admin/keys" \
            -H "Content-Type: application/json" \
            -H "X-Admin-Key: $ADMIN_KEY" \
            -d "{\"name\": \"$company API Key\", \"tenant_id\": \"$tenant_id\", \"scopes\": [\"read\", \"write\", \"ingest\"]}" > /dev/null
            
        # Seed Data
        # Export connection strings for localhost access (since script runs on host)
        export DATABASE_URL="postgresql://regengine:regengine@localhost:5432/regengine"
        export NEO4J_URI="bolt://localhost:7687"
        export NEO4J_AUTH="neo4j/password" # Default dev password
        
        python3 scripts/demo/load_demo_data.py --tenant-id "$tenant_id" --profile "$profile" > /dev/null 2>&1
        echo "     ✅ Created & Seeded ($tenant_id)"
    else
        echo "     ⚠️  Failed to create tenant"
    fi
}

# Process Retailers
echo "   --- Retailers ---"
for company in "${RETAILERS[@]}"; do
    create_and_seed "$company" "retailer"
done

# Process Suppliers
echo "   --- Suppliers ---"
for company in "${SUPPLIERS[@]}"; do
    create_and_seed "$company" "supplier"
done

# Close Frontend Mocks File
echo "];" >> "$FRONTEND_MOCKS"

echo ""
echo "✅ Seeding & Sync Complete!"
echo "   Frontend mocks updated at: $FRONTEND_MOCKS"
echo ""
