#!/bin/bash
set -e

RUN_ID=$(date +%s)
echo "Starting Verification Run: $RUN_ID"

echo "----------------------------------------"
echo "Step 1: Seeding V1 Data (Old World)"
python3 scripts/seed_v1_data.py $RUN_ID

echo "Waiting for processing..."
sleep 10

echo "----------------------------------------"
echo "Step 2: Live Verification (New World Ingestion)"
python3 scripts/verify_live_freshness.py $RUN_ID

echo "Waiting for processing..."
sleep 60

echo "----------------------------------------"
echo "Step 3: Lineage Verification"
python3 scripts/verify_compliance_lineage.py $RUN_ID

echo "----------------------------------------"
echo "✅ FULL VERIFICATION SUCCESSFUL"
