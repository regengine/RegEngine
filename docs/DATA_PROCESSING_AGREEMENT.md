# Data Processing Agreement (DPA)

**RegEngine LLC — Standard Data Processing Agreement**

*Version 1.0 — Effective Date: [INSERT DATE]*

> Internal template status: this markdown file is not the public source of truth and must not be sent externally without counsel review. Use the public DPA page and `docs/security/TRUST_CLAIMS_MATRIX.md` for current wording. Any executed agreement or negotiated DPA controls over this template.

This Data Processing Agreement ("DPA") is entered into between:

- **Controller**: The entity identified in the RegEngine subscription agreement ("Customer")
- **Processor**: RegEngine LLC, a California limited liability company ("RegEngine")

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

- Provide FSMA 204 traceability evidence workflow services
- Maintain platform audit logs that help support recordkeeping and investigation workflows
- Generate FDA-oriented sortable spreadsheets aligned to 21 CFR 1.1455 where applicable
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
5. Assist Customer with compliance efforts related to GDPR Articles 32–36 (security, DPIA, breach notification), taking into account the nature of processing and information available to RegEngine.
6. Return or schedule active-system deletion of Personal Data upon termination of the Agreement, subject to legal-retention, backup, immutable-log, and executed-agreement limits.
7. Make available documentation reasonably needed to support DPA verification under the confidentiality, scope, and cost controls in the executed agreement.

---

## 4. Sub-processors

### 4.1 Authorized Sub-processors

RegEngine's current public subprocessor list is maintained in the public DPA page and the shared frontend constant at `frontend/src/lib/trust-subprocessors.ts`. Attach or generate the current list at execution time after legal/security review. Do not maintain duplicate static subprocessor tables in this template.

### 4.2 Changes to Sub-processors

Subprocessor notice, objection, and termination rights are controlled by the executed agreement or signed DPA. Do not use this template to promise a notice period or objection process without counsel review.

### 4.3 Sub-processor Obligations

Subprocessor contract obligations should be confirmed against current vendor agreements before this template is executed.

---

## 5. Security Measures

RegEngine maintains the following technical and organizational measures:

**Access Control**: Role-based access with API key authentication (SHA-256 hashed at rest), TOTP-based MFA for admin accounts, configurable session timeouts.

**Encryption**: Encrypted transport for customer and service connections; managed-provider encryption at rest for databases and object storage.

**Network Security**: Services bound to localhost only, nginx gateway with rate limiting, Docker network isolation.

**Monitoring**: Structured audit logging for all data access events, OpenTelemetry observability, Sentry error tracking (PII tokenized).

**Incident Response**: Documented incident response procedures with defined severity levels and escalation paths.

**Development Practices**: CI includes secrets, SAST, and dependency checks; DAST, SBOM, and container scans run when configured or on scheduled/main-branch workflows.

---

## 6. Data Subject Rights

RegEngine will assist Customer in fulfilling data subject requests under GDPR Articles 15–22:

- **Right of access** (Art. 15): Export of all Personal Data associated with the data subject
- **Right to rectification** (Art. 16): Correction of inaccurate Personal Data
- **Right to erasure** (Art. 17): Verified deletion requests are processed according to the executed agreement; active-system deletion may be subject to provider backup expiry and legal-retention caveats.
- **Right to restrict processing** (Art. 18): Flagging of restricted records
- **Right to data portability** (Art. 20): Export in machine-readable format (JSON/CSV)
- **Right to object** (Art. 21): Processing cessation for objected purposes

RegEngine will respond to Customer's data subject request instructions according to the executed agreement and applicable law.

---

## 7. Data Retention

| Data Type | Retention Period | Post-Retention Action |
|-----------|-----------------|----------------------|
| User account data | Executed agreement controls | Scheduled active-system deletion, subject to legal-retention and provider-backup caveats |
| Supply chain records | Customer remains responsible for FSMA 204 retention obligations | Export and off-platform archive recommended before cancellation |
| Audit logs | Executed agreement controls | Anonymization, deletion, or preservation as applicable |
| Transaction logs | Executed agreement and applicable law control | Anonymization, deletion, or preservation as applicable |
| Temporary session data | Operationally limited where configured | Provider and application retention settings apply |

Retention and deletion workflows must be verified against the live environment before being described in a customer agreement.

---

## 8. Data Breach Notification

RegEngine will notify Customer of a Personal Data breach without undue delay and in any event within **72 hours** of becoming aware of the breach. Notification will include:

- Nature of the breach (categories and approximate number of data subjects and records affected)
- Name and contact details of the Data Protection Officer or contact point
- Likely consequences of the breach
- Measures taken or proposed to address the breach

---

## 9. International Data Transfers

Where required for a customer deployment, RegEngine relies on the transfer mechanism set out in the executed DPA or procurement package, depending on the data flow and subprocessor. Such mechanisms may include:

- Standard Contractual Clauses (SCCs) approved by the European Commission (Decision 2021/914)
- a UK Addendum/IDTA or another approved transfer mechanism where applicable
- Supplementary technical measures (encryption, access controls, pseudonymization)

---

## 10. Audit Rights

Audit rights are controlled by the executed agreement. RegEngine's standard diligence process prioritizes written security questionnaires, available policies, control summaries, and completed third-party attestations when available. Direct system, facility, or personnel audits should be permitted only where required by law or expressly agreed, and should remain subject to confidentiality, security, scope, timing, and cost controls.

Formal audit reports, penetration-test summaries, or similar artifacts are provided only if completed and available for the requested review tier under NDA.

---

## 11. Term and Termination

This DPA takes effect on the date Customer signs the Agreement and remains in effect as long as RegEngine processes Personal Data on behalf of Customer.

Upon termination, RegEngine will:

1. Cease processing Personal Data according to the executed agreement
2. Return or schedule active-system deletion of Personal Data according to the executed agreement
3. Provide written confirmation where supported by the agreement and live deletion workflow

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
