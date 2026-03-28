# RegEngine Trust Framework

## Purpose

This Trust Framework establishes the technical and operational controls that enable RegEngine to process food traceability data with the integrity and verifiability required by the Food Safety Modernization Act (FSMA) section 204 and 21 CFR Part 11. It defines how data integrity, multi-tenant isolation, security controls, compliance evidence, and incident response work together to create a trustworthy system suitable for regulatory reliance.

RegEngine operates under the principle that every rule evaluation, data transformation, and compliance determination must be auditable, reproducible, and cryptographically bound to the evidence that supports it. This framework is binding on all system changes and is reviewed continuously as new threats emerge.

---

## Data Integrity Guarantees

### SHA-256 Hash Chain on Critical Traceability Events

All Critical Traceability Events (CTEs) are immutably recorded with cryptographic verification:

- **Event Hashing**: Each CTE ingested by the CTEPersistence module receives a SHA-256 hash computed over its serialized canonical form (per CANONICAL_MODEL_SPEC.md). This hash is stored alongside the event and included in all downstream audit trails.
- **Chain Linking**: When multiple events contribute to a single rule evaluation or transformation decision, the response package includes the hash of each contributing event, creating an auditable chain from raw data through rule output.
- **Hash Verification on Export**: When events are exported (via RequestWorkflow or bulk export endpoints), the response package includes the hash for each event. Client systems may verify these hashes against the source to detect tampering in transit.

**Regulatory Alignment**: 21 CFR Part 11 § 11.70 (Audit Trails) requires records to include sufficient detail to permit reconstruction of how a conclusion was reached. Hash chains satisfy this requirement by making the evidence lineage explicit and verifiable.

### Immutable Response Packages with Versioned Diffs

The RequestWorkflow module produces response packages that are sealed, versioned, and delta-compatible:

- **Package Sealing**: Every response package (rule evaluation result, CTE export, compliance report) includes:
  - A manifest listing all included events, transformations, and rule decisions
  - The schema version of the payload
  - A package-level SHA-256 hash computed over the complete manifest
  - A timestamp (UTC, ISO 8601) of generation
  - The authenticated user ID and tenant ID that initiated the request

- **Versioning**: Response packages are tagged with the canonical model version, rule engine version, and schema version in use at generation time. If the system later applies a migration, new packages will carry the new version identifier.

- **Delta Compatibility**: When a rule evaluation is repeated or a CTE is amended, the system produces a new response package. The two packages can be compared via their manifest hashes to identify exactly which events changed, which rules were re-evaluated, and which conclusions differ. This enables compliance teams to detect and justify all material changes.

### Audit Chain Verification (CI-Integrated, ISO 27001 12.7.1 Aligned)

The AuditChain module verifies the integrity of all audit records at ingestion, persistence, and export:

- **CI Integration**: Every commit to the main branch runs `pytest -m audit_chain` which:
  - Generates a synthetic CTE stream with known content and computed hashes
  - Persists it to the test database
  - Re-reads each event and verifies the hash matches the stored value
  - Exports the events and verifies package integrity
  - Detects any modification or reordering of events
  - Reports the audit chain integrity score in the CI log

- **Runtime Verification**: The AuditChain middleware intercepts every database write to the `critical_events` table and recomputes the hash for each inserted row. If the computed hash does not match the pre-computed value submitted by the application, the transaction is rolled back and an alert is sent to the security team.

- **ISO 27001 § 12.7.1 Alignment**: The AuditChain module logs all access to sensitive data (rule evaluations, CTE details, audit records) with sufficient context to identify the user, tenant, timestamp, and action. These logs are retained for 7 years and stored in write-once cold storage after 90 days.

---

## Multi-Tenant Isolation

### PostgreSQL Row-Level Security (RLS) Per Tenant

Every table that contains tenant-specific data is protected by PostgreSQL Row-Level Security policies:

- **Policy Scope**: The tables `critical_events`, `rule_evaluations`, `compliance_reports`, and `audit_logs` all enforce RLS policies that restrict rows to the authenticated tenant.

- **Policy Mechanism**:
  ```sql
  CREATE POLICY rls_tenant_critical_events ON critical_events
    USING (tenant_id = current_setting('rls.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('rls.tenant_id')::uuid);
  ```
  This policy automatically filters all SELECT, UPDATE, and DELETE operations to return only rows belonging to the current tenant. An INSERT is rejected if the tenant_id does not match the current tenant.

- **No Bypass**: RLS policies apply to all database users, including superusers and service accounts. The only exception is the database administrator performing emergency recovery, which is logged and audited.

### Tenant Context Enforcement in Every Database Session

The RequestWorkflow and CTEPersistence modules enforce tenant context at the application layer:

