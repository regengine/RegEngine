# RegEngine: Technical Architecture
## Cryptographic Integrity for SOX Evidence

---

> **Reading Guide**
>
> *CISO/IT Security? You're in the right place. 5-minute read.*
> *CFO/CRO? See the [Executive Brief](/verticals/finance/whitepaper/executive-brief) (2 pages).*
> *Building the business case? See the [Full Business Case](/verticals/finance/whitepaper/business-case).*

---

## Trust Model Transparency

**What RegEngine provides**: Tamper-evident evidence storage with cryptographic integrity verification.

**What this means technically**: Every SOX-relevant event is hashed with SHA-256 and linked to the previous event's hash, forming a chain. If any record is modified, the chain breaks—mathematically provable tampering detection.

**What this does NOT mean**: We don't claim blockchain-level immutability. RegEngine operates the database infrastructure, creating a trust relationship. PostgreSQL superusers with direct database access could theoretically disable constraints and rebuild hash chains.

---

## Cryptographic Architecture

### Hash Chain Mechanics

```
Event #1000: User jdoe@corp.com granted "Finance-Approver" role
  Timestamp: 2026-01-15T14:32:18Z
  Content Hash: SHA-256(event_data) = a3f2b891...
  Chain Hash: SHA-256(content_hash + previous_chain_hash)
  
Event #1001: jdoe approved invoice #INV-4429 ($15,000)
  Timestamp: 2026-01-15T16:45:03Z
  Previous Chain Hash: a3f2b891... (references Event #1000)
  Content Hash: b7e4c3d2...
  Chain Hash: SHA-256(b7e4c3d2... + a3f2b891...)
```

**Tamper Detection**: If Event #1001 is altered (changing $15,000 → $1,500), its content hash changes. The chain hash no longer matches. Event #1002 still references the original chain hash, creating a detectable break.

### Trust Layers

| Layer | What It Protects Against | Limitation |
|-------|-------------------------|------------|
| **Database constraints** | Casual/inadvertent edits | DB superuser can disable |
| **Application-level hashing** | Post-hoc modifications | Requires rebuild to falsify |
| **RFC 3161 timestamps** (optional) | Backdated evidence | Requires external service |
| **Air-gapped exports** (optional) | Full chain reconstruction | Requires customer verification |

---

## Integration Architecture

```
┌────────────────────────────────────────────────────────┐
│              Enterprise Systems (Your Environment)      │
│  Active Directory | ServiceNow | AWS/Azure | SAP/Oracle │
└──────────────────────────┬─────────────────────────────┘
                           │ Real-time API (OAuth 2.0 / SAML)
                           ▼
┌────────────────────────────────────────────────────────┐
│                   RegEngine Platform                    │
│  ┌─────────────────────────────────────────────────┐  │
│  │     Evidence Vault (PostgreSQL + Hash Chain)     │  │
│  │     Continuous Control Monitoring Engine         │  │
│  │     SoD Conflict Detection Matrix               │  │
│  └─────────────────────────────────────────────────┘  │
│                                                        │
│  RegEngine-managed infrastructure (SOC 2 Type II)      │
└──────────────────────────┬─────────────────────────────┘
                           │ On-demand export (API / Dashboard)
                           ▼
┌────────────────────────────────────────────────────────┐
│         Audit & Compliance Consumers                    │
│  External Auditors | SEC | Enterprise Procurement       │
└────────────────────────────────────────────────────────┘
```

### Supported Integrations

| System | Integration Method | Data Collected |
|--------|-------------------|----------------|
| **Active Directory / Azure AD** | LDAP sync, Graph API | User provisioning, group membership, access changes |
| **AWS** | CloudTrail, IAM Access Analyzer | Infrastructure changes, access patterns |
| **Azure** | Monitor, Activity Logs | Resource changes, RBAC assignments |
| **ServiceNow** | REST API | Change tickets, approvals, incidents |
| **SAP / Oracle ERP** | RFC, API | Financial transactions, SoD matrices |
| **Salesforce** | Connect API | User access, data exports |

---

## Segregation of Duties (SoD) Enforcement

### Enforcement Model

RegEngine supports two SoD modes:

**Preventive (recommended)**: Block role assignment that creates SoD conflict
```
Event: AD group change grants jdoe "Vendor-Payment-Approve"
Check: User already has "Vendor-Create" role
Action: BLOCK assignment, alert compliance team
Evidence: Tamper-evident log of blocked action (proves control effectiveness)
```

**Detective**: Alert on conflict, allow assignment (for environments requiring human override)

### Conflict Matrix Example

| Role A | Role B | Risk Level | Default Action |
|--------|--------|------------|----------------|
| Vendor-Create | Vendor-Payment-Approve | HIGH | Block |
| GL-Journal-Entry | GL-Journal-Approve | HIGH | Block |
| Code-Deploy-Prod | Code-Review-Approve | HIGH | Block |
| Database-Write | Database-Backup | MEDIUM | Alert |

Matrices are fully configurable per customer environment.

---

## External Verification Options

For environments requiring zero-trust verification:

### Option 1: RFC 3161 Timestamp Anchoring ($5K/year)
- External cryptographic timestamps from VeriSign/DigiCert
- Provides third-party proof of evidence state at specific time
- Satisfies most Big 4 auditor concerns about operator trust

### Option 2: Air-Gapped Hash Exports
- Weekly hash chain exports to customer-controlled S3 bucket
- Customer can independently verify chain integrity
- No RegEngine access required for verification

### Option 3: Blockchain Anchoring (Premium)
- Daily hash anchoring to Ethereum mainnet
- Full cryptographic proof without trust relationship
- Contact sales for pricing

---

## Compliance Certifications

| Certification | Status | Auditor |
|--------------|--------|---------|
| **SOC 2 Type II** | Current | Deloitte |
| **ISO 27001** | Current | BSI |
| **GDPR** | Compliant | DLA Piper (legal review) |
| **FedRAMP** | In Progress (2026 H2) | — |

---

## Data Architecture

### Evidence Retention
- **Default**: 7 years (SOX requirement)
- **Configurable**: 3-25 years based on regulatory needs
- **Export**: Full data portability (JSON, CSV, encrypted archive)

### Encryption
- **At rest**: AES-256 (customer-managed keys available)
- **In transit**: TLS 1.3
- **Key management**: HashiCorp Vault (SOC 2 certified)

### Data Residency
- **Default**: US-East (AWS)
- **Options**: US-West, EU-Frankfurt, AP-Sydney
- **Single-tenant**: Available for enterprise tier

---

## Implementation Requirements

### Technical Prerequisites
- [ ] API credentials for integrated systems (AD, AWS, ServiceNow, ERP)
- [ ] Network connectivity (outbound HTTPS, or VPN for on-prem systems)
- [ ] Service account with read access to audit logs
- [ ] SSO integration (SAML 2.0 or OIDC) for dashboard access

### Typical Timeline
- **Week 1-2**: Integration setup and historical data import
- **Week 3-4**: Control policy configuration and tuning
- **Week 5-8**: Parallel run with existing SOX process
- **Week 9+**: Full production cutover

---

## Contact

**Technical deep-dive**: [security@regengine.co](mailto:security@regengine.co)
**Security questionnaire**: Available on request
**SOC 2 report**: Available under NDA

---

*RegEngine | Enterprise Compliance Infrastructure*
