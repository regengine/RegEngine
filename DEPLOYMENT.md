# RegEngine AWS Deployment Guide

This guide walks through deploying RegEngine to AWS using Terraform and ECS/Fargate.

## Prerequisites

- AWS Account with appropriate permissions
- AWS CLI configured (`aws configure`)
- Terraform >= 1.5.0 installed
- Docker installed for building images
- Git

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Application Load Balancer            │
│            (HTTPS with ACM Certificate)                 │
└──────────┬──────────────┬──────────────┬────────────────┘
           │              │              │
    ┌──────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
    │   Admin     │ │ Ingestion│ │ Opportunity │
    │   API       │ │  Service │ │     API     │
    │  (ECS)      │ │  (ECS)   │ │   (ECS)     │
    └─────────────┘ └────┬─────┘ └──────┬──────┘
                         │               │
            ┌────────────▼───────────────▼───────┐
            │     MSK (Managed Kafka)             │
            └────────┬───────────────┬────────────┘
                     │               │
            ┌────────▼──────┐ ┌──────▼──────────┐
            │  NLP Service  │ │  Graph Service  │
            │    (ECS)      │ │     (ECS)       │
            └───────┬───────┘ └────────┬─────────┘
                    │                  │
            ┌───────▼──────────────────▼─────────┐
            │   S3 (Raw + Processed Buckets)     │
            └────────────────────────────────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Neo4j (EC2/Aura)    │
                    └──────────────────────┘
```

## Step 1: Initial AWS Setup

### 1.1 Create Terraform State Backend (One-time setup)

```bash
# Create S3 bucket for Terraform state
aws s3api create-bucket \
  --bucket regengine-terraform-state \
  --region us-east-1

aws s3api put-bucket-versioning \
  --bucket regengine-terraform-state \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket regengine-terraform-state \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### 1.2 Configure Terraform Backend

Edit `infra/main.tf` and uncomment the backend configuration:

```hcl
backend "s3" {
  bucket         = "regengine-terraform-state"
  key            = "prod/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "terraform-state-lock"
}
```

## Step 2: Configure Infrastructure

### 2.1 Create terraform.tfvars

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your specific configuration:

```hcl
project_name = "regengine"
environment  = "prod"
aws_region   = "us-east-1"

# Scale as needed
ingestion_service_count = 2
nlp_service_count       = 2
graph_service_count     = 2
opportunity_api_count   = 2
admin_api_count         = 1
```

### 2.2 Review and Customize

**NOTE**: The Terraform configuration in `infra/modules/` includes:
- ✅ **VPC**: Fully implemented with public/private subnets, NAT gateways
- ✅ **S3**: Raw and processed data buckets with encryption and lifecycle policies
- ✅ **ECR**: Container image repositories for all services
- ✅ **Secrets Manager**: Secure storage for credentials
- ⚠️  **ECS, ALB, MSK, Neo4j, IAM**: Placeholder modules (need completion before deployment)

**To complete the infrastructure, you need to implement:**
1. `modules/iam/` - IAM roles and policies
2. `modules/alb/` - Application Load Balancer and target groups
3. `modules/ecs-cluster/` - ECS cluster configuration
4. `modules/ecs-service/` - ECS Fargate services
5. `modules/kafka/` - MSK cluster
6. `modules/neo4j/` - Neo4j database (EC2 or Aura integration)
7. `modules/security-groups/` - Security group rules

## Step 3: Deploy Infrastructure (When modules are complete)

### 3.1 Initialize Terraform

```bash
cd infra
terraform init
```

### 3.2 Plan Deployment

```bash
terraform plan -out=tfplan
```

Review the plan carefully before applying.

### 3.3 Apply Infrastructure

```bash
terraform apply tfplan
```

This will create:
- VPC with public/private subnets across 3 AZs
- S3 buckets for data storage
- ECR repositories for Docker images
- Secrets in AWS Secrets Manager
- (When modules complete): ECS cluster, ALB, MSK, Neo4j, IAM roles

### 3.4 Get Outputs

```bash
terraform output
```

Save these values - you'll need them for deployment.

