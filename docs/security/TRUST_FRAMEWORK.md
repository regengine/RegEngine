# RegEngine Trust Framework

> Internal draft status: this document contains target architecture and historical control language. It is not a public trust commitment and must not be shared with customers without review against `docs/security/TRUST_CLAIMS_MATRIX.md`, the current codebase, and counsel-approved wording.

## Purpose

This Trust Framework describes technical and operational controls that support RegEngine's FSMA 204 evidence posture. It defines how data integrity, multi-tenant isolation, security controls, compliance evidence, and incident response are intended to work together.

RegEngine operates under the principle that rule evaluations, data transformations, and compliance determinations should be auditable, reproducible, and connected to the evidence that supports them. Public claims must be verified against the current implementation before publication.

---

## Data Integrity Posture

### SHA-256 Hash Chain on Critical Traceability Events

Supported Critical Traceability Event (CTE) workflows create cryptographic verification artifacts:

- **Event Hashing**: Supported CTE persistence paths compute SHA-256 hashes over canonicalized event representations. Verify path coverage before external use.
- **Chain Linking**: When multiple events contribute to a single rule evaluation or transformation decision, the response package includes the hash of each contributing event, creating an auditable chain from raw data through rule output.
- **Hash Verification on Export**: When events are exported (via RequestWorkflow or bulk export endpoints), the response package includes the hash for each event. Client systems may verify these hashes against the source to detect tampering in transit.

**Regulatory Alignment**: Hash chains are intended to make evidence lineage explicit and verifiable. Do not describe this as FDA endorsement, electronic-record certification, or a substitute for customer recordkeeping obligations.

### Immutable Response Packages with Versioned Diffs

The RequestWorkflow module produces response packages that are sealed, versioned, and delta-compatible:

- **Package Sealing**: Supported response packages may include:
  - A manifest listing included events, transformations, and rule decisions
  - The schema version of the payload
  - A package-level SHA-256 hash computed over the complete manifest
  - A timestamp (UTC, ISO 8601) of generation
  - The authenticated user ID and tenant ID that initiated the request

- **Versioning**: Supported response packages are intended to carry canonical model, rule engine, and schema version identifiers.

- **Delta Compatibility**: When supported workflows repeat a rule evaluation or amend a CTE, new response packages can be compared through manifest hashes to identify changed events, re-evaluated rules, and differing conclusions.

### Audit Chain Verification

Evidence workflows are intended to verify audit-record integrity at ingest, persistence, and export where the relevant path creates hash manifests:

- **CI Integration**: Relevant CI workflows should exercise audit-chain tests before release. Verify current workflow coverage before using this language externally. The intended checks:
  - Generates a synthetic CTE stream with known content and computed hashes
  - Persists it to the test database
  - Re-reads each event and verifies the hash matches the stored value
  - Exports the events and verifies package integrity
  - Detects any modification or reordering of events
  - Reports the audit chain integrity score in the CI log

- **Runtime Verification**: Supported evidence paths should compute and persist hashes for committed traceability records. Do not claim interception of every database write unless verified against the current service path.

- **Access Logging**: The AuditChain module is intended to log access to sensitive data (rule evaluations, CTE details, audit records) with sufficient context to identify the user, tenant, timestamp, and action. Retention periods and storage locations are controlled by the executed agreement and current hosting configuration.

---

## Multi-Tenant Isolation

### PostgreSQL Row-Level Security (RLS) Per Tenant

Core PostgreSQL-backed tenant data paths are intended to be protected by PostgreSQL Row-Level Security policies:

- **Policy Scope**: Verify table-by-table RLS coverage before external use. Public copy should state that PostgreSQL row-level policies and authenticated tenant context are designed and tested to restrict core PostgreSQL-backed paths.

- **Policy Mechanism**:
  ```sql
  CREATE POLICY rls_tenant_critical_events ON critical_events
    USING (tenant_id = get_tenant_context())
    WITH CHECK (tenant_id = get_tenant_context());
  ```
  Supported PostgreSQL-backed paths use authenticated tenant context via `app.tenant_id` / `get_tenant_context()`. Verify table-by-table policy coverage before external use.

- **Administrative Access**: Emergency or administrative access should be limited, logged, and reviewed. Do not claim that RLS applies to superusers or every service account without current database-role evidence.

