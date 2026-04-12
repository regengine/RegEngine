# Data Processing Agreement (DPA)

**RegEngine, Inc. — Standard Data Processing Agreement**

*Version 1.0 — Effective Date: [INSERT DATE]*

This Data Processing Agreement ("DPA") is entered into between:

- **Controller**: The entity identified in the RegEngine subscription agreement ("Customer")
- **Processor**: RegEngine, Inc., a Delaware corporation ("RegEngine")

This DPA supplements and forms part of the RegEngine Terms of Service or Master Service Agreement between Customer and RegEngine (the "Agreement").

---

## 1. Definitions

**"Personal Data"** means any information relating to an identified or identifiable natural person, as defined under applicable Data Protection Laws.

**"Data Protection Laws"** means all applicable laws relating to data protection and privacy, including GDPR (EU 2016/679), UK GDPR, CCPA/CPRA, and any successor legislation.

**"Processing"** means any operation performed on Personal Data, including collection, recording, organization, storage, adaptation, retrieval, use, disclosure, or erasure.

**"Sub-processor"** means any third party engaged by RegEngine to process Personal Data on behalf of Customer.

---

## 2. Scope of Processing

### 2.1 Categories of Data Subjects

- Customer employees and authorized users
- Customer's suppliers and supply chain partners
- Facility contacts and food safety personnel

### 2.2 Categories of Personal Data

| Category | Examples |
|----------|----------|
| Identity data | Names, job titles, employee IDs |
| Contact data | Email addresses, phone numbers, facility addresses |
| Authentication data | Hashed passwords, MFA secrets, session tokens |
| Supply chain data | GLN (Global Location Numbers), facility identifiers |
| Audit data | IP addresses, user agent strings, action timestamps |

### 2.3 Purpose of Processing

RegEngine processes Personal Data solely to:

- Provide FSMA 204 food traceability compliance services
- Maintain audit trails required by 21 CFR Part 1, Subpart S
- Generate FDA-required sortable spreadsheets per 21 CFR 1.1455(b)(3)
- Operate recall management and supply chain tracing features
- Authenticate and authorize access to the platform

### 2.4 Duration of Processing

Processing continues for the duration of the Agreement plus any legally required retention period. See Section 7 (Retention) for details.

---

## 3. Obligations of RegEngine (Processor)

RegEngine shall:

1. Process Personal Data only on documented instructions from Customer, unless required by applicable law.
2. Ensure that persons authorized to process Personal Data are bound by confidentiality obligations.
3. Implement and maintain appropriate technical and organizational security measures (see Section 5).
4. Assist Customer in responding to data subject rights requests (see Section 6).
5. Assist Customer in ensuring compliance with GDPR Articles 32–36 (security, DPIA, breach notification).
6. At Customer's choice, delete or return all Personal Data upon termination of the Agreement.
7. Make available all information necessary to demonstrate compliance and allow for audits.

---

## 4. Sub-processors

### 4.1 Authorized Sub-processors

RegEngine uses the following sub-processors:

| Sub-processor | Purpose | Location |
|---------------|---------|----------|
| Supabase (via AWS) | Authentication, database hosting | US (AWS us-east-1) |
| Vercel | Frontend hosting, edge functions | US/Global CDN |
| Sentry | Error monitoring (PII minimized) | US |

### 4.2 Changes to Sub-processors

RegEngine will notify Customer at least 30 days before engaging a new sub-processor. Customer may object in writing within 14 days. If a reasonable objection cannot be resolved, Customer may terminate the affected services without penalty.

### 4.3 Sub-processor Obligations

All sub-processors are bound by written agreements imposing data protection obligations no less protective than those in this DPA.

---

## 5. Security Measures

RegEngine maintains the following technical and organizational measures:

**Access Control**: Role-based access with API key authentication (SHA-256 hashed at rest), TOTP-based MFA for admin accounts, configurable session timeouts.

