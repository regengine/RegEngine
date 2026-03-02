# SOC 2 Mapping — Fair Lending Compliance OS

## Scope
- Product scope: Fair Lending Compliance OS only (ECOA, FHA, CFPB fair lending exam procedures, interagency manual).
- Excluded scope: AML, KYC onboarding, complaints systems, vendor risk operations.
- In-scope services: Regulatory Intelligence Core, Bias Engine, Model Governance Registry, Audit Artifact Generator, Executive Risk Dashboard, Compliance Knowledge Graph.

## Control Mapping (Trust Services Criteria)

### CC1 — Control Environment
- **Control objective:** Accountability for fair lending model changes and approvals.
- **RegEngine implementation:** Named model owners (`models.owner`), validator identity (`validations.validator`), reviewer sign-off in audit exports.
- **Evidence:** `models`, `validations`, `audit_exports` records with immutable timestamps.

### CC2 — Communication and Information
- **Control objective:** Controlled dissemination of compliance obligations and test methodology.
- **RegEngine implementation:** Regulatory-to-control-to-test chain (`regulations -> obligations -> controls -> tests`) and OpenAPI contract publication.
- **Evidence:** `/v1/regulatory/map` outputs, `services/compliance/openapi/fair_lending_openapi.yaml`.

### CC3 — Risk Assessment
- **Control objective:** Identify and score fair lending exposure continuously.
- **RegEngine implementation:** DIR threshold checks, regression signal, drift checks, weighted exposure score endpoint.
- **Evidence:** `model_compliance_results`, `/v1/risk/summary` responses, risk trend snapshots.

### CC4 — Monitoring Activities
- **Control objective:** Ongoing detection of control failure conditions.
- **RegEngine implementation:** Monthly/real-time monitoring controls derived by RIC and persisted results per model version.
- **Evidence:** analysis timestamps, drift flags, recommended actions, CI pass/fail logs.

### CC5 — Control Activities
- **Control objective:** Prevent unvalidated model changes from production promotion.
- **RegEngine implementation:** automatic deployment lock when `model_changes.change_type` is `retrain`, `feature_added`, or `threshold_change`.
- **Evidence:** `models.deployment_locked`, `models.lock_reason`, linked change records.

### CC6 — Logical and Access Controls
- **Control objective:** tenant-level data isolation and least privilege.
- **RegEngine implementation:** row-level security policies using tenant context (`app.tenant_id`) and tenant header validation.
- **Evidence:** SQL migration RLS policies, API behavior by `X-Tenant-Id`, isolation test runs.

### CC7 — System Operations
- **Control objective:** reliable service operation and defect handling.
- **RegEngine implementation:** backend matrix CI for compliance service (tests/lint/docker), health checks, deployment workflows.
- **Evidence:** GitHub Actions (`Backend Services CI/CD`, `Test Suite Health Check`, `security`) for release commits.

### CC8 — Change Management
- **Control objective:** controlled code and schema changes with auditability.
- **RegEngine implementation:** migration versioning (`V1__fair_lending_compliance_os.sql`), commit history, CI gates.
- **Evidence:** migration files, PR/commit metadata, successful pipeline runs.

### CC9 — Risk Mitigation
- **Control objective:** generate actionable mitigation artifacts when risk thresholds are breached.
- **RegEngine implementation:** recommended remediation in analysis output and immutable export generation.
- **Evidence:** `/v1/fair-lending/analyze` and `/v1/audit/export` records with hash verification.

## Security/Privacy Control Notes
- **PII minimization:** reviewer and owner identifiers tokenized in logs and stored as operational metadata where feasible.
- **Integrity:** audit artifact hash (`hash_sha256`) for export verification.
- **Immutability model:** append-only versioning of exports (`version` increments per model/output type).

## Auditor Walkthrough Sequence
1. Register model and record owner.
2. Record model change (`threshold_change`) and observe deployment lock.
3. Run fair lending analysis and capture DIR/regression/drift outputs.
4. Generate audit export and verify hash/version metadata.
5. Retrieve risk summary and show exposure score derivation.
6. Query CKG summary to demonstrate traceability from obligation to evidence.