- **Session Initialization**: When a request enters the application, the authentication layer extracts the tenant ID from the JWT token (issued by Supabase Auth). This tenant ID is immediately set as a session variable:
  ```python
  db.session.execute(
    text("SET rls.tenant_id = :tenant_id"),
    {"tenant_id": tenant_id}
  )
  ```

- **Enforcement Points**: Every database query executed by the application includes a middleware check that verifies the current session tenant matches the authenticated tenant. If they do not match, the request is rejected with a 403 error and the incident is logged.

- **Query Auditing**: Queries that access tenant-specific data are tagged with the tenant ID and logged for audit purposes. If a query is executed without a valid tenant context, it is rejected at the ORM layer before reaching the database.

### Tenant Isolation Tests in CI

The CI pipeline runs a dedicated test suite to verify multi-tenant isolation:

- **Test Harness**: `tests/integration/test_rls_isolation.py` creates two synthetic tenants, populates each with distinct data, and verifies that:
  - A user authenticated as tenant A cannot read, write, or modify data belonging to tenant B
  - A query executed with tenant A context returns zero rows when filtered on tenant B's data
  - An attempt to INSERT a row with tenant B's ID while authenticated as tenant A is rejected

- **Cross-Tenant Query Simulation**: The test harness simulates a malicious or misconfigured application that attempts to bypass isolation by setting an incorrect tenant ID. It verifies that RLS policies reject this operation.

- **Coverage**: The test runs on every commit and is part of the merge gate for the main branch.

---

## Security Controls Inventory

### Secret Scanning (gitleaks)

All commits are scanned for accidentally committed secrets using the gitleaks tool:

- **Integration**: Gitleaks is configured as a pre-commit hook and runs on every push to the repository.
- **Scope**: Scans for AWS keys, Stripe API keys, Supabase JWT tokens, private certificates, and other high-risk patterns.
- **Remediation**: If a secret is detected, the push is rejected. The developer is required to rotate the secret and purge it from the commit history using git-filter-branch or similar tools before resubmitting.

### SAST (Semgrep)

All Python code is scanned for common security vulnerabilities using Semgrep:

- **Integration**: Semgrep is configured as a CI step and runs on every pull request.
- **Rules**: The RegEngine project uses the OWASP Top 10 rule set plus custom rules for FSMA-relevant risks (e.g., event tampering, audit log bypass).
- **Findings**: High and medium severity findings block merging to main. Low severity findings are reported but do not block.

### Dependency Audits (pip-audit, npm audit)

Python and Node.js dependencies are scanned for known vulnerabilities:

- **Python**: `pip-audit` is configured to run on every CI pipeline. The pipeline fails if any vulnerable dependencies are found.
- **Node.js**: `npm audit` is configured to run on every CI pipeline for the frontend. Audit findings are reported in the CI log.
- **Lockfiles**: Both `requirements.lock` and `package-lock.json` are committed to the repository to ensure reproducible builds.

### Container Scanning (Trivy)

All Docker images (frontend, backend, worker) are scanned for vulnerable base images and packages using Trivy:

- **Scope**: Scans for CVEs in the base image, Python packages, system libraries, and configuration issues.
- **Integration**: Trivy is configured as part of the Docker build pipeline. The build fails if any critical CVEs are detected.
- **Baseline**: The baseline image is updated monthly to capture the latest security patches.

### DAST (OWASP ZAP Baseline)

A subset of the application is tested for runtime security vulnerabilities using OWASP ZAP:

- **Scope**: ZAP is run against the staging environment after deployment and checks for:
  - Missing or misconfigured security headers (Content-Security-Policy, HSTS, etc.)
  - XXE vulnerabilities (tested via the `/api/upload` endpoint)
  - SSRF vulnerabilities (tested via the `/api/validate-url` endpoint)
  - SQL injection (tested via fuzzed query parameters)
  - Broken authentication (tested via session fixation and credential enumeration)

- **Baseline**: The ZAP baseline is committed to the repository and compared against each DAST run. Regressions block the deployment.

### XXE Prevention (defusedxml)

All XML parsing is performed using the defusedxml library to prevent XML External Entity (XXE) attacks:

- **Integration**: The CTEPersistence module uses `defusedxml.ElementTree` instead of the standard `xml.etree.ElementTree` when parsing EPCIS or other XML-based event formats.
- **Fallback**: If defusedxml parsing fails due to a malformed entity, the event is rejected and logged as a security incident.

### SSRF Prevention (validate_url)

All user-supplied URLs are validated before they are fetched or included in outbound requests:

- **Validation Function**: The `RequestWorkflow.validate_url()` method checks that:
  - The URL uses only http or https schemes
  - The URL does not resolve to a private or reserved IP address (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, etc.)
  - The URL hostname does not match a set of blocked hosts (localhost, *.local, metadata.google.internal, etc.)

