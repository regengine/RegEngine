# Non-Functional Requirements (NFRs)

**Version:** 1.0
**Last Updated:** 2026-01-03
**Status:** Internal planning draft - not a public commitment

> This document contains internal targets and historical architecture assumptions. Do not use it as procurement, DPA, security, or public Trust Center copy without review against `docs/security/TRUST_CLAIMS_MATRIX.md` and the current repository. Executed agreements control availability, retention, deletion, and support commitments.

---

## 1. Availability

These are planning targets for capacity and incident-response design. They are not public SLAs and should not be quoted externally unless an executed agreement adopts them.

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Uptime** | 99.9% | Monthly calculation |
| **Planned Downtime** | < 4 hours/month | Maintenance windows |
| **Unplanned Downtime** | < 43 min/month | Incident tracking |

### Planning Availability Tiers

The tier labels below are internal modeling examples, not packaged service commitments.

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
| Background tasks/hour | Scoped per deployment |

---

## 3. Recovery Objectives

| Metric | Target | Justification |
|--------|--------|---------------|
| **RTO** (Recovery Time Objective) | 4 hours | Maximum acceptable downtime |
| **RPO** (Recovery Point Objective) | Contract-defined | Depends on active hosting configuration |

### Backup Schedule

| Data Store | Frequency | Retention |
|------------|-----------|-----------|
| PostgreSQL | Configuration-dependent | Executed agreement and active hosting configuration control |
| Neo4j | Configuration-dependent | Legacy/optional graph posture; active hosting configuration controls |
| Object storage (documents) | Configuration-dependent | Executed agreement controls |
| Background task queue | Configuration-dependent | Replay capability depends on enabled workflow |

---

## 4. Scalability

### Horizontal Scaling

| Service | Min | Max | Trigger |
|---------|-----|-----|---------|
| Admin API | 1 | 3 | CPU > 70% |
| Ingestion | 2 | 10 | Queue depth > 100 |
| NLP | 2 | 10 | Queue depth or configured worker backlog |
| Graph | 2 | 5 | CPU > 70% |
| Compliance | 1 | 5 | CPU > 70% |

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

Implementation details below are target patterns. Confirm the current deployment provider and key-management setup before using these in customer-facing material.

| Layer | Standard |
|-------|----------|
| Data in Transit | Modern TLS configurations |
| Data at Rest | Managed-provider encryption at rest |
| Secrets | Provider key management or vault service, as configured |
| API Keys | bcrypt hash (cost 12) |

### Network

Network-control examples vary by host and environment. Treat this table as a deployment checklist until the live stack is verified.

| Requirement | Implementation |
|-------------|----------------|
| SSRF Protection | Block private IPs |
| Rate Limiting | Per-key, Redis-backed |
| DDoS Protection | Provider edge/WAF controls where configured |
| Network Isolation | Private network controls where configured |

---

## 6. Compliance

### Audit Trail Requirements

| Event Type | Retention | Immutability |
|------------|-----------|--------------|
| Authentication | Executed agreement controls | Append-oriented logs where configured |
| Data Access | Executed agreement controls | Append-oriented logs where configured |
| Configuration Changes | Executed agreement controls | Append-oriented logs where configured |
| API Calls | Executed agreement and active hosting configuration control | Log aggregation where configured |

### Regulatory Standards

| Standard | Status | Evidence |
|----------|--------|----------|
| External assurance program | Preparation | Control matrix |
| GDPR | Partial | Data handling policy |
| FSMA 204 | Supported | CTE/KDE tracking |
| Electronic-record controls | Preparation | E-signature and audit controls |

---

## 7. Observability

### Logging

| Requirement | Implementation |
|-------------|----------------|
| Format | Structured JSON |
| Correlation ID | X-Request-ID header |
| Log Level | Configurable per service |
| Retention | Executed agreement and active hosting configuration control |

### Metrics

Tool names are planning references; use the active deployment's observability stack as the source of truth.

| Category | Tool | Endpoints |
|----------|------|-----------|
| Application | Prometheus | `/metrics` |
| Infrastructure | Provider monitoring | Database/service metrics |
| Business | Custom dashboards | Implementation-dependent |

### Alerting

Response-time rows are internal operating targets unless adopted by an executed support agreement.

| Severity | Response Time | Channel |
|----------|---------------|---------|
| Critical (SEV1) | Target defined by support agreement or incident plan | On-call channel |
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
