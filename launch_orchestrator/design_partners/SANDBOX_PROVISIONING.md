# RegEngine Sandbox Provisioning Guide

This document describes how to provision and configure sandbox environments for design partners.

---

## Overview

Each design partner receives a dedicated sandbox environment with:
- Unique API key with scoped permissions
- Rate limiting (60 RPM default, adjustable)
- Document quota (1,000 docs, adjustable)
- Pre-loaded sample data (US, UK, EU regulations)
- Isolated data storage (no cross-contamination between partners)

---

## Provisioning Process

### 1. Prerequisites

**Before provisioning**, ensure you have:

- [ ] Design partner agreement signed
- [ ] Primary contact information (name, email, company)
- [ ] Slack channel invite sent (#regengine-design-partners)
- [ ] Use case identified (from sales handoff)
- [ ] Special requirements noted (higher rate limits, additional jurisdictions, etc.)

### 2. Automated Provisioning

**Using the Launch Orchestrator**:

```bash
# From launch_orchestrator directory
python orchestrator.py --mode provision_sandbox --partner-id "acme-corp"
```

This will:
1. Create dedicated sandbox namespace: `dp-sandbox-{partner-id}`
2. Generate API key: `dp_sandbox_{random_32_chars}`
3. Set rate limits: 60 RPM (configurable)
4. Set document quota: 1,000 docs (configurable)
5. Load sample data: US SEC, EU MiFID, UK FCA
6. Create monitoring dashboard
7. Send welcome email with credentials

**Expected output**:
```
✓ Sandbox provisioned: dp-sandbox-acme-corp
✓ API Key generated: dp_sandbox_a1b2c3... (sent via 1Password)
✓ Rate limit set: 60 RPM
✓ Document quota: 1000
✓ Sample data loaded: 45 documents, 327 obligations
✓ Dashboard created: https://sandbox.regengine.ai/dashboard/acme-corp
```

### 3. Manual Provisioning (if automated fails)

**Step 3.1: Generate API Key**

```bash
# Using the Admin API
curl -X POST "http://localhost:8400/admin/keys" \
  -H "X-Admin-Master-Key: ${ADMIN_MASTER_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "key_id": "acme-corp-sandbox",
    "scopes": ["read", "write", "ingest"],
    "rate_limit_per_minute": 60,
    "expires_at": "2025-03-31T23:59:59Z",
    "metadata": {
      "partner_name": "Acme Corp",
      "program": "design_partner",
      "contact": "john@acme.com"
    }
  }'
```

**Step 3.2: Create Database Namespace**

```bash
# Neo4j: Create constraint for partner isolation
docker exec -it regengine-neo4j cypher-shell -u neo4j -p ${NEO4J_PASSWORD} \
  "CREATE CONSTRAINT partner_namespace IF NOT EXISTS FOR (n:Document) REQUIRE n.namespace IS NOT NULL;"

# Tag sample data with namespace
docker exec -it regengine-neo4j cypher-shell -u neo4j -p ${NEO4J_PASSWORD} \
  "MATCH (n) WHERE n.namespace IS NULL SET n.namespace = 'dp-sandbox-acme-corp';"
```

**Step 3.3: Configure Rate Limiting**

```bash
# Redis: Set rate limit key
redis-cli SET "ratelimit:acme-corp-sandbox" 60 EX 3600
```

**Step 3.4: Load Sample Data**

```bash
# Ingest pre-configured sample documents
cd /path/to/demo/documents
for file in us-sec-*.json eu-mifid-*.json uk-fca-*.json; do
  curl -X POST "http://localhost:8100/ingest/url" \
    -H "X-RegEngine-API-Key: ${API_KEY}" \
    -H "Content-Type: application/json" \
    -d @"$file"
done
```

---

## Configuration Options

### Rate Limits

| Tier | RPM | Use Case |
|------|-----|----------|
| Standard | 60 | Most design partners |
| High-Volume | 300 | Partners testing bulk ingestion |
| Unlimited | 999999 | Partners load-testing for production |

**To adjust**:
```bash
curl -X PATCH "http://localhost:8400/admin/keys/acme-corp-sandbox" \
  -H "X-Admin-Master-Key: ${ADMIN_MASTER_KEY}" \
  -d '{"rate_limit_per_minute": 300}'
```

### Document Quotas

| Tier | Max Docs | Use Case |
|------|----------|----------|
| Standard | 1,000 | Typical evaluation |
| Extended | 5,000 | Partners ingesting full regulatory corpus |
| Unlimited | 999999 | Production-scale testing |

**To adjust**:
```bash
curl -X PATCH "http://localhost:8400/admin/keys/acme-corp-sandbox" \
  -H "X-Admin-Master-Key: ${ADMIN_MASTER_KEY}" \
  -d '{"metadata": {"max_documents": 5000}}'
```

### Jurisdiction Coverage

**Default**: US, UK, EU

**To add additional jurisdictions** (e.g., Singapore, Canada):

1. Load regulatory documents for that jurisdiction
2. Update API key metadata:
```bash
curl -X PATCH "http://localhost:8400/admin/keys/acme-corp-sandbox" \
  -H "X-Admin-Master-Key: ${ADMIN_MASTER_KEY}" \
  -d '{"metadata": {"jurisdictions": ["United States", "United Kingdom", "European Union", "Singapore"]}}'
```

---

## Monitoring & Usage Tracking

### Metrics Dashboard

Each sandbox has a dedicated dashboard:
- **URL**: `https://sandbox.regengine.ai/dashboard/{partner-id}`
- **Metrics**:
  - API calls (by endpoint, by day)
  - Documents ingested
  - Obligations extracted
  - Error rate
  - Response time (p50, p95, p99)

### Prometheus Queries

**API call volume**:
```promql
rate(regengine_api_requests_total{api_key="acme-corp-sandbox"}[5m])
```

**Document ingestion count**:
```promql
regengine_documents_ingested_total{namespace="dp-sandbox-acme-corp"}
```

**Error rate**:
```promql
rate(regengine_api_errors_total{api_key="acme-corp-sandbox"}[5m])
```

### Logs

**View partner-specific logs**:
```bash
docker logs regengine-ingestion | grep "api_key=acme-corp-sandbox"
```

**Structured log query** (if using DataDog/Splunk):
```
service:regengine api_key:acme-corp-sandbox status:error
```

---

## Data Management

### Sandbox Reset

To reset a partner's sandbox (delete all their data, keep API key):

```bash
# Delete all nodes/relationships for this namespace
docker exec -it regengine-neo4j cypher-shell -u neo4j -p ${NEO4J_PASSWORD} \
  "MATCH (n {namespace: 'dp-sandbox-acme-corp'}) DETACH DELETE n;"

# Reload sample data
cd /path/to/demo/documents
./load_demo_data.sh "acme-corp-sandbox"
```

### Sandbox Deletion

To permanently delete a partner's sandbox (end of program):

```bash
# 1. Revoke API key
curl -X DELETE "http://localhost:8400/admin/keys/acme-corp-sandbox" \
  -H "X-Admin-Master-Key: ${ADMIN_MASTER_KEY}"

# 2. Delete all data
docker exec -it regengine-neo4j cypher-shell -u neo4j -p ${NEO4J_PASSWORD} \
  "MATCH (n {namespace: 'dp-sandbox-acme-corp'}) DETACH DELETE n;"

# 3. Remove S3 artifacts (if any)
aws s3 rm s3://reg-engine-raw-data-dev/dp-sandbox-acme-corp/ --recursive

# 4. Archive logs
# (Retain for 90 days per data retention policy)
```

---

## Migration to Production

When a design partner transitions to paid customer:

### 1. Export Sandbox Data (if requested)

```bash
# Export obligations to JSON
docker exec -it regengine-neo4j cypher-shell -u neo4j -p ${NEO4J_PASSWORD} \
  "MATCH (o:Obligation {namespace: 'dp-sandbox-acme-corp'}) RETURN o" \
  > acme-corp-sandbox-export.json
```

### 2. Provision Production Environment

```bash
# Create production API key (no rate limits, no expiration)
curl -X POST "http://localhost:8400/admin/keys" \
  -H "X-Admin-Master-Key: ${ADMIN_MASTER_KEY}" \
  -d '{
    "key_id": "acme-corp-production",
    "scopes": ["read", "write", "ingest", "admin"],
    "rate_limit_per_minute": 999999,
    "expires_at": null,
    "metadata": {
      "partner_name": "Acme Corp",
      "tier": "enterprise",
      "contract_start": "2025-02-01"
    }
  }'
```

### 3. Update DNS/URLs

- Sandbox: `sandbox.regengine.ai` → Production: `api.regengine.ai`
- Provide new API key via secure channel
- Update documentation links

### 4. SLA Commitment

Production environments include:
- **Uptime SLA**: 99.9% (8.76 hours downtime/year max)
- **Support SLA**: < 1 hour response for P1 issues
- **Data retention**: 7 years (regulatory compliance)
- **Backup**: Daily snapshots, 30-day retention

---

## Troubleshooting

### Issue: Partner can't connect to sandbox

**Check**:
1. API key valid: `curl http://localhost:8400/admin/keys/acme-corp-sandbox -H "X-Admin-Master-Key: ${ADMIN_MASTER_KEY}"`
2. Sandbox URL resolving: `dig sandbox.regengine.ai`
3. Firewall rules allowing access
4. API key not expired

### Issue: Sample data not appearing

**Check**:
1. Namespace filter: `MATCH (n {namespace: 'dp-sandbox-acme-corp'}) RETURN count(n)`
2. Ingestion logs: `docker logs regengine-ingestion | tail -100`
3. Re-run sample data load script

### Issue: Rate limiting not working

**Check**:
1. Redis connectivity: `redis-cli PING`
2. API key rate limit config: `curl http://localhost:8400/admin/keys/acme-corp-sandbox`
3. Middleware configuration in ingestion service

---

## Security Considerations

### API Key Security

- **Generation**: Use cryptographically secure random (32 bytes)
- **Storage**: Hash API keys (SHA-256) before storing
- **Transmission**: Only send via 1Password shared vault or encrypted email
- **Rotation**: Design partner keys expire after 90 days (configurable)

### Data Isolation

- **Namespace enforcement**: All queries must include `WHERE n.namespace = 'dp-sandbox-{id}'`
- **Cross-contamination prevention**: Constraint enforcement at DB level
- **Audit logging**: All API calls logged with api_key and namespace

### Compliance

- **GDPR**: Design partners retain data ownership
- **Data residency**: Sandbox hosted in US-East-1 (configurable)
- **Retention**: Sandbox data deleted 30 days after program end (unless transitioned to production)

---

## Appendix: Provisioning Checklist

Use this checklist for each new design partner:

- [ ] Design partner agreement signed (legal)
- [ ] Partner information collected (sales)
  - [ ] Company name
  - [ ] Primary contact (name, email, role)
  - [ ] Use case summary
  - [ ] Special requirements (rate limits, jurisdictions, etc.)
- [ ] API key generated
- [ ] API key sent via secure channel (1Password)
- [ ] Sandbox namespace created
- [ ] Sample data loaded
- [ ] Rate limits configured
- [ ] Document quota set
- [ ] Monitoring dashboard created
- [ ] Slack invite sent
- [ ] Welcome email sent with ONBOARDING_GUIDE.md
- [ ] Bi-weekly check-ins scheduled
- [ ] Success metrics baseline recorded

---

## Contact

**For provisioning issues**:
- **Email**: devops@regengine.ai
- **Slack**: #regengine-internal-ops

**For partner questions**:
- **Email**: partnerships@regengine.ai
- **Slack**: #regengine-design-partners

---

**Version**: 1.0
**Last Updated**: 2025-11-19
**Owner**: DevOps Team