- **Integration**: Every endpoint that accepts a URL parameter (e.g., webhook URL, export destination URL) calls `validate_url()` before storing or using the URL.

### Subscription Gating (require_active_subscription)

All API endpoints that interact with sensitive data or trigger computations are gated by subscription status:

- **Decorator**: The `@require_active_subscription` decorator is applied to all routes in the RequestWorkflow module. It checks that:
  - The authenticated user's tenant has an active subscription with the required feature set
  - The subscription has not expired or been cancelled
  - The subscription quotas (e.g., CTE volume per month) have not been exceeded

- **Grace Period**: If a subscription expires, the tenant has a 7-day grace period to renew. After 7 days, all API endpoints return 403 Forbidden.

- **Fallback**: If the subscription service is unavailable (e.g., Stripe is down), the system defaults to denying access and alerts the security team.

---

## Compliance Evidence Model

Every rule evaluation in RegEngine produces a Compliance Evidence Record (CER) that contains:

- **Rule Metadata**:
  - Rule name and unique identifier (e.g., `fsma_204_cte_type_validation_v1`)
  - Rule version (e.g., `1.2.3`)
  - Regulatory citation (e.g., `21 CFR 11.70, FSMA 204 § 1.1340`)
  - Rule engine version

- **Evidence**:
  - A list of all CTEs or data elements inspected by the rule
  - For each inspected item: the item's canonical form, its SHA-256 hash, and the timestamp it was ingested
  - A copy of the rule's decision logic (the Semgrep or custom Python code that was executed)

- **Evaluation Outcome**:
  - Result: pass, fail, warn, or skip
  - If fail or warn: the reason (e.g., "Missing cooling temperature data")
  - The timestamp of the evaluation

- **Response Package**:
  - All CERs generated by a single request are bundled into a response package with:
    - A package manifest listing all CERs
    - The package SHA-256 hash
    - A signature (HMAC-SHA256) to prove the package was generated by RegEngine
    - A timestamp (UTC, ISO 8601)
    - The authenticated user ID and tenant ID

This model ensures that a compliance auditor can:
1. Request the full evidence for a rule evaluation
2. Receive a cryptographically sealed package with the rule version, inspected data, and decision logic
3. Independently verify the hash, signature, and timestamp
4. Audit the regulatory citation to confirm the rule is correct
5. Trace the evidence back to the original ingested CTE

---

## Incident Response

### Detection

Security incidents are detected via multiple channels:

- **Automated Alerts**: The CI pipeline, AuditChain middleware, and security scanning tools emit alerts to a dedicated Slack channel (`#security-incidents`) and to the Sentry error tracking service.
- **Manual Reports**: Employees and users can report suspected security issues to security@regengine.ai.

### Triage

The security team triages incidents within 4 hours:

- **Severity Assessment**: Incidents are classified as Critical, High, Medium, or Low based on impact (data exposure, availability, compliance violation) and exploitability.
- **Initial Investigation**: The team examines logs, audit trails, and affected data to determine the scope of the incident.

### Communication

- **Internal**: The security team notifies the product, engineering, and legal teams.
- **External**: If customer data was exposed, affected customers are notified within 72 hours per applicable regulations. Regulators are notified if required by law.

### Resolution

- **Containment**: The system is put into a safe state (e.g., affected services are taken offline, access is revoked).
- **Remediation**: The root cause is fixed in the codebase, and the fix is reviewed and deployed.
- **Verification**: Testing confirms that the vulnerability is closed and that similar issues are not present elsewhere.

### Post-Incident

A blameless postmortem is conducted within 5 business days, documented in the Incident Register, and shared with the relevant teams.

---

## Subprocessor List

RegEngine engages the following subprocessors to deliver service:

| Subprocessor | Purpose | Data Access | Jurisdiction |
|---|---|---|---|
| Vercel | Frontend hosting, CDN, edge functions | Front-end traffic logs, non-sensitive | US, EU |
| Railway | Backend API, application hosting | All application data (encrypted at rest) | US |
| Supabase | PostgreSQL database, authentication | All customer data (encrypted at rest and in transit) | US, EU |
| Stripe | Payment processing, billing | Customer name, email, billing address, payment method (tokenized) | US |
| Sentry | Error tracking, performance monitoring | Application error logs, performance metrics, non-sensitive context | US |

Each subprocessor has executed a Data Processing Agreement (DPA) and is subject to annual security audits. Subprocessors are required to notify RegEngine within 24 hours of any security incidents affecting customer data.

---

## Review and Updates

This Trust Framework is reviewed and updated:
- **Annually**: A full security audit and compliance assessment
- **Quarterly**: A review of incident logs and control effectiveness
- **Ad hoc**: In response to new threats, regulatory changes, or identified control gaps

All changes to this framework are documented, reviewed by the security and compliance teams, and communicated to customers.
