# RegEngine Production Deployment Guide

This guide covers the complete production deployment process for RegEngine, including prerequisites, configuration, deployment steps, and operational procedures.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [Infrastructure Setup](#infrastructure-setup)
- [Application Deployment](#application-deployment)
- [Verification & Health Checks](#verification--health-checks)
- [Monitoring & Observability](#monitoring--observability)
- [Rollback Procedures](#rollback-procedures)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

RegEngine is a microservices-based regulatory intelligence platform consisting of:

### Core Services
- **Gateway (Nginx)**: TLS termination, request routing, rate limiting
- **Admin API**: Tenant management, API key provisioning, system configuration
- **Ingestion Service**: Multi-state regulatory document scraping and normalization
- **NLP Service**: Entity extraction, compliance analysis using LLMs
- **Graph Service**: Knowledge graph construction and querying (Neo4j)
- **Opportunity API**: Business opportunity detection and scoring
- **Compliance API**: Regulatory compliance checking and recommendations
- **Scheduler**: Automated scraping orchestration

### Infrastructure Components
- **Kafka (MSK)**: Event streaming between services
- **Redis**: Rate limiting and caching
- **PostgreSQL (RDS)**: Admin and application database
- **Neo4j**: Graph database for regulatory relationships
- **S3**: Raw and processed document storage
- **CloudWatch**: Logging and monitoring

---

## Prerequisites

### Required Tools
- Docker 24.0+ and Docker Compose 2.20+
- Terraform 1.5+
- AWS CLI v2 configured with appropriate credentials
- Python 3.11+ (for verification scripts)
- Git

### Required Access
- AWS account with administrative access (for initial setup)
- GitHub Container Registry (GHCR) access for pulling images
- Domain name with DNS management access
- TLS/SSL certificates for your domain

### Resource Requirements
Minimum production environment:
- **Compute**: 15 vCPUs, 32GB RAM (distributed across services)
- **Storage**: 500GB for databases, 1TB for S3 document storage
- **Network**: 100Mbps sustained bandwidth

---

## Environment Configuration

### 1. Create Production Environment File

Create `.env.production` at the repository root:

```bash
# Environment
REGENGINE_ENV=production
LOG_LEVEL=INFO

# AWS Configuration
AWS_REGION=us-east-1
RAW_DATA_BUCKET=regengine-raw-data-prod
PROCESSED_DATA_BUCKET=regengine-processed-data-prod
AWS_ACCESS_KEY_ID=<your-access-key>
AWS_SECRET_ACCESS_KEY=<your-secret-key>

# Database (RDS)
DATABASE_URL=postgresql://regengine:PASSWORD@regengine-db.us-east-1.rds.amazonaws.com:5432/regengine_prod
ADMIN_DATABASE_URL=postgresql://regengine:PASSWORD@regengine-db.us-east-1.rds.amazonaws.com:5432/regengine_admin_prod

# Redis (ElastiCache)
REDIS_URL=redis://:PASSWORD@regengine-cache.xxxxx.0001.use1.cache.amazonaws.com:6379/0
REDIS_PASSWORD=<strong-redis-password>

# Kafka (MSK)
KAFKA_BOOTSTRAP_SERVERS=b-1.regengine-msk.xxxxx.kafka.us-east-1.amazonaws.com:9092,b-2.regengine-msk.xxxxx.kafka.us-east-1.amazonaws.com:9092
KAFKA_TOPIC_NORMALIZED=ingest.normalized
KAFKA_TOPIC_NLP=nlp.extracted

# Neo4j
NEO4J_URI=bolt://regengine-neo4j.us-east-1.amazonaws.com:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<strong-neo4j-password>

# LLM Configuration
OLLAMA_HOST=http://ollama:11434
OPENAI_API_KEY=<your-openai-key>  # Optional, for advanced NLP

# Security
ADMIN_MASTER_KEY=<generate-strong-key-256-bit>

# Rate Limiting (CRITICAL - Required in Production)
RATE_LIMIT_BACKEND=redis
```

### 2. Generate Secrets

Use strong, random secrets for all credentials:

```bash
# Generate master admin key (256-bit)
openssl rand -hex 32

# Generate database passwords
openssl rand -base64 32

# Generate Redis password
openssl rand -base64 24
```

### 3. Validate Environment File

Run the verification script to ensure all required variables are set:

```bash
python scripts/verify_production_readiness.py
```

---

## Infrastructure Setup

### 1. Initialize Terraform

```bash
cd infra

# Initialize with remote state backend
terraform init

# Select or create production workspace
terraform workspace new production
terraform workspace select production
```

### 2. Review Infrastructure Plan

```bash
# Create infrastructure plan
terraform plan -var-file=environments/production.tfvars -out=prod.tfplan

# Review the plan carefully
less prod.tfplan
```

### 3. Apply Infrastructure

```bash
# Apply the infrastructure changes
terraform apply prod.tfplan

# Save outputs for application configuration
terraform output -json > ../config/terraform-outputs.json
```

**Expected Resources Created:**
- VPC with public/private subnets across 3 AZs
- Application Load Balancer with TLS
- RDS PostgreSQL Multi-AZ instance
- ElastiCache Redis cluster
- MSK (Managed Kafka) cluster
- EC2 instance for Neo4j (or managed solution)
- S3 buckets with versioning and encryption
- IAM roles and policies
- Security groups and NACLs
- CloudWatch log groups

### 4. Initialize Databases

```bash
# Connect to RDS and create databases
psql $DATABASE_URL -c "CREATE DATABASE regengine_prod;"
psql $ADMIN_DATABASE_URL -c "CREATE DATABASE regengine_admin_prod;"

# Run migrations (from admin service)
docker run --rm \
  -e DATABASE_URL=$ADMIN_DATABASE_URL \
  ghcr.io/regengine/admin-api:latest \
  python -m alembic upgrade head
```

---

## Application Deployment

### 1. Pull Latest Images

```bash
# Authenticate to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull all service images
docker-compose -f docker-compose.prod.yml pull
```

### 2. Pre-Deployment Checklist

- [ ] All environment variables set in `.env.production`
- [ ] Database migrations completed
- [ ] S3 buckets created and accessible
- [ ] Kafka topics created
- [ ] Redis accessible
- [ ] Neo4j initialized
- [ ] SSL certificates in `gateway/ssl/`
- [ ] DNS records pointing to ALB

### 3. Deploy Services

```bash
# Load production environment
set -a
source .env.production
set +a

# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Monitor startup logs
docker-compose -f docker-compose.prod.yml logs -f
```

### 4. Verify Service Startup

```bash
# Check all containers are running
docker-compose -f docker-compose.prod.yml ps

# Expected output: All services in "Up" state with health checks passing
```

---

## Verification & Health Checks

### 1. Service Health Endpoints

Check each service is responding:

```bash
# Gateway
curl -k https://your-domain.com/health

# Admin API
curl http://localhost:8400/health

# Ingestion Service
curl http://localhost:8000/health

# NLP Service
curl http://localhost:8100/health

# Graph Service
curl http://localhost:8200/health

# Opportunity API
curl http://localhost:8300/health

# Compliance API
curl http://localhost:8500/health
```

Expected response from each:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### 2. Integration Tests

Test critical workflows:

```bash
# Create a test API key
curl -X POST https://your-domain.com/admin/v1/api-keys \
  -H "X-Admin-Key: $ADMIN_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-tenant",
    "name": "production-test-key",
    "rate_limit_per_minute": 60
  }'

# Test ingestion trigger
curl -X POST https://your-domain.com/api/v1/ingestion/trigger \
  -H "X-RegEngine-API-Key: $TEST_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jurisdiction": "US-TX"}'

# Verify document processing
# (Check Kafka topics, S3 buckets, and graph database)
```

### 3. Monitoring Checks

```bash
# Check Redis connectivity
redis-cli -u $REDIS_URL ping
# Expected: PONG

# Check Kafka connectivity
kafka-topics.sh --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS --list

# Check Neo4j connectivity
cypher-shell -u $NEO4J_USER -p $NEO4J_PASSWORD -a $NEO4J_URI "RETURN 1"
```

### 4. Rate Limiting Verification

```bash
# Verify Redis-based rate limiting is active
docker-compose -f docker-compose.prod.yml logs admin-api | grep "rate_limit_backend"
# Expected: backend=redis

# Test rate limit enforcement
for i in {1..100}; do
  curl -X GET https://your-domain.com/api/v1/opportunities \
    -H "X-RegEngine-API-Key: $TEST_API_KEY"
done
# Should see 429 responses after hitting limit
```

---

## Monitoring & Observability

### CloudWatch Dashboards

Key metrics to monitor:

1. **Service Health**
   - Container CPU/Memory utilization
   - Request rates and latencies (p50, p95, p99)
   - Error rates (4xx, 5xx)
   - Health check failures

2. **Infrastructure**
   - RDS connections, IOPS, storage
   - ElastiCache hit rate, evictions
   - MSK broker CPU, network throughput
   - ALB target health, request count

3. **Application Metrics**
   - Ingestion: Documents scraped/hour per jurisdiction
   - NLP: Entities extracted, processing time
   - Graph: Query latency, node/edge counts
   - Rate limiting: Rejected requests, top consumers

### Log Aggregation

All services use structured logging with correlation IDs:

```bash
# Follow logs across all services
docker-compose -f docker-compose.prod.yml logs -f

# Filter by correlation ID
docker-compose -f docker-compose.prod.yml logs | grep "correlation_id=abc-123"

# Search for errors
docker-compose -f docker-compose.prod.yml logs | grep "level=error"
```

### Alerting Rules

Configure CloudWatch alarms for:

- Container restarts > 3 in 10 minutes
- Error rate > 5% for 5 minutes
- p95 latency > 2 seconds for 10 minutes
- Database connections > 80% for 5 minutes
- Disk usage > 85%
- Failed health checks > 2 consecutive

---

## Rollback Procedures

### Quick Rollback (Service-Level)

If a new deployment causes issues:

```bash
# Rollback to previous image version
docker-compose -f docker-compose.prod.yml down

# Update image tags in docker-compose.prod.yml to previous version
# Or set environment variable: export IMAGE_TAG=v1.2.3

docker-compose -f docker-compose.prod.yml up -d
```

### Database Rollback

```bash
# Rollback migrations (use with caution)
docker run --rm \
  -e DATABASE_URL=$ADMIN_DATABASE_URL \
  ghcr.io/regengine/admin-api:v1.2.3 \
  python -m alembic downgrade -1

# Restore from snapshot (if needed)
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier regengine-db-restored \
  --db-snapshot-identifier regengine-db-snapshot-2025-01-15
```

### Infrastructure Rollback

```bash
cd infra

# Revert to previous Terraform state
terraform workspace select production
git checkout <previous-commit>
terraform plan -var-file=environments/production.tfvars
terraform apply
```

---

## Troubleshooting

### Service Won't Start

**Symptom:** Container exits immediately after starting

**Diagnosis:**
```bash
# Check container logs
docker-compose -f docker-compose.prod.yml logs <service-name>

# Check environment variables
docker-compose -f docker-compose.prod.yml config

# Verify dependencies are accessible
docker-compose -f docker-compose.prod.yml exec <service> ping redis
```

**Common Causes:**
- Missing required environment variables
- Database connection refused (check security groups)
- Redis connection timeout (check REDIS_URL)
- Port conflicts

### Rate Limiting Issues

**Symptom:** "CRITICAL SECURITY: REDIS_URL is required" error

**Fix:**
```bash
# Ensure REDIS_URL is set in environment
echo $REDIS_URL

# Verify Redis is accessible
redis-cli -u $REDIS_URL ping

# Check REGENGINE_ENV is set to "production"
echo $REGENGINE_ENV
```

### High Memory Usage

**Symptom:** OOM kills, container restarts

**Diagnosis:**
```bash
# Check current memory usage
docker stats

# Check resource limits
docker-compose -f docker-compose.prod.yml config | grep -A 5 "resources"
```

**Fix:**
- Adjust memory limits in docker-compose.prod.yml
- Increase instance size in infrastructure
- Enable memory swap if appropriate

### Kafka Connection Issues

**Symptom:** Services can't connect to Kafka

**Diagnosis:**
```bash
# Test Kafka connectivity
docker run --rm -it confluentinc/cp-kafka:latest \
  kafka-broker-api-versions --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS

# Check security groups allow port 9092
# Check MSK cluster status in AWS console
```

### Neo4j Query Timeouts

**Symptom:** Graph queries taking >30 seconds

**Fix:**
```bash
# Add indexes to frequently queried properties
cypher-shell -u $NEO4J_USER -p $NEO4J_PASSWORD -a $NEO4J_URI \
  "CREATE INDEX FOR (n:Regulation) ON (n.jurisdiction)"

# Review and optimize queries
# Consider increasing Neo4j instance size
```

---

## Disaster Recovery

### Backup Strategy

**Automated Backups:**
- RDS: Daily snapshots, 30-day retention
- S3: Versioning enabled, lifecycle policies
- Neo4j: Daily exports to S3

**Manual Backup:**
```bash
# Backup Neo4j
docker-compose -f docker-compose.prod.yml exec graph-service \
  neo4j-admin dump --to=/backups/neo4j-$(date +%Y%m%d).dump

# Backup PostgreSQL
pg_dump $DATABASE_URL | gzip > backup-$(date +%Y%m%d).sql.gz
```

### Recovery Procedures

**RDS Recovery:**
```bash
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier regengine-db-restored \
  --db-snapshot-identifier <snapshot-id>
```

**S3 Recovery:**
```bash
# Restore previous version
aws s3api get-object \
  --bucket $RAW_DATA_BUCKET \
  --key <object-key> \
  --version-id <version-id> \
  <output-file>
```

---

## Security Hardening

### Post-Deployment Security

1. **Rotate Initial Credentials**
   ```bash
   # Rotate admin master key after initial setup
   # Update in AWS Secrets Manager and restart services
   ```

2. **Enable WAF**
   ```bash
   # Attach WAF to ALB for DDoS protection
   aws wafv2 associate-web-acl \
     --web-acl-arn <waf-acl-arn> \
     --resource-arn <alb-arn>
   ```

3. **Configure VPC Flow Logs**
   ```bash
   aws ec2 create-flow-logs \
     --resource-type VPC \
     --resource-ids <vpc-id> \
     --traffic-type ALL \
     --log-destination-type cloud-watch-logs
   ```

4. **Enable GuardDuty**
   ```bash
   aws guardduty create-detector --enable
   ```

---

## Performance Tuning

### Database Optimization

```sql
-- Add indexes for common queries
CREATE INDEX idx_documents_jurisdiction ON documents(jurisdiction_code);
CREATE INDEX idx_api_keys_tenant ON api_keys(tenant_id) WHERE deleted_at IS NULL;

-- Analyze query performance
EXPLAIN ANALYZE SELECT * FROM documents WHERE jurisdiction_code = 'US-TX';
```

### Redis Tuning

```bash
# Increase max memory (via ElastiCache console)
# Set eviction policy to allkeys-lru
# Enable persistence (RDB + AOF)
```

### Service Scaling

```yaml
# Update docker-compose.prod.yml for horizontal scaling
services:
  ingestion-service:
    deploy:
      replicas: 3  # Scale to 3 instances
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
```

---

## Maintenance Windows

### Planned Maintenance

1. **Schedule downtime** (recommended: Sunday 2-4 AM UTC)
2. **Notify users** 48 hours in advance
3. **Create backups** before maintenance
4. **Execute updates** with monitoring
5. **Verify functionality** post-update
6. **Document changes** in changelog

### Zero-Downtime Deployment

For critical services:

```bash
# Use rolling updates
docker-compose -f docker-compose.prod.yml up -d --no-deps --scale ingestion-service=6 ingestion-service
# Wait for new instances to be healthy
docker-compose -f docker-compose.prod.yml up -d --no-deps --scale ingestion-service=3 ingestion-service
```

---

## Support & Escalation

### On-Call Runbook

**P1 - Critical (Service Down):**
1. Check CloudWatch alarms
2. Review service logs
3. Attempt automatic restart
4. Escalate to engineering lead if unresolved in 15 minutes

**P2 - High (Degraded Performance):**
1. Identify bottleneck using metrics
2. Scale affected service if resource-constrained
3. Create incident ticket
4. Escalate if degradation persists >1 hour

**P3 - Medium (Non-Critical Issues):**
1. Create ticket with logs and reproduction steps
2. Schedule fix for next deployment window

### Contact Information

- **Engineering Lead:** [email/slack]
- **DevOps:** [email/slack]
- **AWS Support:** [account number]
- **On-Call Rotation:** [PagerDuty/OpsGenie]

---

## Compliance & Audit

### Audit Logging

All administrative actions are logged:

```bash
# View admin API audit logs
docker-compose -f docker-compose.prod.yml logs admin-api | grep "audit_event"
```

### Compliance Requirements

- **Data Encryption:** At rest (S3, RDS) and in transit (TLS)
- **Access Control:** IAM roles, API key authentication
- **Audit Trail:** All API calls logged with correlation IDs
- **Data Retention:** 90 days for logs, 7 years for documents
- **Backup:** Daily automated backups with 30-day retention

---

## Changelog & Versioning

Document all production deployments:

```markdown
## [1.0.0] - 2025-01-15
### Added
- Initial production deployment
- All core services deployed
- Monitoring and alerting configured

### Changed
- N/A

### Fixed
- N/A
```

---

## Additional Resources

- [Architecture Diagrams](./architecture/)
- [API Documentation](./api/)
- [Runbooks](./runbooks/)
- [Incident Response](./incident-response.md)
- [Terraform Modules](../infra/modules/)

---

**Last Updated:** 2025-01-15
**Document Version:** 1.0
**Maintained By:** DevOps Team
