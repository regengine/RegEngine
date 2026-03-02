# RegEngine Fair Lending Compliance OS MVP Spec

## Wedge Definition
- Build only fair lending infrastructure for AI underwriting defensibility.
- Scope in: ECOA, FHA, CFPB fair lending examination procedures, Interagency Fair Lending Examination Manual.
- Scope out: AML, KYC onboarding, complaint management, vendor risk, multi-industry expansion.

## Core Services
1. Regulatory Intelligence Core (RIC)
2. Bias and Disparate Impact Engine
3. Model Governance Registry
4. Audit Artifact Generator
5. Executive Risk Dashboard API

All services publish into a shared Compliance Knowledge Graph (CKG).

## Data Contracts

### Regulatory Intelligence
- `regulations(id, source_name, citation, section, text, effective_date)`
- `obligations(id, regulation_id, obligation_text, risk_category)`
- `controls(id, obligation_id, control_name, control_type, frequency, threshold_value)`
- `tests(id, control_id, test_name, methodology, metric_definition, failure_threshold)`

### Model Governance
- `models(id, name, version, owner, deployment_date, status)`
- `validations(id, model_id, validation_type, validator, date, status, notes)`
- `model_changes(id, model_id, change_type, description, date, requires_revalidation)`

### Analysis and Evidence
- `model_compliance_results`
- `audit_exports`
- `ckg_nodes`
- `ckg_edges`

## APIs

### RIC
- `POST /v1/regulatory/map`
- Behavior: map regulation text to obligations, controls, tests, and required evidence structure.

### Bias and Disparate Impact
- `POST /v1/fair-lending/analyze`
- Required analytics:
  - DIR with 0.80 threshold
  - Regression fairness signal
  - Threshold sensitivity (+/-5%, +/-10%)
  - Drift monitoring (approval-rate and KS signal)

### Model Governance
- `POST /v1/models`
- `GET /v1/models/{model_id}`
- `POST /v1/models/{model_id}/validations`
- `POST /v1/models/{model_id}/changes`
- Change trigger lock: retrain, feature_added, threshold_change require fairness re-test.

### Audit Exports
- `POST /v1/audit/export`
- Export classes:
  - regulator_examination_package
  - fair_lending_summary_report
  - model_validation_dossier
  - bias_incident_timeline
- Required fields: citation, controls, methodology, statistical output, model version, timestamp, reviewer sign-off.

### Executive Dashboard
- `GET /v1/risk/summary?model_id=...`
- Exposure score weights:
  - 40% DIR deviation
  - 30% regression significance
  - 20% drift
  - 10% testing recency

### CKG
- `GET /v1/ckg/summary`
- Node types: Regulation, Obligation, Control, Test, Model, Evidence, Reviewer.
- Edge examples: Regulation->Obligation, Obligation->Control, Control->Test, Test->Evidence, Evidence->Model.

## Security Requirements
- Tenant isolation enforced via row-level partitioning.
- Immutable audit artifacts (append-only + hash verification).
- SOC2-aligned structured logging with tokenized identifiers.
- Encryption and PII tokenization strategy required before production launch.

## Delivery Phases

### Phase 1 (Weeks 1-4)
- DIR engine
- Base RIC mapping
- Audit export metadata and hash verification

### Phase 2 (Weeks 5-8)
- Regression fairness module
- Model registry and deployment lock triggers
- Revalidation workflow enforcement

### Phase 3 (Weeks 9-12)
- Drift module hardening
- CKG backbone persistence
- Executive risk scoring and trend views

## Implementation Artifacts in This Repo
- API implementation: `services/compliance/main.py`
- Fair lending routes: `services/compliance/app/routes.py`
- Statistical engine: `services/compliance/app/analysis.py`
- RIC mapping logic: `services/compliance/app/regulatory_intelligence.py`
- In-memory MVP store + CKG projection: `services/compliance/app/store.py`
- SQL schema baseline: `services/compliance/migrations/V1__fair_lending_compliance_os.sql`
- OpenAPI 3.1 contract: `services/compliance/openapi/fair_lending_openapi.yaml`
