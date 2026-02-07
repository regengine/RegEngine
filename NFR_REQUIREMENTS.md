# Non-Functional Requirements (NFRs)

**Version:** 1.0
**Last Updated:** 2026-01-03
**Status:** Active

---

## 1. Availability

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Uptime** | 99.9% | Monthly calculation |
| **Planned Downtime** | < 4 hours/month | Maintenance windows |
| **Unplanned Downtime** | < 43 min/month | Incident tracking |

### SLA Tiers

| Tier | Availability | Downtime/Year |
|------|--------------|---------------|
| Standard | 99.5% | 43.8 hours |
| Professional | 99.9% | 8.7 hours |
| Enterprise | 99.95% | 4.4 hours |

---

## 2. Performance

### Response Time Targets

| Operation | p50 | p95 | p99 |
|-----------|-----|-----|-----|
| API Health Check | < 50ms | < 100ms | < 200ms |
| Checklist Query | < 200ms | < 500ms | < 1s |
| Arbitrage Query | < 500ms | < 2s | < 5s |
| Review Item Fetch | < 100ms | < 300ms | < 500ms |

### Processing Time Targets

| Operation | Target | Max |
|-----------|--------|-----|
| Document Ingestion | < 5s | 30s |
| NLP Extraction | < 30s | 2 min |
| Graph Upsert | < 1s | 5s |
| End-to-End Pipeline | < 2 min | 5 min |

### Throughput

| Metric | Target |
|--------|--------|
| Concurrent Users | 100 |
| API Requests/sec | 500 |
| Documents/hour (ingestion) | 100 |
| Kafka Messages/sec | 1000 |

---

## 3. Recovery Objectives

| Metric | Target | Justification |
|--------|--------|---------------|
| **RTO** (Recovery Time Objective) | 4 hours | Maximum acceptable downtime |
| **RPO** (Recovery Point Objective) | 15 minutes | Kafka retention window |

### Backup Schedule

| Data Store | Frequency | Retention |
|------------|-----------|-----------|
| PostgreSQL | Hourly | 30 days |
| Neo4j | Daily | 14 days |
| S3 (documents) | Versioned | 7 years (regulatory) |
| Kafka | 7 days | Replay capability |

---

## 4. Scalability

### Horizontal Scaling

| Service | Min | Max | Trigger |
|---------|-----|-----|---------|
| Admin API | 1 | 3 | CPU > 70% |
| Ingestion | 2 | 10 | Queue depth > 100 |
| NLP | 2 | 10 | Kafka lag > 1000 |
| Graph | 2 | 5 | CPU > 70% |
| Compliance | 1 | 5 | CPU > 70% |
| Opportunity | 1 | 5 | Request latency > 2s |

### Data Growth Projections

| Year | Documents | Graph Nodes | PostgreSQL |
|------|-----------|-------------|------------|
| Y1 | 10,000 | 500K | 10 GB |
| Y2 | 50,000 | 2.5M | 50 GB |
| Y3 | 200,000 | 10M | 200 GB |

---

## 5. Security

### Authentication

| Requirement | Implementation |
|-------------|----------------|
| API Key Rotation | Every 90 days |
| Session Timeout | 30 minutes inactivity |
| Failed Login Lockout | 5 attempts → 15 min lock |
| MFA for Admin | Required (future) |

### Encryption

| Layer | Standard |
|-------|----------|
| Data in Transit | TLS 1.3 |
| Data at Rest | AES-256 |
| Secrets | AWS KMS / Vault |
| API Keys | bcrypt hash (cost 12) |

### Network

| Requirement | Implementation |
|-------------|----------------|
| SSRF Protection | Block private IPs |
| Rate Limiting | Per-key, Redis-backed |
| DDoS Protection | WAF + CloudFront |
| VPC Isolation | Private subnets for data |

---

## 6. Compliance

### Audit Trail Requirements

| Event Type | Retention | Immutability |
|------------|-----------|--------------|
| Authentication | 2 years | WORM storage |
| Data Access | 7 years | WORM storage |
| Configuration Changes | 7 years | WORM storage |
| API Calls | 90 days | Log aggregation |

### Regulatory Standards

| Standard | Status | Evidence |
|----------|--------|----------|
| SOC 2 Type II | Roadmap Y1 | Control matrix |
| GDPR | Partial | Data handling policy |
| FSMA 204 | Implemented | CTE/KDE tracking |
| 21 CFR Part 11 | Roadmap | E-signatures |

---

## 7. Observability

### Logging

| Requirement | Implementation |
|-------------|----------------|
| Format | Structured JSON |
| Correlation ID | X-Request-ID header |
| Log Level | Configurable per service |
| Retention | 30 days hot, 1 year cold |

### Metrics

| Category | Tool | Endpoints |
|----------|------|-----------|
| Application | Prometheus | `/metrics` |
| Infrastructure | CloudWatch | ECS/RDS metrics |
| Business | Custom dashboards | Grafana |

### Alerting

| Severity | Response Time | Channel |
|----------|---------------|---------|
| Critical (SEV1) | 15 min | PagerDuty |
| High (SEV2) | 1 hour | Slack + Email |
| Medium (SEV3) | 4 hours | Email |
| Low (SEV4) | Next business day | Ticket |

---

## 8. Usability

### Accessibility

| Standard | Requirement |
|----------|-------------|
| WCAG | 2.1 AA compliance |
| Keyboard Navigation | Full support |
| Screen Reader | Compatible |
| Color Contrast | 4.5:1 minimum |

### Browser Support

| Browser | Versions |
|---------|----------|
| Chrome | Last 2 |
| Firefox | Last 2 |
| Safari | Last 2 |
| Edge | Last 2 |

---

## 9. Maintainability

### Code Quality

| Metric | Target |
|--------|--------|
| Test Coverage | > 80% |
| Cyclomatic Complexity | < 10 per function |
| Documentation | All public APIs |
| Linting | Zero warnings |

### Deployment

| Metric | Target |
|--------|--------|
| Deploy Frequency | Daily capable |
| Deploy Duration | < 15 minutes |
| Rollback Time | < 5 minutes |
| Change Failure Rate | < 5% |
