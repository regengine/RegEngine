#!/bin/bash
set -e
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Starting RegEngine Production Setup for Railway...${NC}"

# 1. Check Prerequisites
echo -e "\n${GREEN}[1/3] Checking Prerequisites...${NC}"
command -v railway >/dev/null 2>&1 || { echo "Railway CLI required."; exit 1; }
command -v gh >/dev/null 2>&1 || { echo "GitHub CLI required."; exit 1; }

# 2. Authentication & Linking
echo -e "\n${GREEN}[2/3] Verifying Railway Connection...${NC}"
railway whoami || railway login
# Use the --id flag for the Project ID
railway link --id 4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51

# 3. Deploy
echo -e "\n${GREEN}[3/3] Deploying to Railway...${NC}"
# --force ensures it starts the upload right away
railway up --force
