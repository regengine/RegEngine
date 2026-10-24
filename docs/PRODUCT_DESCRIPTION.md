# RegEngine — Canonical Product Description

Product descriptions should align with this document or link here. Capability claims below are grounded in checked-in code and the consolidated API's release policy. Live configuration, customer adoption, and deployment success require separate evidence.

## One-line description

RegEngine is an API-first FSMA 204 food traceability evidence platform: supplier and ERP data ingestion, CTE/KDE validation, tamper-evident audit records, recall readiness, and FDA-oriented exports.

## Product description

RegEngine works alongside an ERP, turning existing food supply-chain records into traceability evidence. It accepts webhook events, CSV uploads, EPCIS documents, and EDI records. Inflow Workbench provides a preparation workflow with preflight checks, readiness scoring, a fix queue, and a commit gate. Direct intake routes have their own validation and persistence paths; not every ingestion request passes through Workbench.

Accepted events are stored with tenant boundaries in PostgreSQL. The platform evaluates versioned rules, records audit evidence, and provides FDA-oriented exports, request-response cases, auditor workflows, and recall readiness reports. Canonical and legacy persistence paths coexist during a documented cutover. Rule enforcement can be advisory or blocking according to configuration and route support.

Optional Jev assistance suggests mappings for unfamiliar CSV columns and a file's CTE when none is declared. Upload screens expose suggestions for operator review. Automatic application defaults off, requests use headers without row samples by default, and model suggestions do not replace deterministic validation. Preview and evaluation tools let operators inspect suggestions before enabling automatic application.

Public synthetic artifacts, a browser verifier, a downloadable Python bundle verifier, and a reproducible recall drill let reviewers inspect the evidence format. Successful hash or Merkle verification establishes artifact integrity; it does not establish source-data accuracy or regulatory approval.

## Capability and availability matrix

“Release-enabled” means included in the checked-in production routing policy, not a live deployment check. The authoritative policy is [server/router_policy.py](../server/router_policy.py); mounting is in [server/main.py](../server/main.py).

| Capability | Availability and code evidence |
| --- | --- |
| Webhook, CSV, EPCIS, and EDI intake; CTE/KDE normalization | Core intake: [webhook routes](../services/ingestion/app/webhook_router_v2/routes.py), [CSV intake](../services/ingestion/app/csv_templates.py), [EPCIS](../services/ingestion/app/epcis/router.py), [EDI](../services/ingestion/app/edi_ingestion/). |
| Inflow Workbench and supplier preflight | Release-enabled: [Workbench](../services/ingestion/app/inflow_workbench.py), [supplier portal](../services/ingestion/app/supplier_portal.py). |
| Jev CSV header and file-CTE suggestions | Optional integration: [settings and policies](../services/shared/jev/), [configuration and evaluation guide](engineering/JEV_HEADER_MAPPING.md). Requires provider configuration; automatic application is opt-in. |
| Versioned rules and compliance scores | Release-enabled: [rules engine](../services/shared/rules/engine.py), [compliance validation](../services/compliance/app/routes.py), [score API](../services/ingestion/app/compliance_score.py). Enforcement is configuration-dependent. |
| Tenant-scoped records and tamper-evident chains | [Tenant authority](../services/shared/tenant_context.py), [canonical persistence](../services/shared/canonical_persistence/writer.py), [canonical chain verification](../services/shared/canonical_persistence/verification.py), [admin audit integrity](../services/admin/app/audit_integrity.py). See [persistence cutover](persistence/dual-write-cutover.md). |
| FDA-oriented exports and request-response packages | Release-enabled: [FDA export](../services/ingestion/app/fda_export/router.py), [request workflow](../services/ingestion/app/request_workflow_router.py), [auditor API](../services/ingestion/app/auditor_router.py). |
| Readiness assessments and recall reporting | Release-enabled: [readiness](../services/ingestion/app/readiness_router.py), [recall reports](../services/ingestion/app/recall_report.py). |
| Bundle verifier and synthetic recall drill | [Browser verifier](https://regengine.co/verify), [recall drill](https://regengine.co/proof/recall-drill), [verifier source](../frontend/public/sdk/verify_chain.py). Synthetic demonstration data. |
| Supplier manifest remediation and correction links | Implemented in [remediation](../services/ingestion/app/remediation/) and the [buyer dashboard](../frontend/src/app/remediation/page.tsx); excluded from the production router allowlist. Notification delivery also requires recipient/provider configuration. |
| EPCIS JSON-LD export and broader recall simulations | Implemented in [EPCIS export](../services/ingestion/app/epcis_export.py) and [simulations](../services/ingestion/app/recall_simulations.py); these routers are experimental and excluded from the production allowlist. Public sample EPCIS downloads are a separate proof surface. |
| Inbound email CSV ingestion | [Postmark integration](../services/ingestion/app/email_ingest/); excluded from the production allowlist, with no self-service provisioning UI. See [rollout notes](engineering/EMAIL_INGESTION.md). |
| Passwordless login and administration | [Email OTP/passkey auth](../services/admin/app/auth/challenges_router.py), tenant/user/API-key management, and session controls. Email delivery requires provider and identity provisioning. |
| Subscription access and usage metering | [Subscription gate](../services/ingestion/app/subscription_gate.py), [metering design and limitations](../DESIGN_metering-billing.md). Usage reporting to Stripe requires an operator call; there is no periodic reporting job. |
| Python SDK and record verifier | [Source-installable SDK](../regengine/README.md): record lookup/query and verification. Graph-based trace, timeline, export, recall, and readiness methods require experimental routes. Not published to PyPI. |

## Scope and runtime

- Focus: FSMA 204 food traceability. Inventory, orders, and finance remain in the customer's ERP.
- AI assistance supports data preparation; deterministic validation and evidence are the product contract.
- One consolidated FastAPI backend (`server.main:app`) is built from the root Dockerfile for Railway. Service directories organize code within that process.
- The Next.js 16 frontend deploys separately to Vercel. PostgreSQL stores tenant records; Redis supports runtime controls. Graph/NLP modules are not the core release surface.
- Stage: pre-production/design-partner development. This repository does not prove paid adoption, regulatory approval, or FDA certification.
- The application is proprietary and source-visible under the repository [license](../LICENSE). The public verifier tools have the Apache 2.0 exceptions specified there.

## Talking-track opener

RegEngine turns supplier and ERP records into traceability evidence for food businesses. Import records, identify missing or inconsistent CTEs and KDEs, resolve issues, and assemble FDA-oriented exports with verifiable audit evidence. Inflow Workbench prepares the data; RegEngine stores and verifies the evidence. Check a bundle at [regengine.co/verify](https://regengine.co/verify).

## Maintenance rule

Update this document when implementation or release availability changes, and keep the root README, frontend README, SDK metadata, and GitHub description/topics aligned. Verify claims against source and routing policy; record live deployment evidence separately.
