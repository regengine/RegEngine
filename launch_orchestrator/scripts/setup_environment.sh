#!/bin/bash

# RegEngine Launch Orchestrator - Environment Setup Script
# This script helps you configure the orchestrator environment

set -e

echo "========================================="
echo "  RegEngine Launch Orchestrator Setup"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if .env already exists
if [ -f .env ]; then
    echo -e "${YELLOW}Warning: .env file already exists${NC}"
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled. Keeping existing .env file."
        exit 0
    fi
fi

# Copy example file
echo "Creating .env from .env.example..."
cp .env.example .env

echo -e "${GREEN}✓ Created .env file${NC}"
echo ""

# Interactive configuration
echo "Let's configure your environment interactively."
echo "Press ENTER to skip any field (will use placeholder value)."
echo ""

# AWS Configuration
echo "========================================="
echo "  AWS Configuration"
echo "========================================="
echo ""

read -p "AWS Access Key ID: " aws_key
if [ ! -z "$aws_key" ]; then
    sed -i "s/AWS_ACCESS_KEY_ID=.*/AWS_ACCESS_KEY_ID=$aws_key/" .env
fi

read -sp "AWS Secret Access Key: " aws_secret
echo ""
if [ ! -z "$aws_secret" ]; then
    sed -i "s/AWS_SECRET_ACCESS_KEY=.*/AWS_SECRET_ACCESS_KEY=$aws_secret/" .env
fi

read -p "AWS Region (default: us-east-1): " aws_region
if [ ! -z "$aws_region" ]; then
    sed -i "s/AWS_REGION=.*/AWS_REGION=$aws_region/" .env
fi

echo ""

# CRM Configuration
echo "========================================="
echo "  CRM Configuration"
echo "========================================="
echo ""
echo "Choose CRM provider:"
echo "  1) HubSpot"
echo "  2) Salesforce"
echo "  3) Skip (configure manually later)"
echo ""

read -p "Choice (1-3): " crm_choice

case $crm_choice in
    1)
        read -p "HubSpot API Key: " hubspot_key
        if [ ! -z "$hubspot_key" ]; then
            sed -i "s/CRM_API_TOKEN=.*/CRM_API_TOKEN=$hubspot_key/" .env
            sed -i "s/CRM_PROVIDER=.*/CRM_PROVIDER=hubspot/" .env
        fi
        ;;
    2)
        read -p "Salesforce OAuth Token: " sf_token
        if [ ! -z "$sf_token" ]; then
            sed -i "s/CRM_API_TOKEN=.*/CRM_API_TOKEN=$sf_token/" .env
            sed -i "s/CRM_PROVIDER=.*/CRM_PROVIDER=salesforce/" .env
        fi
        read -p "Salesforce Instance URL: " sf_url
        if [ ! -z "$sf_url" ]; then
            echo "SALESFORCE_INSTANCE_URL=$sf_url" >> .env
        fi
        ;;
    *)
        echo "Skipping CRM configuration"
        ;;
esac

echo ""

# Email Provider
echo "========================================="
echo "  Email Provider Configuration"
echo "========================================="
echo ""
echo "Choose email provider:"
echo "  1) SendGrid"
echo "  2) Mailchimp"
echo "  3) AWS SES"
echo "  4) Skip (configure manually later)"
echo ""

read -p "Choice (1-4): " email_choice

case $email_choice in
    1)
        read -p "SendGrid API Key: " sendgrid_key
        if [ ! -z "$sendgrid_key" ]; then
            sed -i "s/EMAIL_PROVIDER_API_KEY=.*/EMAIL_PROVIDER_API_KEY=$sendgrid_key/" .env
            sed -i "s/EMAIL_PROVIDER=.*/EMAIL_PROVIDER=sendgrid/" .env
        fi
        ;;
    2)
        read -p "Mailchimp API Key: " mailchimp_key
        if [ ! -z "$mailchimp_key" ]; then
            sed -i "s/EMAIL_PROVIDER_API_KEY=.*/EMAIL_PROVIDER_API_KEY=$mailchimp_key/" .env
            sed -i "s/EMAIL_PROVIDER=.*/EMAIL_PROVIDER=mailchimp/" .env
        fi
        read -p "Mailchimp List ID: " mailchimp_list
        if [ ! -z "$mailchimp_list" ]; then
            echo "MAILCHIMP_LIST_ID=$mailchimp_list" >> .env
        fi
        ;;
    3)
        sed -i "s/EMAIL_PROVIDER=.*/EMAIL_PROVIDER=ses/" .env
        echo "Using AWS credentials already configured"
        ;;
    *)
        echo "Skipping email provider configuration"
        ;;
