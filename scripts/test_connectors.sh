#!/bin/bash
# Connector Verification Script

echo "Testing FDA Client Scaffolding..."
python3 -c "from shared.external_connectors.fda_client import FDAClient; client = FDAClient(); print('FDA Client Import: OK')"

echo "Testing NERC Client Scaffolding..."
python3 -c "from shared.external_connectors.nerc_client import NERCClient; client = NERCClient(); print('NERC Client Import: OK')"

echo "Verification Complete."