### Tenant Context Enforcement in Database Sessions

Application services are intended to enforce tenant context before accessing tenant-specific records:

- **Session Initialization**: On supported paths, the authentication layer extracts tenant context and binds it to database access before tenant-specific work:
  ```python
  db.session.execute(
    text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
    {"tenant_id": tenant_id}
  )
  ```

- **Enforcement Points**: Core tenant-specific queries should bind authenticated tenant context. Verify exact middleware and query coverage before external use.

- **Query Auditing**: Tenant-specific access should be logged with enough context for review where supported by the active service path.

### Tenant Isolation Tests in CI

Relevant CI workflows and scheduled checks should verify multi-tenant isolation where services and fixtures are available:

- **Test Harness**: Tenant-isolation checks include scheduled/manual API security tests and repo migration tests for RLS coverage. Exact CI gating should be verified before external use.

- **Cross-Tenant Query Simulation**: The test harness simulates a malicious or misconfigured application that attempts to bypass isolation by setting an incorrect tenant ID. It verifies that RLS policies reject this operation.

- **Coverage**: Isolation tests should run in relevant CI workflows; main-branch and release gating must be verified before being described externally.

---

## Security Controls Inventory

### Secret Scanning (gitleaks)

Secret scanning is part of the intended repository security posture:

- **Integration**: Verify current pre-commit, pull-request, and scheduled workflow coverage before external use.
- **Scope**: Scans for AWS keys, Stripe API keys, Supabase JWT tokens, private certificates, and other high-risk patterns.
- **Remediation**: If a secret is detected, the secret should be rotated and removed from the affected history according to the incident response process.

### SAST (Semgrep)

Python code is scanned for common security vulnerabilities where Semgrep workflows are configured:

- **Integration**: Verify current pull-request, scheduled, and main-branch coverage before external use.
- **Rules**: The RegEngine project uses the OWASP Top 10 rule set plus custom rules for FSMA-relevant risks (e.g., event tampering, audit log bypass).
- **Findings**: Blocking behavior depends on the active workflow configuration and branch protection.

### Dependency Audits (pip-audit, npm audit)

Python and Node.js dependencies are scanned for known vulnerabilities where dependency workflows are configured:

- **Python**: `pip-audit` coverage depends on the active CI workflow.
- **Node.js**: `npm audit` coverage depends on the active frontend workflow.
- **Lockfiles**: Both `requirements.lock` and `package-lock.json` are committed to the repository to ensure reproducible builds.

### Container Scanning (Trivy)

Docker images are scanned for vulnerable base images and packages using Trivy where container scanning is configured:

- **Scope**: Scans for CVEs in the base image, Python packages, system libraries, and configuration issues.
- **Integration**: Trivy scan cadence and blocking behavior depend on scheduled/main-branch workflow configuration.
- **Baseline**: Base-image update cadence should be verified before external use.

### DAST (OWASP ZAP Baseline)

A subset of the application may be tested for runtime security vulnerabilities using OWASP ZAP where DAST is configured:

- **Scope**: When `ZAP_TARGET` is configured, CI runs an OWASP ZAP baseline against that target. Container scanning covers the repo-root monolith image on scheduled/main/manual workflows.

- **Baseline**: ZAP baselines and blocking behavior depend on the active DAST target and workflow configuration.

### XXE Prevention (defusedxml)

XML parsing should use hardened parsers such as defusedxml to prevent XML External Entity (XXE) attacks:

- **Integration**: The CTEPersistence module uses `defusedxml.ElementTree` instead of the standard `xml.etree.ElementTree` when parsing EPCIS or other XML-based event formats.
- **Fallback**: If defusedxml parsing fails due to a malformed entity, the event is rejected and logged as a security incident.

### SSRF Prevention (validate_url)

User-supplied URLs should be validated before they are fetched or included in outbound requests:

- **Validation Function**: The `RequestWorkflow.validate_url()` method checks that:
  - The URL uses only http or https schemes
  - The URL does not resolve to a private or reserved IP address (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, etc.)
  - The URL hostname does not match a set of blocked hosts (localhost, *.local, metadata.google.internal, etc.)

