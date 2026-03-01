#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting RegEngine Production Setup...${NC}"

# 1. Check Prerequisites
echo -e "\n${GREEN}[1/5] Checking Prerequisites...${NC}"
command -v aws >/dev/null 2>&1 || { echo -e "${RED}Error: aws CLI is required but not installed.${NC}"; exit 1; }
command -v terraform >/dev/null 2>&1 || { echo -e "${RED}Error: terraform is required but not installed.${NC}"; exit 1; }
command -v gh >/dev/null 2>&1 || { echo -e "${RED}Error: gh CLI is required but not installed.${NC}"; exit 1; }

# 2. AWS Authentication Check
echo -e "\n${GREEN}[2/5] Verifying AWS Access...${NC}"
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "AWS credentials not found. Please configure them now."
    aws configure
fi
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Authenticated as AWS Account: $ACCOUNT_ID"

# 3. Bootstrap Infrastructure
echo -e "\n${GREEN}[3/5] Bootstrapping Infrastructure...${NC}"
chmod +x infra/bootstrap.sh
./infra/bootstrap.sh

# 4. Initialize Terraform
echo -e "\n${GREEN}[4/5] Initializing Terraform...${NC}"
cd infra/terraform
terraform init
cd ../..

# 5. Configure GitHub Secrets
echo -e "\n${GREEN}[5/5] Configuring GitHub Secrets...${NC}"
echo "We need to set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY for the deployment workflow."

# Extract credentials from AWS CLI config if available, or prompt
AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id)
AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key)

if [ -z "$AWS_ACCESS_KEY_ID" ]; then
    read -p "Enter AWS Access Key ID: " AWS_ACCESS_KEY_ID
fi
if [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
    read -s -p "Enter AWS Secret Access Key: " AWS_SECRET_ACCESS_KEY
    echo ""
fi

# Set secrets
echo "Setting AWS_ACCESS_KEY_ID..."
echo "$AWS_ACCESS_KEY_ID" | gh secret set AWS_ACCESS_KEY_ID
echo "Setting AWS_SECRET_ACCESS_KEY..."
echo "$AWS_SECRET_ACCESS_KEY" | gh secret set AWS_SECRET_ACCESS_KEY

echo -e "\n${GREEN}Setup Complete!${NC}"
echo "You can now push to main to trigger the deployment pipeline."
