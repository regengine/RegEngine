# Repository Purpose

This repository contains the production application for RegEngine.

RegEngine is a pre-production FSMA 204 traceability system. Its primary job is to ingest supplier and ERP data, normalize it into traceability evidence, validate the evidence against FSMA 204 expectations, and produce audit/export material for regulatory workflows.

## Scope

- FSMA 204 ingestion
- CTE/KDE canonicalization
- Compliance validation and readiness scoring
- Tenant-scoped data model
- Audit evidence and hash-chain persistence
- FDA export generation
- Operator/admin workflows required to manage tenants, users, API keys, and audit logs

## Non-Goals

- Experimental features on the production request path
- Non-FSMA verticals
- Demo-only tooling
- Unbounded generic document or NLP products
- Integrations that bypass tenant isolation, schema validation, or audit evidence persistence

## Production Standard

Code in this repository should be evaluated against the FSMA pipeline:

```text
ingest -> canonicalize -> validate -> persist evidence -> export
```

Changes that do not strengthen or protect that pipeline should be explicitly marked as experimental, archived, or kept outside the production router surface.

