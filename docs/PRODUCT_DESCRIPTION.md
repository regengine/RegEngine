# RegEngine — Canonical Product Description

This is the source of truth. Every other surface — site, deck, kit, repo doc, sales script — must align here or link here.

## One-line description

RegEngine is an FSMA 204 traceability evidence layer. It ingests supply-chain records, normalizes them into FDA-oriented CTE/KDE structures, persists them with a tamper-evident audit chain where configured, and produces FDA-oriented and retailer-review exports.

## Two-paragraph description

RegEngine sits beside an ERP, not in place of one. The ERP remains system of record for inventory, orders, and finance. RegEngine is the evidence layer that turns existing supply-chain records into FDA-defensible traceability artifacts. It accepts three intake paths — webhook events, CSV uploads, and EPCIS 2.0 / EDI 856 documents — and runs them through Inflow Workbench, a preflight surface where suppliers and operators resolve identity, KDE, and CTE-completeness issues before commit. Nothing reaches the canonical store until the commit gate passes.

Once committed through supported evidence workflows, records land in Postgres with row-level security per tenant and tamper-evident audit metadata where configured. From that store, RegEngine can produce FDA-oriented sortable spreadsheets aligned to 21 CFR 1.1455 where applicable, EPCIS 2.0 JSON-LD for partners on a GS1 stack, and recall-drill simulations on demand. A public verifier (`verify_chain.py`) can help reviewers independently confirm supported export-bundle integrity without trusting our infrastructure.

## What we are NOT

- Not an ERP. We do not hold inventory, orders, or finance — those stay in the customer's system of record.
- Not an AI product. ML is a supportive normalization helper inside Inflow Workbench, not the value proposition. The value is deterministic evidence.
- Not multi-vertical. FSMA 204 food-traceability only. No pharma, no medical device, no general supply-chain compliance.
- Not microservices in deploy. The repo is organized into service folders for code boundaries; production runs them as a small set of monolithic processes.
- Not yet in production. No paying customers. Founding Design Partners only.

## Capability matrix

| Capability | Code evidence |
|---|---|
| CTE/KDE ingestion across webhook, CSV, EPCIS, and EDI | `services/ingestion/app/webhook_router_v2.py`, `services/ingestion/app/csv_templates.py`, `services/ingestion/app/epcis/router.py`, `services/ingestion/app/edi_ingestion/` |
| Inflow Workbench preflight + commit gate | `services/ingestion/app/inflow_workbench.py`, `services/ingestion/app/supplier_portal.py` |
| Tamper-evident audit chain (hash-linked, independently verifiable) | `services/admin/app/audit.py`, `services/admin/app/audit_integrity.py`, `services/shared/cte_persistence/`, `frontend/public/sdk/verify_chain.py` |
| FDA + retailer exports (1.1455 spreadsheet, EPCIS 2.0 JSON-LD, Merkle proofs) | `services/ingestion/app/fda_export/router.py`, `services/ingestion/app/epcis_export.py`, `services/ingestion/app/fda_export/merkle.py` |
| Recall drill simulation and readiness reporting | `services/ingestion/app/recall_simulations.py`, `services/ingestion/app/recall_report.py`, `services/ingestion/app/readiness_router.py` |

## Talking-track opener

RegEngine is infrastructure, not a dashboard. FSMA 204 requires that any actor in a covered food's supply chain produce a sortable spreadsheet of CTEs and KDEs within 24 hours of FDA request. Most operators have the data — scattered across an ERP, supplier emails, and EDI feeds — and no defensible way to assemble it. We are the evidence layer that ingests those records, normalizes them to the regulation's shape, persists them with a hash chain, and exports the artifacts FDA and retailers actually ask for. We are not an ERP, not an AI product, and not multi-vertical. Food traceability, evidence layer, that is the whole product.

Want to see it? regengine.co/verify lets you upload a bundle right now. No login. No email capture. The verifier source is public and the synthetic test bundles are at regengine.co/proof.

## Maintenance rule

Any product description elsewhere — site, deck, kit, repo doc — must align to this file or link here. If you find a contradiction, file an issue against the document, not against the code.
