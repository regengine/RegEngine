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

> **There is no partner-scoped provisioning command.** The orchestrator has no
> `provision_sandbox` mode and no `--partner-id` flag, and it ignores partner
> identity entirely. To provision a sandbox *for a named partner*, use the
> manual steps in section 3. This section documents only what the orchestrator
> actually does.

**What the orchestrator does**: as one phase of a launch run, it pre-provisions a
fixed pool of generic sandboxes — `dp-sandbox-1` through `dp-sandbox-N`, where N
is `design_partner_program.max_partners` in `launch_orchestrator_spec.yaml`
(default 5). Partner names are never used.

**Prerequisites**: the run aborts environment validation unless these are set —
`OBJECT_STORAGE_ACCESS_KEY_ID`, `OBJECT_STORAGE_SECRET_ACCESS_KEY`,
`OBJECT_STORAGE_REGION`, `CRM_API_TOKEN`, `EMAIL_PROVIDER_API_KEY`,
`LINKEDIN_AUTOMATION_TOKEN`.

**Preview the run** (writes nothing except `orchestration_result.json`):

```bash
# From launch_orchestrator directory
python orchestrator.py --mode dry_run
```

**Execute it** (writes tenant configs and keys to disk):

```bash
# From launch_orchestrator directory
python orchestrator.py --mode full_launch
```

`--mode` accepts exactly `full_launch`, `sales_only`, `infra_only` and `dry_run`;
`dry_run` is the default. The design-partner phase runs only under `full_launch`
and `dry_run`. Run `python orchestrator.py --help` for the authoritative list.

For each of the N sandboxes, a `full_launch` run:

1. Generates a sandbox id of the form `dp-sandbox-N` (sequential, not partner-scoped).
2. Generates an API key: `sk_test_` followed by 32 random alphanumeric characters.
3. Sets the rate limit from `sandbox.rate_limits.rpm_per_api_key` (default 60 RPM).
4. Sets the document quota from `sandbox.max_docs_per_partner` (1,000 in the
   shipped spec; the in-code default when the key is absent is 100).
5. Writes `generated/tenants/dp-sandbox-N.json` and appends the key to
   `generated/sandbox_keys.txt`.

**It does not** create a namespace, load sample data, create a dashboard, or send
a welcome email — those steps are manual (section 3 and the checklist below).
The generated key is only written to those local files; it is not registered with
any running service, so it will not authenticate until an operator creates a real
key via the Admin API in section 3.1.

**Expected output** (`--mode dry_run`, abridged):

```
INFO - === Phase: Design Partner Provisioning ===
INFO - Provisioning sandbox: dp-sandbox-1
INFO - [design_partner_provisioning] provision_sandbox_dp-sandbox-1: success
...
INFO - Provisioning sandbox: dp-sandbox-5
INFO - [design_partner_provisioning] provision_sandbox_dp-sandbox-5: success
INFO - Success: True
INFO - Result written to: orchestration_result.json
```

Exit status is 0 on success and 1 if any phase recorded an error — including the
environment-validation failure above, which is the most common cause of a
non-zero exit on a first run.

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
