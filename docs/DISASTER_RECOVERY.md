# Disaster Recovery and Business Continuity Plan

**Version:** 1.0
**Last Updated:** 2026-01-03
**Owner:** Engineering Team
**Review Frequency:** Quarterly

---

## 1. Executive Summary

This document defines procedures to recover RegEngine services in the event of system failures, data loss, or catastrophic incidents. The plan ensures business continuity and regulatory compliance.

### Recovery Objectives

| Metric | Target | Maximum |
|--------|--------|---------|
| **RTO** (Recovery Time) | 4 hours | 8 hours |
| **RPO** (Data Loss) | 15 minutes | 1 hour |

---

## 2. Critical Systems Classification

### Tier 1 - Critical (RTO: 1 hour)

| System | Impact if Down |
|--------|----------------|
| PostgreSQL (Admin DB) | No authentication, no tenant management |
| Neo4j (Knowledge Graph) | No queries, no compliance checks |
| API Gateway | Complete service outage |

### Tier 2 - Important (RTO: 4 hours)

| System | Impact if Down |
|--------|----------------|
| Kafka/Redpanda | Processing stops, but data queued |
| NLP Service | Ingestion pipeline pauses |
| Redis | Rate limiting disabled |

### Tier 3 - Standard (RTO: 24 hours)

| System | Impact if Down |
|--------|----------------|
| S3/MinIO (raw docs) | New ingestion blocked |
| Monitoring (Grafana) | Reduced visibility |

---

## 3. Backup Procedures

### 3.1 PostgreSQL

```bash
# Automated daily backup (via cron or ECS scheduled task)
pg_dump -h $DB_HOST -U regengine regengine_admin | \
  gzip | \
  aws s3 cp - s3://regengine-backups/postgres/$(date +%Y-%m-%d).sql.gz
```

| Schedule | Retention | Location |
|----------|-----------|----------|
| Hourly | 24 hours | S3 same-region |
| Daily | 30 days | S3 cross-region |
| Weekly | 1 year | S3 Glacier |

### 3.2 Neo4j

```bash
# Neo4j backup
neo4j-admin database dump neo4j --to-path=/backups/
aws s3 sync /backups/ s3://regengine-backups/neo4j/
```

| Schedule | Retention | Location |
|----------|-----------|----------|
| Daily | 14 days | S3 same-region |
| Weekly | 90 days | S3 cross-region |

### 3.3 Kafka Topics

| Topic | Retention | Backup Strategy |
|-------|-----------|-----------------|
| ingest.normalized | 7 days | Topic mirroring to DR cluster |
| graph.update | 7 days | Topic mirroring |
| nlp.needs_review | 30 days | Topic mirroring |
| graph.audit | 90 days | S3 archival via Kafka Connect |

### 3.4 S3 Documents

| Bucket | Versioning | Cross-Region Replication |
|--------|------------|--------------------------|
| reg-engine-raw-data | Enabled | Yes (us-west-2) |
| reg-engine-processed-data | Enabled | Yes (us-west-2) |

---

## 4. Disaster Scenarios

### Scenario 1: Single Service Failure

**Trigger:** Container crash, OOM, deadlock

**Detection:** ECS health check fails, Prometheus alerts

**Response:**
1. ECS auto-restarts container (automatic)
2. If persistent: inspect logs (`aws logs tail /ecs/regengine-prod/{service}`)
3. Rollback to previous task definition if needed
4. RTO: < 5 minutes (automatic)

### Scenario 2: Database Corruption

**Trigger:** Disk failure, software bug, human error

**Response:**
1. Stop affected services to prevent further damage
2. Assess scope of corruption
3. Execute point-in-time recovery:

```bash
# PostgreSQL PITR
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier regengine-prod \
  --target-db-instance-identifier regengine-prod-recovery \
  --restore-time 2026-01-03T20:00:00Z
```

4. Validate data integrity
5. Switch applications to recovered instance
6. RTO: 2-4 hours

### Scenario 3: Region Outage

**Trigger:** AWS region failure, natural disaster