**Encryption**: TLS 1.2+ for data in transit (HSTS enforced), AES-256 encryption at rest for databases and object storage.

**Network Security**: Services bound to localhost only, nginx gateway with rate limiting, Docker network isolation.

**Monitoring**: Structured audit logging for all data access events, OpenTelemetry observability, Sentry error tracking (PII tokenized).

**Incident Response**: Documented incident response procedures with defined severity levels and escalation paths.

**Development Practices**: Dependency vulnerability scanning in CI/CD, Semgrep static analysis, container image scanning, pre-commit security hooks.

---

## 6. Data Subject Rights

RegEngine will assist Customer in fulfilling data subject requests under GDPR Articles 15–22:

- **Right of access** (Art. 15): Export of all Personal Data associated with the data subject
- **Right to rectification** (Art. 16): Correction of inaccurate Personal Data
- **Right to erasure** (Art. 17): Deletion via the GDPR right-to-erasure endpoint (soft-delete with 30-day grace period, followed by hard-delete and audit log anonymization)
- **Right to restrict processing** (Art. 18): Flagging of restricted records
- **Right to data portability** (Art. 20): Export in machine-readable format (JSON/CSV)
- **Right to object** (Art. 21): Processing cessation for objected purposes

RegEngine will respond to Customer's data subject request instructions within 5 business days.

---

## 7. Data Retention

| Data Type | Retention Period | Post-Retention Action |
|-----------|-----------------|----------------------|
| User account data | Duration of account + 30 days | Soft-delete → hard-delete |
| Supply chain records | 24 months (FSMA 204 requirement) | Anonymization of PII fields |
| Audit logs | 24 months | PII anonymization |
| Transaction logs | 84 months (7 years, FDA compliance) | PII anonymization |
| Temporary PII (session data) | 14 days | Hard-delete |

Automated retention enforcement runs nightly via scheduled job.

---

## 8. Data Breach Notification

RegEngine will notify Customer of a Personal Data breach without undue delay and in any event within **72 hours** of becoming aware of the breach. Notification will include:

- Nature of the breach (categories and approximate number of data subjects and records affected)
- Name and contact details of the Data Protection Officer or contact point
- Likely consequences of the breach
- Measures taken or proposed to address the breach

---

## 9. International Data Transfers

When Personal Data is transferred outside the EEA/UK, RegEngine ensures adequate protection through:

- Standard Contractual Clauses (SCCs) approved by the European Commission (Decision 2021/914)
- Data Processing Addendum with each sub-processor
- Supplementary technical measures (encryption, access controls, pseudonymization)

---

## 10. Audit Rights

Customer (or its designated independent auditor) may audit RegEngine's compliance with this DPA once per calendar year, with 30 days' prior written notice. RegEngine will cooperate reasonably and provide access to relevant facilities, systems, and documentation.

RegEngine also makes available SOC 2 Type II reports and penetration test summaries upon request under NDA.

---

## 11. Term and Termination

This DPA takes effect on the date Customer signs the Agreement and remains in effect as long as RegEngine processes Personal Data on behalf of Customer.

Upon termination, RegEngine will:

1. Cease processing Personal Data within 30 days
2. Delete or return all Personal Data (at Customer's election) within 90 days
3. Provide written certification of deletion upon request

Obligations that by their nature survive termination (confidentiality, indemnification) remain in effect.

---

## 12. Governing Law

This DPA is governed by the laws specified in the Agreement. For EU data subjects, GDPR takes precedence where applicable.

---

## Signatures

| | Controller (Customer) | Processor (RegEngine) |
|---|---|---|
| **Name** | _________________________ | _________________________ |
| **Title** | _________________________ | _________________________ |
| **Date** | _________________________ | _________________________ |
| **Signature** | _________________________ | _________________________ |

---

*This DPA template is provided for reference purposes. Customers should have their legal counsel review this document before execution. For questions, contact legal@regengine.co.*
