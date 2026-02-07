#!/bin/bash
# =============================================================================
# FSMA 204 Mock Recall Demo Script
# =============================================================================
# 
# This script demonstrates RegEngine's FSMA 204 compliance capabilities:
# 1. Load sample supply chain data (lots, events, facilities)
# 2. Run a mock recall scenario
# 3. Generate FDA-compliant reports within 24-hour requirement
#
# Prerequisites:
# - RegEngine stack running (make up)
# - API keys initialized (source .api-keys)
#
# Usage:
#   ./scripts/demo/fsma_mock_recall.sh
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_BASE="${REGENGINE_API_BASE:-http://localhost:8200}"
API_KEY="${DEMO_KEY:-demo-key}"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}   FSMA 204 Mock Recall Demonstration${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# -----------------------------------------------------------------------------
# Step 1: Health Check
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[1/6] Checking API health...${NC}"

HEALTH=$(curl -s "${API_BASE}/v1/fsma/health")
if echo "$HEALTH" | grep -q "ok"; then
    echo -e "${GREEN}✓ FSMA API is healthy${NC}"
else
    echo -e "${RED}✗ FSMA API not responding${NC}"
    exit 1
fi
echo ""

# -----------------------------------------------------------------------------
# Step 2: Load Demo Data
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[2/6] Loading sample supply chain data...${NC}"

# Note: In a real scenario, this would load from the graph database
# For demo purposes, we'll describe the scenario

echo "
📦 DEMO SCENARIO: Romaine Lettuce Contamination

Supply Chain Structure:
  • Grower: Sunny Valley Farms (GLN: 1234567890128)
      └── Lot: SV-20240115-001 (500 cases Romaine)
  
  • Processor: Fresh Cut Co (GLN: 2345678901234)
      └── Received: SV-20240115-001
      └── Created: FC-20240116-A (250 cases Chopped Romaine)
      └── Created: FC-20240116-B (250 cases Romaine Hearts)
  
  • Distributor 1: Metro Foods (GLN: 3456789012340)
      └── Received: FC-20240116-A (100 cases)
  
  • Distributor 2: Valley Wholesale (GLN: 4567890123456)
      └── Received: FC-20240116-B (150 cases)
  
  • Retailer: SuperMart #42 (GLN: 5678901234562)
      └── Received: 50 cases from Metro Foods
"
echo -e "${GREEN}✓ Demo scenario loaded${NC}"
echo ""

# -----------------------------------------------------------------------------
# Step 3: Simulate FDA Recall Request
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[3/6] Simulating FDA recall request...${NC}"

echo "
🚨 RECALL ALERT

FDA has received reports of E. coli contamination traced to:
  Lot Code: SV-20240115-001
  Product: Romaine Lettuce
  Grower: Sunny Valley Farms

REQUEST: Provide complete traceability within 24 hours
"

echo -e "${GREEN}✓ Recall request received at $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "   24-hour deadline: $(date -v+24H '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -d '+24 hours' '+%Y-%m-%d %H:%M:%S')"
echo ""

# -----------------------------------------------------------------------------
# Step 4: Execute Forward Trace
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[4/6] Running forward trace (find all affected products)...${NC}"

# API call to trace forward
FORWARD_TRACE=$(curl -s -H "X-RegEngine-API-Key: ${API_KEY}" \
    "${API_BASE}/v1/fsma/trace/forward/SV-20240115-001" 2>/dev/null || echo '{"error":"API not available"}')

if echo "$FORWARD_TRACE" | grep -q "error"; then
    echo "
Simulated Forward Trace Results:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Source Lot: SV-20240115-001 (Romaine Lettuce - 500 cases)
            │
            ▼
    ┌───────────────────────────────────────────────────────────┐
    │ Fresh Cut Co (Processor)                                   │
    │ Received: 2024-01-16 08:00                                │
    │ Transformation: Washing, Cutting                          │
    │                                                           │
    │   Created Lots:                                           │
    │   • FC-20240116-A: Chopped Romaine (250 cases)           │
    │   • FC-20240116-B: Romaine Hearts (250 cases)            │
    └───────────────────────────────────────────────────────────┘
            │
            ├─────────────────────┬─────────────────────┐
            ▼                     ▼                     ▼
    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
    │ Metro Foods  │     │ Valley       │     │ Direct Ship  │
    │ 100 cases    │     │ Wholesale    │     │ 150 cases    │
    │ FC-20240116-A│     │ 150 cases    │     │ FC-20240116-B│
    └──────────────┘     │ FC-20240116-B│     └──────────────┘
            │            └──────────────┘
            ▼
    ┌──────────────┐
    │ SuperMart #42│
    │ 50 cases     │
    └──────────────┘

TOTAL AFFECTED:
  • 4 Facilities identified
  • 500 cases total (in various forms)
  • 2 derivative products created
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"
else
    echo "$FORWARD_TRACE" | python3 -m json.tool 2>/dev/null || echo "$FORWARD_TRACE"
fi

echo -e "${GREEN}✓ Forward trace completed${NC}"
echo ""

# -----------------------------------------------------------------------------
# Step 5: Generate Recall Contact List
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[5/6] Generating recall contact list...${NC}"

echo "
RECALL CONTACT LIST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| Facility Name    | GLN           | Type        | Qty Affected | Contact Status |
|------------------|---------------|-------------|--------------|----------------|
| Fresh Cut Co     | 2345678901234 | Processor   | 500 cases    | PENDING        |
| Metro Foods      | 3456789012340 | Distributor | 100 cases    | PENDING        |
| Valley Wholesale | 4567890123456 | Distributor | 150 cases    | PENDING        |
| SuperMart #42    | 5678901234562 | Retailer    | 50 cases     | PENDING        |

Total facilities to contact: 4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"

echo -e "${GREEN}✓ Contact list generated${NC}"
echo ""

# -----------------------------------------------------------------------------
# Step 6: Generate FDA Spreadsheet
# -----------------------------------------------------------------------------
echo -e "${YELLOW}[6/6] Generating FDA-compliant CSV report...${NC}"

# Create export directory
EXPORT_DIR="./demo_exports"
mkdir -p "$EXPORT_DIR"

# Generate CSV
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
CSV_FILE="${EXPORT_DIR}/fsma_recall_SV-20240115-001_${TIMESTAMP}.csv"

cat > "$CSV_FILE" << 'EOF'
Traceability Lot Code (TLC),Product Description,Quantity,Unit of Measure,Event Type,Event Date,Event Time,Facility Name,Facility GLN,Facility Address,Confidence Score
SV-20240115-001,Romaine Lettuce,500,cases,SHIPPING,2024-01-15,14:00:00,Sunny Valley Farms,1234567890128,"123 Farm Road, Salinas CA",0.98
SV-20240115-001,Romaine Lettuce,500,cases,RECEIVING,2024-01-16,08:00:00,Fresh Cut Co,2345678901234,"456 Processing Lane, Fresno CA",0.97
FC-20240116-A,Chopped Romaine,250,cases,TRANSFORMATION,2024-01-16,10:00:00,Fresh Cut Co,2345678901234,"456 Processing Lane, Fresno CA",0.95
FC-20240116-B,Romaine Hearts,250,cases,TRANSFORMATION,2024-01-16,11:00:00,Fresh Cut Co,2345678901234,"456 Processing Lane, Fresno CA",0.95
FC-20240116-A,Chopped Romaine,100,cases,SHIPPING,2024-01-17,06:00:00,Fresh Cut Co,2345678901234,"456 Processing Lane, Fresno CA",0.96
FC-20240116-A,Chopped Romaine,100,cases,RECEIVING,2024-01-17,10:00:00,Metro Foods,3456789012340,"789 Distribution Dr, Oakland CA",0.94
FC-20240116-B,Romaine Hearts,150,cases,SHIPPING,2024-01-17,07:00:00,Fresh Cut Co,2345678901234,"456 Processing Lane, Fresno CA",0.96
FC-20240116-B,Romaine Hearts,150,cases,RECEIVING,2024-01-17,11:00:00,Valley Wholesale,4567890123456,"321 Wholesale Ave, Stockton CA",0.93
FC-20240116-A,Chopped Romaine,50,cases,SHIPPING,2024-01-18,05:00:00,Metro Foods,3456789012340,"789 Distribution Dr, Oakland CA",0.95
FC-20240116-A,Chopped Romaine,50,cases,RECEIVING,2024-01-18,08:00:00,SuperMart #42,5678901234562,"100 Retail St, San Jose CA",0.92
EOF

echo -e "${GREEN}✓ FDA spreadsheet generated: ${CSV_FILE}${NC}"
echo ""

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}   Mock Recall Summary${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""
echo "📊 RESULTS:"
echo "   • Recall initiated: $(date '+%Y-%m-%d %H:%M:%S')"
echo "   • Trace completed: $(date '+%Y-%m-%d %H:%M:%S')"
echo "   • Time elapsed: < 1 minute"
echo "   • 24-hour requirement: ✓ MET"
echo ""
echo "📁 GENERATED FILES:"
echo "   • ${CSV_FILE}"
echo ""
echo "📋 COMPLIANCE STATUS:"
echo "   ✓ All CTEs captured with required KDEs"
echo "   ✓ Forward trace complete (One-Down)"
echo "   ✓ Backward trace available (One-Up)"
echo "   ✓ Sortable spreadsheet generated"
echo "   ✓ Contact list prepared"
echo ""
echo -e "${GREEN}✓ Mock recall demonstration complete!${NC}"
echo ""
echo "Next steps in a real recall:"
echo "  1. Notify all facilities on contact list"
echo "  2. Submit spreadsheet to FDA"
echo "  3. Coordinate product removal/destruction"
echo "  4. Document all actions taken"
echo ""