esac

read -p "Email From Address (e.g., hello@regengine.ai): " email_from
if [ ! -z "$email_from" ]; then
    sed -i "s/EMAIL_FROM_ADDRESS=.*/EMAIL_FROM_ADDRESS=$email_from/" .env
fi

echo ""

# LinkedIn
echo "========================================="
echo "  LinkedIn Configuration"
echo "========================================="
echo ""
echo -e "${YELLOW}WARNING: Only use LinkedIn-approved automation tools${NC}"
echo "Unauthorized automation violates LinkedIn Terms of Service"
echo ""

read -p "Do you have an approved LinkedIn API token? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    read -p "LinkedIn API Token: " linkedin_token
    if [ ! -z "$linkedin_token" ]; then
        sed -i "s/LINKEDIN_AUTOMATION_TOKEN=.*/LINKEDIN_AUTOMATION_TOKEN=$linkedin_token/" .env
        sed -i "s/ENABLE_LINKEDIN_AUTOMATION=.*/ENABLE_LINKEDIN_AUTOMATION=true/" .env
    fi
else
    echo "LinkedIn automation will be disabled"
    sed -i "s/ENABLE_LINKEDIN_AUTOMATION=.*/ENABLE_LINKEDIN_AUTOMATION=false/" .env
fi

echo ""

# Calendly
echo "========================================="
echo "  Scheduling Configuration"
echo "========================================="
echo ""

read -p "Calendly booking link: " calendly_link
if [ ! -z "$calendly_link" ]; then
    sed -i "s|CALENDLY_LINK=.*|CALENDLY_LINK=$calendly_link|" .env
fi

echo ""

# Slack notifications
echo "========================================="
echo "  Slack Notifications (Optional)"
echo "========================================="
echo ""

read -p "Slack Webhook URL (or press ENTER to skip): " slack_webhook
if [ ! -z "$slack_webhook" ]; then
    sed -i "s|SLACK_WEBHOOK_URL=.*|SLACK_WEBHOOK_URL=$slack_webhook|" .env
    sed -i "s/ENABLE_SLACK_NOTIFICATIONS=.*/ENABLE_SLACK_NOTIFICATIONS=true/" .env
else
    sed -i "s/ENABLE_SLACK_NOTIFICATIONS=.*/ENABLE_SLACK_NOTIFICATIONS=false/" .env
fi

echo ""
echo "========================================="
echo "  Setup Complete!"
echo "========================================="
echo ""
echo -e "${GREEN}✓ Environment configured${NC}"
echo ""
echo "Configuration saved to: .env"
echo ""
echo "Next steps:"
echo "  1. Review .env file and verify all values"
echo "  2. Run dry-run test: python orchestrator.py --mode dry_run"
echo "  3. Execute sales launch: python orchestrator.py --mode sales_only"
echo ""
echo -e "${YELLOW}IMPORTANT: Never commit .env to version control!${NC}"
echo ""

# Validate configuration
echo "Validating configuration..."
echo ""

# Check for placeholder values
if grep -q "your-" .env; then
    echo -e "${YELLOW}⚠ Warning: Some placeholder values remain in .env${NC}"
    echo "   You may need to update these manually:"
    grep "your-" .env | sed 's/^/   /'
    echo ""
fi

# Test Python dependencies
if command -v python3 &> /dev/null; then
    echo "Checking Python dependencies..."
    if python3 -c "import yaml" 2>/dev/null; then
        echo -e "${GREEN}✓ PyYAML installed${NC}"
    else
        echo -e "${YELLOW}⚠ PyYAML not installed${NC}"
        echo "   Run: pip install -r requirements.txt"
    fi
else
    echo -e "${RED}✗ Python 3 not found${NC}"
    echo "   Please install Python 3.8 or higher"
fi

echo ""
echo "Setup script complete!"