## Step 4: Build and Push Docker Images

### 4.1 Authenticate to ECR

```bash
# Get ECR login token
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com
```

### 4.2 Build Images

From the repository root:

```bash
# Get ECR repository URLs from Terraform output
ADMIN_REPO=$(terraform -chdir=infra output -raw ecr_repositories | jq -r '.admin_api')
INGESTION_REPO=$(terraform -chdir=infra output -raw ecr_repositories | jq -r '.ingestion')
NLP_REPO=$(terraform -chdir=infra output -raw ecr_repositories | jq -r '.nlp')
GRAPH_REPO=$(terraform -chdir=infra output -raw ecr_repositories | jq -r '.graph')
OPPORTUNITY_REPO=$(terraform -chdir=infra output -raw ecr_repositories | jq -r '.opportunity')

# Build and push
docker build -t $ADMIN_REPO:latest -f services/admin/Dockerfile .
docker push $ADMIN_REPO:latest

docker build -t $INGESTION_REPO:latest -f services/ingestion/dockerfile .
docker push $INGESTION_REPO:latest

docker build -t $NLP_REPO:latest -f services/nlp/dockerfile .
docker push $NLP_REPO:latest

docker build -t $GRAPH_REPO:latest -f services/graph/dockerfile .
docker push $GRAPH_REPO:latest

docker build -t $OPPORTUNITY_REPO:latest -f services/opportunity/dockerfile .
docker push $OPPORTUNITY_REPO:latest
```

### 4.3 Automated Build Script

Use the included script:

```bash
bash scripts/build-and-push.sh
```

## Step 5: Configure DNS (Optional but Recommended)

### 5.1 Request ACM Certificate

```bash
aws acm request-certificate \
  --domain-name api.regengine.yourdomain.com \
  --validation-method DNS \
  --region us-east-1
```

### 5.2 Create DNS Records

Point your domain to the ALB:

```bash
ALB_DNS=$(terraform -chdir=infra output -raw alb_dns_name)

# Create CNAME record in Route53 or your DNS provider
aws route53 change-resource-record-sets \
  --hosted-zone-id YOUR_ZONE_ID \
  --change-batch '{
    "Changes": [{
      "Action": "UPSERT",
      "ResourceRecordSet": {
        "Name": "api.regengine.yourdomain.com",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [{"Value": "'$ALB_DNS'"}]
      }
    }]
  }'
```

## Step 6: Initialize API Keys

### 6.1 Get Admin Master Key

```bash
ADMIN_KEY=$(aws secretsmanager get-secret-value \
  --secret-id regengine/prod/admin-master-key \
  --query SecretString \
  --output text)
```

### 6.2 Create API Keys

```bash
ALB_URL=$(terraform -chdir=infra output -raw alb_url)

# Create demo key
curl -X POST https://api.regengine.yourdomain.com/admin/keys \
  -H "Content-Type: application/json" \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -d '{
    "name": "Production Demo Key",
    "rate_limit_per_minute": 100,
    "scopes": ["read", "ingest"]
  }'
```

Save the returned API key securely.

## Step 7: Monitoring Setup

### 7.1 Enable CloudWatch Container Insights

Already enabled via `enable_container_insights = true`.

View metrics:
```bash
aws cloudwatch get-dashboard \
  --dashboard-name regengine-prod-ecs
```

### 7.2 Configure Alarms

```bash
# Example: High error rate alarm
aws cloudwatch put-metric-alarm \
  --alarm-name regengine-high-error-rate \
  --alarm-description "Alert when error rate exceeds 5%" \
  --metric-name HTTPCode_Target_5XX_Count \
  --namespace AWS/ApplicationELB \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 50 \
  --comparison-operator GreaterThanThreshold
```

## Step 8: Test Deployment

### 8.1 Health Checks

```bash
ALB_URL=$(terraform -chdir=infra output -raw alb_url)

curl $ALB_URL/admin/health
curl $ALB_URL/ingestion/health
curl $ALB_URL/opportunity/health
```

### 8.2 Functional Test

