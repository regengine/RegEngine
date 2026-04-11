# RegEngine — Competitive Landscape & Market Positioning Research

**Date:** 2026-03-28 | **Scope:** FSMA 204 traceability software, horizontal RegTech, rules-as-code ecosystem

---

## Executive Summary

Regulatory "engines" converge from three directions: (a) vertical compliance infrastructure (e.g., FSMA 204 food traceability), (b) horizontal regulatory change/obligations management (financial services RegTech), and (c) rules-as-code/policy-as-code primitives (OPA, Cedar, OpenFisca, Catala, OSCAL).

RegEngine is best understood as **vertical compliance infrastructure for FSMA 204**: it combines canonicalization of traceability events, a versioned rules engine with citable regulatory references, a 24-hour FDA-request response workflow with immutability and signoffs, and security controls for multi-tenant isolation plus audit-chain verification.

**Timeline context:** FDA's Food Traceability Rule originally had a compliance date of January 20, 2026. FDA proposed a 30-month extension to July 20, 2028; Congress then directed FDA not to enforce prior to July 20, 2028.

---

## FSMA 204 Direct Competitors

| Vendor | Key Positioning | Strengths | Pricing |
|--------|----------------|-----------|---------|
| **ReposiTrak** | "Touchless Traceability" — automated, scan-free intake/correlation of shipment + DC data | Large network; AI error detection/auto-correction; no WMS mods required | Not public |
| **Trustwell (FoodLogiQ)** | End-to-end traceability + GS1 alignment | 25K+ suppliers; 250M+ CTEs captured; professional services | Not public |
| **iFoodDS (Trace Exchange)** | Flexible data-sharing (API, EDI ASN, CSV, web forms) + TraceApproved readiness program | Supplier credentialing; multiple ingestion methods | Not public |
| **IBM Food Trust** | Subscription traceability network/platform | Enterprise scale; data access policies; Trace API | Not public |
| **AuditComply** | Farm-to-fork visibility with approval workflows | ERP/procurement integrations; 24-hour FDA reporting | Not public |
| **CompliTrace** | AI-powered KDE extraction from invoices/shipping docs | Smart lot registry; traceback graphs; FDA-ready exports | "Transparent pricing" page |
| **Inteligistics** | "1-Click FSMA 204" — works with existing ERP/WMS | Automates data collection from existing systems | Not public |
| **SGS (TRAKKEY)** | Enterprise-grade digital traceability + audits/training | "Validated by billions of annual transactions" | Not public |

## Horizontal RegTech (Regulatory Change Management)

| Vendor | Focus | Key Features |
|--------|-------|-------------|
| **Ascent RegTech** | Multi-jurisdiction regulatory lifecycle | AI summaries; horizon scanning; obligations inventory; controls mapping |
| **CUBE** | Automated regulatory intelligence | 750+ jurisdictions; obligation mapping; change management |
| **Regology** | Cross-industry compliance | Smart Law Library; AI agent "Reggi"; redlined change views |
| **Compliance.ai** | Regulatory change monitoring | Automated scanning/analysis; dashboards |
| **Corlytics Clausematch** | Policy management | Single source of truth; audit trail; AI classification |

## Rules-as-Code / Policy Engines

| Tool | Type | Relevance to RegEngine |
|------|------|----------------------|
| **OPA (Open Policy Agent)** | CNCF policy engine (Rego language) | Generic policy-as-code; no domain model |
| **AWS Cedar / Verified Permissions** | Managed authorization + Cedar language | RBAC/ABAC; Apache 2.0 |
| **NIST OSCAL** | Machine-readable compliance formats | XML/JSON/YAML for control catalogs + assessment results |
| **OpenFisca** | Rules-as-code engine for law/policy | Tax/benefit simulations; shared interpretations of legislation |
| **Catala** | DSL for statutory-law-to-code | Research-stage; high-assurance legal computation |

---

## Feature Parity Matrix