- **Integration**: Endpoints that accept URL parameters (e.g., webhook URL, export destination URL) should call `validate_url()` or an equivalent guard before storing or using the URL.

### Subscription Gating (require_active_subscription)

API endpoints that interact with sensitive data or trigger computations should be gated by subscription or contract status where applicable:

- **Decorator**: Where used, the `@require_active_subscription` decorator checks that:
  - The authenticated user's tenant has an active subscription with the required feature set
  - The subscription has not expired or been cancelled
  - The subscription quotas (e.g., CTE volume per month) have not been exceeded

- **Grace Period**: Grace periods and suspension behavior are controlled by the executed agreement and current billing configuration.

- **Fallback**: If the subscription service is unavailable (e.g., Stripe is down), the system defaults to denying access and alerts the security team.

---

## Compliance Evidence Model

Supported rule-evaluation workflows are intended to produce Compliance Evidence Records (CERs) that contain:

- **Rule Metadata**:
  - Rule name and unique identifier (e.g., `fsma_204_cte_type_validation_v1`)
  - Rule version (e.g., `1.2.3`)
  - Regulatory citation (e.g., `21 CFR 11.70, FSMA 204 § 1.1340`)
  - Rule engine version

- **Evidence**:
  - A list of CTEs or data elements inspected by the rule
  - For each inspected item: the item's canonical form, its SHA-256 hash, and the timestamp it was ingested
  - A copy of the rule's decision logic (the Semgrep or custom Python code that was executed)

- **Evaluation Outcome**:
  - Result: pass, fail, warn, or skip
  - If fail or warn: the reason (e.g., "Missing cooling temperature data")
  - The timestamp of the evaluation

- **Response Package**:
  - CERs generated by a supported request may be bundled into a response package with:
    - A package manifest listing all CERs
    - The package SHA-256 hash
    - A signature (HMAC-SHA256) to prove the package was generated by RegEngine
    - A timestamp (UTC, ISO 8601)
    - The authenticated user ID and tenant ID

This model is intended to let a compliance auditor:
1. Request the full evidence for a rule evaluation
2. Receive a cryptographically sealed package with the rule version, inspected data, and decision logic
3. Independently verify the hash, signature, and timestamp
4. Audit the regulatory citation to confirm the rule is correct
5. Trace the evidence back to the original ingested CTE

---

## Incident Response

### Detection

Security incidents are detected via multiple channels:

- **Detection Channels**: Security findings surface through CI failures/artifacts, application monitoring where configured, VDP/manual reports, and incident routing defined in the current incident-response plan.
- **Manual Reports**: Employees and users can report suspected security issues to security@regengine.co.

### Triage

Incident triage targets are defined by the current incident response plan and any executed customer commitments:

- **Severity Assessment**: Incidents are classified as Critical, High, Medium, or Low based on impact (data exposure, availability, compliance violation) and exploitability.
- **Initial Investigation**: The team examines logs, audit trails, and affected data to determine the scope of the incident.

### Communication

- **Internal**: The security team notifies the product, engineering, and legal teams.
- **External**: If customer data was exposed, affected customers and regulators are notified according to applicable law and executed agreement commitments.

### Resolution

- **Containment**: The system is put into a safe state (e.g., affected services are taken offline, access is revoked).
- **Remediation**: The root cause is fixed in the codebase, and the fix is reviewed and deployed.
- **Verification**: Testing confirms that the vulnerability is closed and that similar issues are not present elsewhere.

### Post-Incident

A blameless postmortem is conducted within 5 business days, documented in the Incident Register, and shared with the relevant teams.

---

## Subprocessor List

The public DPA page and `frontend/src/lib/trust-subprocessors.ts` are the current sources for default and where-configured subprocessors. Do not maintain a duplicate static subprocessor table in this framework.

Subprocessor contract obligations, audit rights, and incident-notice commitments must be confirmed against current vendor agreements before being used in customer-facing materials.

---

## Review and Updates

This Trust Framework is reviewed and updated:
- **Annually**: A full security audit and compliance assessment
- **Quarterly**: A review of incident logs and control effectiveness
- **Ad hoc**: In response to new threats, regulatory changes, or identified control gaps

Changes to this framework should be documented and reviewed internally. Customer communications are controlled by the Trust Claims Matrix, public Trust/DPA pages, and executed agreements.