```bash
# Get an API key first (from Step 6.2)
API_KEY="your-api-key-here"

# Ingest a test document
curl -X POST $ALB_URL/ingestion/ingest/url \
  -H "Content-Type: application/json" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -d '{
    "url": "https://www.sec.gov/example-regulation.pdf",
    "source_system": "test"
  }'

# Query opportunities (after data is processed)
curl "$ALB_URL/opportunity/opportunities/gaps?j1=US&j2=EU&limit=10" \
  -H "X-RegEngine-API-Key: $API_KEY"
```

## Step 9: Ongoing Maintenance

### 9.1 Update Services

```bash
# Rebuild and push new image
docker build -t $INGESTION_REPO:latest -f services/ingestion/dockerfile .
docker push $INGESTION_REPO:latest

# Force new deployment
aws ecs update-service \
  --cluster regengine-prod \
  --service ingestion \
  --force-new-deployment
```

### 9.2 Scale Services

```bash
# Scale up
aws ecs update-service \
  --cluster regengine-prod \
  --service ingestion \
  --desired-count 5

# Or update terraform.tfvars and reapply
```

### 9.3 View Logs

```bash
# Get log stream
aws logs tail /ecs/regengine-prod/ingestion --follow
```

## Cost Optimization

### Estimated Monthly Costs (Minimal Production Setup)

| Resource | Configuration | Monthly Cost |
|----------|---------------|--------------|
| ECS Fargate | 5 tasks @ 0.5 vCPU, 1GB RAM | ~$90 |
| ALB | 1 ALB + data transfer | ~$25 |
| NAT Gateway | 3 NAT Gateways | ~$100 |
| MSK | 3 kafka.m5.large brokers | ~$450 |
| Neo4j EC2 | 1 t3.medium instance | ~$30 |
| S3 | 100GB storage + requests | ~$5 |
| Data Transfer | Typical usage | ~$50 |
| **Total** | | **~$750/month** |

### Cost Reduction Strategies

1. **Use fewer NAT Gateways** (1 instead of 3): Save ~$65/month
2. **Use smaller Kafka instances** (kafka.t3.small): Save ~$300/month
3. **Use Neo4j Aura Serverless**: Variable cost based on usage
4. **Enable S3 Intelligent Tiering**: Save 20-30% on storage
5. **Use Fargate Spot** (for non-critical workloads): Save 50-70% on compute

## Troubleshooting

### Issue: ECS tasks fail to start

**Check:**
1. ECR image exists: `aws ecr list-images --repository-name regengine/prod/ingestion`
2. IAM task role has permissions
3. Secrets are accessible
4. View task logs: `aws logs tail /ecs/regengine-prod/ingestion`

### Issue: Cannot connect to Neo4j

**Check:**
1. Security group allows traffic from ECS tasks
2. Neo4j password is correct in Secrets Manager
3. Neo4j instance is running

### Issue: High latency

**Check:**
1. Enable Container Insights metrics
2. Scale ECS services up
3. Review ALB metrics
4. Check Kafka consumer lag

## Security Checklist

- [x] All secrets in Secrets Manager
- [x] S3 buckets encrypted at rest
- [x] VPC with private subnets
- [ ] ACM certificate for HTTPS
- [ ] WAF rules on ALB
- [ ] VPC Flow Logs enabled
- [ ] CloudTrail audit logging
- [ ] IAM roles with least privilege
- [ ] Security group rules minimized
- [ ] Enable GuardDuty
- [ ] Regular security scans of ECR images

## Next Steps

1. **Complete remaining Terraform modules** (IAM, ECS, ALB, MSK, Neo4j)
2. **Set up CI/CD pipeline** (GitHub Actions, AWS CodePipeline)
3. **Configure custom domain** with Route53 and ACM
4. **Enable monitoring and alerting** (CloudWatch, PagerDuty)
5. **Implement auto-scaling** based on metrics
6. **Set up disaster recovery** (cross-region replication)
7. **Load demo dataset** (see `demo/` directory)

## Support

For issues or questions:
- Review logs in CloudWatch
- Check Terraform state: `terraform show`
- Consult AWS documentation
- File issues in GitHub repository