| Capability | RegEngine | ReposiTrak | Trustwell | iFoodDS | IBM Food Trust | Ascent | OPA |
|-----------|-----------|------------|-----------|---------|----------------|--------|-----|
| Rule authoring (versioned, citable) | **Yes** | Partial | Partial | Partial | Partial | Yes | Yes (Rego) |
| Domain modeling (FSMA events + identity) | **Yes** | Yes | Yes | Yes | Yes | Yes (generic) | Partial |
| Data connectors | Partial | Yes (touchless) | Yes (network) | **Yes** (API/EDI/CSV/forms) | Yes | Partial | Yes (JSON) |
| Workflow / orchestration | **Yes** (10-stage) | Partial | Partial | Partial | Partial | Yes | No |
| Audit trail / integrity | **Yes** (hash chain) | Partial | Partial | Partial | Yes | Yes | Yes (logs) |
| Explainability (why_failed + citations) | **Yes** | Partial | Partial | Partial | Partial | Partial | Partial |
| AI/ML integration | Partial (fuzzy matching) | **Yes** | Unknown | Unknown | Unknown | **Yes** | No |
| Deployment model | Self-host + SaaS | SaaS | SaaS | SaaS | SaaS | SaaS | Self-host |
| Licensing | **Apache 2.0** | Proprietary | Proprietary | Proprietary | Proprietary | Proprietary | Open source |

---

## RegEngine's 4 Defensible Differentiators

### 1. Compliance-Evidence Data Model
Every rule evaluation produces: rule version, inspected evidence fields, pass/fail/warn/skip, human-readable failure reason, and regulatory citation reference. Competitors validate; RegEngine *explains with legal references*.

### 2. 24-Hour Response Workflow as Product Primitive
10-stage workflow (intake → scoping → collecting → gap analysis → exception triage → assembling → internal review → ready → submitted → amended). Immutable packages sealed with SHA-256 hashes. Signoff gates. Blocking-defect checks. No competitor shows this level of operational detail.

### 3. Security Posture as Inherited Controls
Tenant isolation tests, audit chain verification, SAST/DAST, dependency/container scanning in CI. For compliance buyers, "controls you inherit" is a sales asset.

### 4. Open Source (Apache 2.0)
Only open-source option in a space of proprietary SaaS networks. Enables self-hosting, white-labeling, and enterprise embedding.

---

## Where Competitors Outflank RegEngine

| Threat | Who | Impact |
|--------|-----|--------|
| **Network effects** | ReposiTrak, Trustwell, iFoodDS | If ICP = large retailers, "the network IS the product" |
| **Touchless operational integration** | ReposiTrak | Correlates shipment + DC data without WMS mods |
| **AI document extraction** | CompliTrace | Extracts KDEs from invoices/shipping docs (PDF/email world) |
| **Professional services wrapper** | Trustwell, SGS | Software + consulting + audits + training |
| **Retailer-driven timelines** | ReposiTrak, iFoodDS | Retailers enforcing traceability before FDA does |

---

## Recommended Positioning

> "Compliance evidence infrastructure for FSMA 204 teams who need deterministic, auditable outputs — and who cannot afford enterprise network lock-in or a long implementation cycle."

This positions against the proprietary network moats while leaning into RegEngine's strongest assets (explainability, audit integrity, open source, fast deployment).

---

## Strategic Next Steps

### This Week
1. Add RegEngine to G2, SourceForge, Capterra (currently listed on zero comparison sites)
2. Publish the walkthrough page as a standalone case study / blog post
3. Create a "Why Open Source Compliance" positioning page

### This Month
4. Schema-to-regulation trace audit: tie each seeded rule to authoritative FSMA requirements
5. Benchmark connector coverage vs iFoodDS (API/EDI/CSV/forms)
6. Publish audit chain threat model + construction as a trust differentiator

### Next Quarter
7. Document extraction capability (compete with CompliTrace AI-from-invoices)
8. Supplier onboarding portal (lightweight network play)
9. GS1 integration/certification strategy
10. FSMA consultant referral network (cover implementation gaps without building services arm)

---

## FSMA 204 Timeline

| Date | Event |
|------|-------|
| 2011 | FSMA enacted |
| 2022-11 | FDA publishes final Food Traceability Rule |
| 2023-01 | Rule effective (compliance period begins) |
| 2025-03 | FDA announces intent to extend compliance date by 30 months |
| 2026 | Congressional directive: no enforcement prior to July 2028 |
| **2028-07-20** | **Earliest enforcement date** |