**Response:**
1. Activate cross-region DNS failover (Route 53)
2. Promote read replicas in DR region
3. Update Kafka consumers to DR cluster
4. Verify S3 replication complete
5. RTO: 4-8 hours

```bash
# DNS failover
aws route53 change-resource-record-sets \
  --hosted-zone-id $ZONE_ID \
  --change-batch file://failover-to-dr.json
```

### Scenario 4: Ransomware/Cyber Attack

**Trigger:** Security breach, encryption attack

**Response:**
1. **Isolate:** Disable public access immediately
2. **Assess:** Determine scope of compromise
3. **Preserve:** Snapshot all systems for forensics
4. **Recover:** Restore from air-gapped backups
5. **Notify:** Contact legal, customers, regulators as required
6. RTO: 8-24 hours

```bash
# Immediate isolation
aws ec2 modify-instance-attribute --instance-id $ID \
  --no-source-dest-check
aws ec2 revoke-security-group-ingress --group-id $SG \
  --protocol all --cidr 0.0.0.0/0
```

---

## 5. Recovery Procedures

### 5.1 Full System Recovery Runbook

```
Step 1: Infrastructure
├── Verify DR region VPC
├── Launch RDS from backup
├── Restore Neo4j from S3 backup
└── Start Kafka cluster

Step 2: Data Validation
├── Run PostgreSQL integrity checks
├── Run Neo4j consistency check
└── Verify S3 document counts

Step 3: Services
├── Deploy Admin API
├── Deploy Ingestion (with Kafka paused)
├── Deploy Graph Service
├── Deploy Compliance/Opportunity APIs
└── Resume Kafka consumers

Step 4: Verification
├── Health check all endpoints
├── Run smoke tests
├── Verify audit logging
└── Test one ingestion flow

Step 5: Cutover
├── Update DNS
├── Notify stakeholders
└── Monitor error rates
```

### 5.2 Service-Specific Recovery

| Service | Recovery Command | Validation |
|---------|------------------|------------|
| Admin API | `kubectl rollout restart deployment/admin-api` | `curl /health` |
| Ingestion | `kubectl rollout restart deployment/ingestion` | Ingest test URL |
| NLP | Check Kafka consumer lag | Process backlog |
| Graph | `cypher-shell -d neo4j "RETURN 1"` | Query provision |

---

## 6. Communication Plan

### Escalation Matrix

| Severity | Notify | Response Time |
|----------|--------|---------------|
| SEV1 (Complete outage) | Exec team, On-call, All hands | 15 min |
| SEV2 (Degraded service) | Engineering lead, On-call | 1 hour |
| SEV3 (Single component) | On-call engineer | 4 hours |

### Stakeholder Notification Templates

**Customer Notification (Outage):**
```
Subject: RegEngine Service Disruption

We are currently experiencing a service disruption affecting [COMPONENT].
Impact: [DESCRIPTION]
Started: [TIME]
Expected Resolution: [ETA]

Updates will be provided every [30 minutes].
```

**Internal Notification:**
```
@channel INCIDENT: [SEVERITY] - [DESCRIPTION]
Incident Commander: [NAME]
Status Page: [URL]
War Room: [LINK]
```

---

## 7. Testing Schedule

| Test Type | Frequency | Last Tested | Next Test |
|-----------|-----------|-------------|-----------|
| Backup Restoration | Monthly | - | TBD |
| Failover Drill | Quarterly | - | TBD |
| Full DR Exercise | Annually | - | TBD |
| Tabletop Exercise | Semi-annually | - | TBD |

---

## 8. Manual Workarounds

If RegEngine is unavailable for extended periods:

### Compliance Checks
- Export checklists to spreadsheet (pre-generated)
- Manual review against regulatory text

### Document Ingestion
- Queue URLs in shared document
- Process when service restored

### Audit Trail
- Manual logging in incident log
- Reconcile with system logs after recovery

---

## 9. Post-Incident Review

After every SEV1/SEV2 incident:

1. **Blameless Post-Mortem** within 72 hours
2. **Root Cause Analysis** documented
3. **Action Items** with owners and deadlines
4. **Runbook Updates** if gaps identified
5. **DR Plan Review** if assumptions invalidated
