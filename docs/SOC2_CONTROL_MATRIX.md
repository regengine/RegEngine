# SOC 2 Control Matrix

**Version:** 1.0
**Last Updated:** 2026-01-03
**Audit Period:** TBD
**Status:** Preparation

---

## Trust Services Criteria Mapping

### CC1: Control Environment

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| CC1.1 | Commitment to Integrity | Code review required for all PRs | GitHub PR settings |
| CC1.2 | Board Oversight | Quarterly security reviews planned | Meeting notes (TBD) |
| CC1.3 | Organizational Structure | Service ownership documented | `docs/architecture/` |
| CC1.4 | Competency | Engineering team qualifications | HR records |
| CC1.5 | Accountability | Audit logging for all actions | `shared/audit.py` |

### CC2: Communication and Information

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| CC2.1 | Information Quality | Schema validation on all inputs | `shared/schemas.py` |
| CC2.2 | Internal Communication | Slack channels, documentation | `README.md`, docs/ |
| CC2.3 | External Communication | API documentation, changelog | `CHANGELOG.md` |

### CC3: Risk Assessment

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| CC3.1 | Risk Objectives | NFR document with targets | `NFR_REQUIREMENTS.md` |
| CC3.2 | Risk Identification | Gap analysis, threat modeling | `gap_analysis_validation.md` |
| CC3.3 | Fraud Consideration | Rate limiting, audit trails | `shared/rate_limit.py` |
| CC3.4 | Change Assessment | ADR process for architecture | `docs/architecture/decisions/` |

### CC4: Monitoring Activities

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| CC4.1 | Ongoing Monitoring | Prometheus metrics, health checks | `/metrics` endpoints |
| CC4.2 | Deficiency Remediation | Production readiness checklist | `PRODUCTION_READINESS_CHECKLIST.md` |

### CC5: Control Activities

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| CC5.1 | Control Selection | Defense in depth approach | Architecture docs |
| CC5.2 | Technology Controls | API keys, TLS, encryption | `AUTHENTICATION.md` |
| CC5.3 | Policy Deployment | Infrastructure as code | `infra/`, `docker-compose.yml` |

### CC6: Logical and Physical Access

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| CC6.1 | Logical Access | API key authentication | `shared/auth.py`, `AUTHENTICATION.md` |
| CC6.2 | Access Provisioning | Admin API for key creation | `POST /admin/keys` |
| CC6.3 | Access Removal | Key revocation endpoint | `DELETE /admin/keys/{id}` |
| CC6.4 | Access Review | Key listing with metadata | `GET /admin/keys` |
| CC6.5 | Physical Access | AWS/Cloud provider controls | AWS SOC 2 report |
| CC6.6 | Logical Threats | SSRF protection, input validation | `services/ingestion/app/routes.py` |
| CC6.7 | Identity Management | Tenant isolation, scoped keys | `shared/api_key_store.py` |
| CC6.8 | Access Credentials | Key hashing (bcrypt) | `shared/auth.py` |

### CC7: System Operations

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| CC7.1 | Configuration Management | Docker, Terraform | `docker-compose.yml`, `infra/` |
| CC7.2 | Change Management | Git, PR reviews | GitHub history |
| CC7.3 | Vulnerability Management | Dependency scanning (planned) | CI pipeline |
| CC7.4 | Incident Detection | Audit logging, alerting | `shared/audit.py` |
| CC7.5 | Incident Response | DR/BCP plan | `DISASTER_RECOVERY.md` |

### CC8: Change Management

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| CC8.1 | Change Authorization | PR approval required | GitHub branch protection |

### CC9: Risk Mitigation

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| CC9.1 | Vendor Risk | Third-party risk assessment (planned) | Vendor matrix (TBD) |
| CC9.2 | Risk Acceptance | Risk register (planned) | Risk register (TBD) |

---

## Availability Criteria (A1)

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| A1.1 | Availability Commitment | 99.9% SLA target | `NFR_REQUIREMENTS.md` |
| A1.2 | Capacity Planning | Scaling configuration | `docker-compose.yml`, Terraform |
| A1.3 | Recovery | RTO/RPO defined, backups | `DISASTER_RECOVERY.md` |

---

## Confidentiality Criteria (C1)

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| C1.1 | Confidentiality Commitment | Data classification | Security brief |
| C1.2 | Disposal | Secure deletion procedures | `SECRETS.md` |

---

## Processing Integrity Criteria (PI1)

| Control ID | Criteria | RegEngine Implementation | Evidence |
|------------|----------|--------------------------|----------|
| PI1.1 | Processing Accuracy | Schema validation | `shared/schemas.py` |
| PI1.2 | Processing Completeness | Kafka exactly-once (future) | Consumer config |
| PI1.3 | Processing Timeliness | Latency monitoring | Prometheus metrics |
| PI1.4 | Output Accuracy | Human-in-the-loop review | Review queue system |
| PI1.5 | Input Validation | Pydantic models | All API routes |

---

## Evidence Collection Checklist

### Automated Evidence

- [ ] GitHub PR logs (change management)
- [ ] CloudWatch logs (access logs)
- [ ] Prometheus metrics (performance)
- [ ] Kafka audit topic exports (audit trail)
- [ ] Terraform state (configuration)

### Manual Evidence

- [ ] Security review meeting notes
- [ ] Incident response runbooks
- [ ] Employee security training records
- [ ] Vendor assessment documentation
- [ ] Risk register

---

## Readiness Summary

| Category | Controls | Implemented | Partial | Planned |
|----------|----------|-------------|---------|---------|
| CC (Common) | 27 | 18 | 5 | 4 |
| A (Availability) | 3 | 3 | 0 | 0 |
| C (Confidentiality) | 2 | 1 | 1 | 0 |
| PI (Processing Integrity) | 5 | 4 | 1 | 0 |
| **Total** | **37** | **26 (70%)** | **7 (19%)** | **4 (11%)** |
