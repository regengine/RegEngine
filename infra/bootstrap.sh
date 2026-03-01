#!/bin/bash
set -e

# Configuration
AWS_REGION="${AWS_REGION:-us-east-1}"
BUCKET_NAME="regengine-terraform-state"
DYNAMODB_TABLE="regengine-terraform-locks"

# Colors
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Infrastructure Bootstrap for RegEngine...${NC}"
echo "Region: $AWS_REGION"
echo "Bucket: $BUCKET_NAME"
echo "Table:  $DYNAMODB_TABLE"

# Check for AWS CLI
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed."
    exit 1
fi

# 1. Create S3 Bucket for Terraform State
echo -e "\n${GREEN}[1/4] Checking S3 Bucket...${NC}"
if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
    echo "Bucket $BUCKET_NAME already exists."
else
    echo "Creating bucket $BUCKET_NAME..."
    if [ "$AWS_REGION" == "us-east-1" ]; then
        aws s3api create-bucket --bucket "$BUCKET_NAME" --region "$AWS_REGION"
    else
        aws s3api create-bucket --bucket "$BUCKET_NAME" --region "$AWS_REGION" --create-bucket-configuration LocationConstraint="$AWS_REGION"
    fi
fi

# 2. Enable S3 Versioning
echo -e "\n${GREEN}[2/4] Enabling Bucket Versioning...${NC}"
aws s3api put-bucket-versioning --bucket "$BUCKET_NAME" --versioning-configuration Status=Enabled
echo "Versioning enabled."

# 3. Enable S3 Encryption
echo -e "\n${GREEN}[3/4] Enabling Bucket Encryption...${NC}"
aws s3api put-bucket-encryption --bucket "$BUCKET_NAME" --server-side-encryption-configuration '{
  "Rules": [
    {
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }
  ]
}'
echo "Encryption enabled."

# 4. Create DynamoDB Table for State Locking
echo -e "\n${GREEN}[4/4] Checking DynamoDB Table...${NC}"
if aws dynamodb describe-table --table-name "$DYNAMODB_TABLE" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "Table $DYNAMODB_TABLE already exists."
else
    echo "Creating table $DYNAMODB_TABLE..."
    aws dynamodb create-table \
        --table-name "$DYNAMODB_TABLE" \
        --attribute-definitions AttributeName=LockID,AttributeType=S \
        --key-schema AttributeName=LockID,KeyType=HASH \
        --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5 \
        --region "$AWS_REGION"
    
    echo "Waiting for table to be active..."
    aws dynamodb wait table-exists --table-name "$DYNAMODB_TABLE" --region "$AWS_REGION"
    echo "Table created successfully."
fi

echo -e "\n${GREEN}Bootstrap Complete!${NC}"
echo "You can now run 'terraform init' in infra/terraform/"
