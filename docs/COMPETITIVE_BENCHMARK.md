# Competitive Benchmark: RegEngine vs. FSMA 204 Incumbents

> **Last updated:** 2026-03-09 (v3 — code-audited RegEngine capabilities, enriched competitor data)
> **Status:** Internal — do not distribute externally without founder approval
> **Author:** Christopher Sellers

---

## Purpose

This document scores RegEngine against the three primary FSMA 204 compliance platforms on the dimensions that actually determine adoption. It exists so the engineering and product team can see where we have real advantages and where we need to close gaps before those advantages matter.

The scoring criteria are chosen from the buyer's perspective: a mid-market food distributor or retailer who needs to be FSMA 204 compliant and is evaluating vendors right now.

**v3 methodology change:** RegEngine scores are now based on a code-level audit of what's actually shipped and functional — not marketing copy or aspirational features. Every RegEngine claim below has a file path backing it.

---

## Competitors

| Company | Product | Key Numbers | Moat |
|---------|---------|-------------|------|
| **ReposiTrak** (NASDAQ: TRAK) | Traceability Network + Enterprise Platform | $5.9M Q2 rev (+7% YoY), 98% recurring, 9 US patents, 4,000+ traceability suppliers, 30K+ compliance network, $25.8M cash | Patent portfolio (Touchless Traceability, Touchless Error Correction), 500+ error detection algorithms, first end-to-end FSMA 204 retailer live, NGA exclusive partner |
| **iFoodDS** | Trace Exchange + TraceApproved | IBM partnership, TraceGains alliance (100K+ supplier locations), Trace Navigator FDA export, two tiers (Supplier Data Link + Core) | Data capture at source (mobile SSCC labels), structured enrollment + certification pipeline, deep EDI/ASN integration, Trace Navigator FDA spreadsheet workflow |
| **Trustwell** | FoodLogiQ Traceability + Recall + Genesis | 25,000+ suppliers in network, FSMA consulting arm (Julie McGill, 30yr), full CTE coverage as of Q2 2025, Operator Dashboard live | Broadest suite (recipe-to-recall), Operator Dashboard for FDA investigations, supplier invitation workflow, variance request process, professional consulting upsell |
| **RegEngine** | FSMA 204 compliance API + free tools | Early-stage, pre-revenue, demo tenants, 23-category FTL Checker live, full FDA export pipeline shipped | Self-service free tools, API-first architecture, SHA-256 evidence hashing on every CTE record, zero-signup time-to-value |

---

## Scoring Dimensions

Each dimension is scored 1–5:

- **1** = Major gap or friction
- **2** = Below average
- **3** = Industry standard
- **4** = Competitive advantage
- **5** = Clear best-in-class

---

### 1. Time-to-First-Value

How fast can a new customer go from "I signed up" to "I have my first compliant CTE record"?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 3 | Sales engagement required. Touchless Traceability eliminates scanning but requires data format mapping across EDI/CSV/XLSX/XML/JSON/API. Onboarding queue exceeds installed base (Q2 FY2026 earnings call) — backlog of suppliers waiting. ReposiTrak manages implementation end-to-end, which means high touch = slower start. Weeks to first compliant record. |
| **iFoodDS** | 2 | Supplier enrollment portal requires company info, GLN setup, trading partner coordination. Two-tier model adds decision friction (Supplier Data Link vs. Trace Exchange Core — and the Data Link is explicitly "not fully FSMA 204 compliant"). TraceApproved certification bundled with Core adds steps. Q4 2025 blog tells prospects to "start now to hit July 2028" — they're planning 2.5-year timelines. |
| **Trustwell** | 2 | Enterprise sales cycle. Supplier invitation requires domain whitelisting (up to 10 domains) before invites can be sent. FSMA consulting recommended (paid). Q1–Q2 2025 still adding fundamental CTE types (harvesting, cooling, packing, landing). Months for full deployment. |
| **RegEngine** | 4 | FTL Checker is live, free, no signup — 23 FDA categories with full CFR §1.1325–§1.1350 mapping (`FTLCheckerClient.tsx`). API ingestion via `POST /api/v1/webhooks/ingest` works today with full KDE validation. First CTE record can be submitted via cURL in under 5 minutes. **Honest gaps:** CSV upload UI is beta-gated (API works, drag-and-drop UI is non-functional). No guided onboarding wizard. IoT import UI is placeholder. |

**RegEngine advantage:** Only platform where a prospect can verify FTL coverage AND submit their first CTE record without talking to a human. Minutes vs. weeks.

**RegEngine gap:** CSV upload UI needs to actually work (currently beta-gated). No white-glove onboarding for enterprise buyers with 500+ suppliers.

---

### 2. Supplier Onboarding Friction

How much work does each supplier in the network need to do to start sharing compliant data?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 4 | Touchless Traceability accepts any format (EDI, CSV, XLSX, XML, JSON, API) and normalizes via canonical data model. Flat-fee per-facility pricing (free for retailers). Patent-pending auto error correction with 500+ algorithms handles 40% average error rate. Hybrid engine: deterministic rules + AI inference with confidence scoring. No new hardware. ReposiTrak manages entire implementation. NGA exclusive partner gives grocery distribution channel. |
| **iFoodDS** | 3 | Multiple data methods (API, flat files, mobile SSCC labels, EDI). TraceGains alliance provides access to 100K+ supplier locations. But two-tier confusion: Supplier Data Link (single customer, not fully compliant) vs. Core (multi-customer, compliant). Enrollment portal requires GLN setup, trading partner coordination. Expert label review included. |
| **Trustwell** | 3 | Q1 2025: Supplier invitation workflow live — Community Owners invite suppliers directly (requires domain whitelisting first). Q2 2025: Bulk activate/deactivate supplier assets. 25,000 suppliers in network. Variance request workflow for attribute exceptions. Operator Dashboard gives suppliers read-only CTE access. Upgraded from 2→3 based on Q1-Q2 2025 feature releases improving supplier experience. |
| **RegEngine** | 2 | API ingestion works (`webhook_router.py`) with GLN check-digit validation, ISO 8601 timestamp validation, and per-CTE-type required field checks. **Honest gaps:** (1) Supplier portal is UI mockup only — "Send Portal Link" button does nothing, 5 hardcoded mock suppliers, no POST endpoint, no invite email generation (`supplier_mgmt.py` has models but no endpoints). (2) No supplier network — zero network gravity. (3) CSV upload UI non-functional. Downgraded from 3→2 because the supplier story is vaporware. |

**RegEngine advantage:** When a supplier does submit data via API, validation is immediate and specific (missing lot code, invalid GLN, etc.). No enrollment ceremony.

**RegEngine gap:** Supplier portal is a UI shell. No invitation flow, no network effect, no format normalization beyond CSV/JSON. This is the gap most likely to kill enterprise deals. Trustwell shipped supplier invitations in Q1 2025 — we need parity.

---

### 3. CTE/KDE Data Quality Controls

How well does the platform ensure the traceability data is actually correct and complete?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 5 | Nine US patents. Hybrid engine: deterministic expert rules + AI-driven inference. 500+ error detection algorithms. Identifies structural, semantic, and contextual anomalies. Generates, ranks, and applies candidate corrections using historical records and cross-document correlation. Confidence scoring routes low-confidence corrections to human review. Canonical data model normalizes all input formats. Addresses documented 40% error rate. Unmatched in the market. |
| **iFoodDS** | 3 | Capture-at-source approach (mobile SSCC pallet labels) prevents errors before they enter the system. Expert label review in TraceApproved certification. Q2 2025 simplified CSV uploads by removing optional fields (reduces formatting errors). Decent prevention, less sophisticated correction. |
| **Trustwell** | 3 | Variance request workflow (Q1 2025) formalizes exception handling with approve/reject + feedback. Community Owners control which attributes allow variances. Q2 2025 added remaining CTE types via CSV upload. Custom tables with data type validation (Q4 2025). Monitoring-oriented, not correction-oriented. |
| **RegEngine** | 3 | **What actually exists in code (`webhook_router.py`, `webhook_models.py`):** 7 CTE types with per-type required KDEs. GLN check-digit validation (13-digit GS1 Luhn algorithm). ISO 8601 timestamp validation with bounds (reject >90 days old or >24 hours future). Unit of measure validation against approved set (lbs, kg, cases, pallets, etc.). Field presence checks. **What doesn't exist:** No ML/AI error correction. No fuzzy matching. No cross-document correlation. No auto-suggestions for typos. Validation is binary: accept or reject. |

**RegEngine advantage:** Validation is immediate at ingest (fail fast). Rules are auditable and deterministic — no black-box AI making unchecked corrections. FTL Checker (free) lets prospects verify coverage before submitting anything.

**RegEngine gap:** ReposiTrak's error correction engine is patent-protected and genuinely superior. Our binary accept/reject is honest but unhelpful when a supplier sends a slightly wrong GLN. Priority: build the 10 most common auto-correction rules (GLN transposition detection, date format normalization, lot code format standardization) without trying to replicate their 500-algorithm patent.

---

### 4. FDA Export & Verification Quality

Can the platform produce the FDA-required electronic sortable spreadsheet within 24 hours, and how trustworthy is the output?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 4 | Designed for FDA sortable spreadsheet template. Generated hundreds of thousands of KDE records for first live retailer. Class-5 secure environment. 24-hour retrieval. Full CTE→KDE matrix. |
| **iFoodDS** | 4 | Trace Navigator: click FDA Spreadsheet link → notification when ready → download. Documented workflow in knowledge base. EDI/ASN data pre-structured for export. Third-party record maintenance supported. |
| **Trustwell** | 3 | Stores CTE data for retrieval. Operator Dashboard provides read-only CTE access for FDA investigations. Q2 2025 completed full CTE coverage (all event types). Less emphasis on FDA template format specifically. |
| **RegEngine** | 3 | **What actually exists in code (`fda_export_router.py`):** Full FDA export pipeline with 30 columns covering TLC, product, quantity, UOM, CTE type, dates, locations, GLNs, carrier, temperature. Three endpoints: single-TLC export, bulk export (date-filtered), export history. SHA-256 hash per row (immutability). Chain hash per row (audit trail linkage). Export audit log persisted to database. CSV StreamingResponse for large exports. **Upgraded from 2→3:** The code audit revealed a working FDA export that the v2 assessment missed. **Remaining gaps:** (1) Output is CSV, not the multi-tab Excel format the FDA template uses (each tab = one CTE type). (2) No UI for generating exports (API-only). (3) No documented 24-hour SLA. |

**RegEngine advantage:** Every exported row carries a SHA-256 hash and chain hash — cryptographic proof of integrity that no competitor advertises. Export audit log means we can prove when data was generated and what it contained.

**RegEngine gap:** (1) FDA template is multi-tab Excel (one tab per CTE type), not flat CSV. Need xlsx output matching the FDA template. (2) Need a "Generate FDA Export" button in the UI, not just API endpoints. (3) Chain hash state is in-memory (`_chain_state` dict) — breaks on service restart. Needs database-backed persistence for production.

---

### 5. Evidence Traceability UX

Can a compliance officer trace a specific product back through the supply chain and see verifiable evidence at each step?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 3 | Network-centric data flow between trading partners via canonical model. Sortable spreadsheet output for FDA, not for investigation UX. No public evidence of visual trace-back, supply chain mapping, or lot-level UI. Their moat is data quality + normalization, not investigation experience. |
| **iFoodDS** | 3 | Trace Navigator for data access, filtering, FDA export. Mobile app captures at source with label verification. Compliance dashboard. Oriented around data management and export, not step-by-step investigation. |
| **Trustwell** | 4 | Operator Dashboard (Q2 2025): read-only CTE view per operator, purpose-built for FDA investigations and retailer requests. Curated resources: FSMA 204 guides, live FDA RSS feed. "Track My Products" feature. FoodLogiQ Recall integrates traceability with recall execution (mobile-accessible). Variance request creates documented exception trail. Best investigation UX of incumbents. |
| **RegEngine** | 1 | **Code audit reality (`trace/page.tsx`):** Trace page exists but is completely non-functional. Hardcoded mock data with `setTimeout(1000)` fake latency. No `/api/v1/trace` endpoint. No graph traversal logic. No facility linking. Search UI renders but returns canned results regardless of input. **Downgraded from 2→1:** v2 said "API returns CTE chains" — code audit shows this isn't true. The trace page is a mockup. The only real data retrieval is the FDA export endpoint, which returns flat records, not linked chains. |

**RegEngine advantage:** The data model (CTE records with TLC, GLN, timestamps, chain hashes) is structurally ready for trace-back. Building the query layer is engineering work, not architectural change.

**RegEngine gap:** This is now our worst score and the gap is real. Every competitor has some investigation capability. We have a mockup page with fake data. Priority: (1) Build a `/api/v1/trace?tlc={TLC}` endpoint that follows a TLC through shipping→receiving→transformation chains. (2) Build a minimal trace-back UI that shows the event timeline for a given lot. (3) Link each event to its SHA-256 hash and chain hash — this is what "evidence traceability" should mean for RegEngine.

---

### 6. Pricing Bridge (Free Tool → Paid Conversion)

Does the platform offer a credible free-to-paid path that lets prospects experience value before committing budget?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 2 | No free tools. Cost calculator on website estimates current compliance spend (inputs: # suppliers, docs/supplier, labor rate) — designed to justify ROI, not give product experience. Free for retailers/wholesalers; suppliers pay flat per-facility fee. NGA partnership gives distribution but not product-led growth. 98% recurring revenue = retention-optimized, not acquisition-optimized. |
| **iFoodDS** | 1 | No free tier. Two subscription tiers (Supplier Data Link, Trace Exchange Core) both require enrollment. Knowledge base articles are public but not interactive tools. Q4 2025 blog explicitly frames timeline as 2.5 years. No way to experience the product without purchasing. |
| **Trustwell** | 2 | Free FSMA 204 guides, compliance resources, live FDA RSS feed. FSMA in Focus Consult (paid) with Julie McGill (30yr experience) is good upsell. Build-vs-buy blog content is decent marketing. But no self-service product. Demo requires sales. |
| **RegEngine** | 5 | **What actually works:** FTL Checker is live, free, no signup, covers all 23 FDA categories with full CFR mapping and per-product CTE/KDE requirements (`FTLCheckerClient.tsx`, 87KB). Data Import Hub shows API ingestion format with working cURL examples. API documentation is public. **What's coming:** CSV upload UI is beta-gated but the API endpoint behind it works. **No competitor is building toward free tools.** ReposiTrak, iFoodDS, and Trustwell are all doubling down on enterprise sales. |

**RegEngine advantage:** Structurally different go-to-market. Every competitor requires a sales conversation before a prospect touches the product. We let them solve a real problem (FTL coverage verification) for free, then offer the obvious next step (submit your CTE data). No incumbent shows any movement toward this model.

**RegEngine gap:** The bridge needs instrumentation. Track: FTL Checker usage → Data Import page views → API key generation → first CTE submission. Add explicit CTAs at each conversion point. The FTL Checker should capture email (opt-in) — current UI audit flagged this as HIGH priority.

---

## Summary Scorecard

| Dimension | ReposiTrak | iFoodDS | Trustwell | RegEngine |
|-----------|-----------|---------|-----------|-----------|
| Time-to-first-value | 3 | 2 | 2 | **4** |
| Supplier onboarding friction | **4** | 3 | 3 | 2 |
| CTE/KDE data quality | **5** | 3 | 3 | 3 |
| FDA export quality | **4** | **4** | 3 | 3 |
| Evidence traceability UX | 3 | 3 | **4** | 1 |
| Pricing bridge | 2 | 1 | 2 | **5** |
| **Total** | **21** | **16** | **17** | **18** |

---

## Score Changes from v2

| Dimension | v2 Score | v3 Score | Reason |
|-----------|----------|----------|--------|
| Supplier onboarding (Trustwell) | 2 | **3** | Upgraded. Q1 2025 shipped supplier invitation workflow with domain whitelisting. Q2 2025 shipped bulk supplier asset management. Material improvement over previous assessment. |
| Supplier onboarding (RegEngine) | 3 | **2** | Downgraded. Code audit revealed supplier portal is UI mockup only — "Send Portal Link" does nothing, hardcoded mock data, no POST endpoint, no invite email. |
| FDA export (RegEngine) | 2 | **3** | Upgraded. Code audit found working FDA export pipeline (`fda_export_router.py`) with 30 columns, SHA-256 per row, chain hashing, export audit log. v2 missed this. Gap is format (CSV vs. multi-tab Excel) and UI, not functionality. |
| Evidence traceability UX (RegEngine) | 2 | **1** | Downgraded. Code audit revealed trace page is completely non-functional — hardcoded mock data, no API endpoint, no graph traversal. v2 said "API returns CTE chains" which is false. |

**Net effect:** RegEngine dropped from 19→18. Trustwell rose from 16→17. The gap vs. ReposiTrak is now 3 points.

---

## What This Tells Us

**RegEngine's total score dropped because we got honest.** The code audit exposed two claims from earlier versions that weren't true (supplier portal, trace-back API). But it also found a capability we'd undersold (FDA export with cryptographic hashing).

### Where We Win

1. **Pricing bridge (5 vs. max 2):** No competitor offers free tools. No competitor is building toward it. This is a structural go-to-market advantage that compounds over time as organic traffic grows.
2. **Time-to-first-value (4 vs. max 3):** Minutes to first CTE record vs. weeks/months. ReposiTrak has an onboarding backlog; iFoodDS plans 2.5-year timelines; Trustwell requires domain whitelisting before supplier invites. We skip all of that.

### Where We Must Improve (Priority Order)

1. **Evidence traceability UX (score: 1 — worst in benchmark):** The trace page is a mockup. Build: (a) `/api/v1/trace?tlc={TLC}` endpoint that follows a lot through CTE chains using existing event data, (b) minimal timeline UI showing events in order with SHA-256 verification links, (c) forward + backward trace capability. This is what "agentic" means for RegEngine — AI that surfaces a verifiable evidence trail, not AI that generates unverifiable text.

2. **Supplier onboarding (score: 2 — below average):** Supplier portal is vaporware. Build: (a) `POST /api/v1/suppliers` endpoint, (b) portal link generation + invite email, (c) supplier-facing page where they can upload CSVs to their buyer's account. Trustwell shipped this in Q1 2025. We need parity.

3. **FDA export format (score: 3 — functional but incomplete):** Backend works but output is CSV. FDA template is multi-tab Excel. Build: (a) xlsx output with one tab per CTE type matching FDA template, (b) "Generate FDA Export" button in dashboard, (c) database-backed chain hash state (currently in-memory — breaks on restart). (d) Document a 24-hour retrieval SLA.

4. **CTE/KDE data quality (score: 3 — industry standard):** Validation is rules-based and binary. Not a crisis but limits enterprise appeal. Start with: GLN transposition detection, date format normalization, lot code format standardization. Don't try to replicate ReposiTrak's 500-algorithm patent.

### The Honest Assessment

**ReposiTrak (21)** is the clear market leader. $5.9M quarterly revenue, 98% recurring, profitable, 9 patents, first live end-to-end deployment. Their Touchless Traceability + Error Correction patent portfolio is a genuine moat. Their biggest vulnerability: onboarding queue exceeds installed base. They can't onboard fast enough.

**Trustwell (17)** has improved significantly with Q1-Q2 2025 releases. Supplier invitations, Operator Dashboard, bulk asset management, and full CTE coverage make them the most complete suite. Their FSMA consulting arm (Julie McGill, 30 years) is a trust differentiator. Weakness: no free-to-paid path, no self-service.

**iFoodDS (16)** has the best distribution play via TraceGains (100K+ supplier locations) and IBM partnership. Trace Navigator's FDA export workflow is production-tested. Weakness: two-tier confusion (Data Link vs. Core, where Data Link is explicitly "not fully compliant"), no free tools, 2.5-year onboarding framing.

**RegEngine (18)** has a unique structural advantage (free tools, self-service, API-first) but the code audit revealed the gap between what's marketed and what's shipped. The FTL Checker, API ingestion, KDE validation, and FDA export with SHA-256 hashing are real and working. The supplier portal, trace-back UI, and CSV upload UI are not. The path forward is to close the gap on the 3 things that are mockups (trace-back, supplier portal, CSV upload) while preserving the 2 things no competitor has (free tools, cryptographic evidence hashing).

**Our window:** ReposiTrak can't onboard fast enough. iFoodDS is telling people to plan 2.5 years. Trustwell requires consulting. The mid-market food company that needs to be compliant by July 2028 and doesn't have 6 figures or 6 months to spare — that's our customer. Ship the trace-back UI, supplier portal, and FDA Excel export, and we have a complete enough product to win that segment.

---

## Appendix: RegEngine Code Audit Reference

For engineering team context, here are the file paths backing each RegEngine score:

| Feature | Primary File | Status |
|---------|-------------|--------|
| FTL Checker | `frontend/src/app/tools/ftl-checker/components/FTLCheckerClient.tsx` | ✅ Live (23 categories, 87KB) |
| API Ingestion | `services/ingestion/app/webhook_router.py` | ✅ Live |
| KDE Validation | `services/ingestion/app/webhook_models.py` (REQUIRED_KDES_BY_CTE) | ✅ Live (7 CTE types) |
| GLN Validation | `services/ingestion/app/webhook_router.py` (Luhn algorithm) | ✅ Live |
| FDA Export | `services/ingestion/app/fda_export_router.py` | ✅ Live (30 columns, 3 endpoints) |
| SHA-256 Hashing | `services/ingestion/app/webhook_router.py` (lines 76–96) | ✅ Live (per-event + chain) |
| Chain Hash State | `services/ingestion/app/webhook_router.py` (_chain_state dict) | ⚠️ In-memory only |
| Export Audit Log | `services/ingestion/app/fda_export_router.py` (persistence.log_export) | ✅ Live |
| CSV Upload UI | `frontend/src/app/tools/data-import/components/DataImportClient.tsx` | ❌ Beta-gated |
| IoT Import UI | `frontend/src/app/tools/data-import/components/DataImportClient.tsx` | ❌ Placeholder |
| Supplier Portal | `frontend/src/app/dashboard/suppliers/page.tsx` | ❌ Mockup (hardcoded data) |
| Supplier Backend | `services/ingestion/app/supplier_mgmt.py` | ❌ Models only, no endpoints |
| Trace-back UI | `frontend/src/app/trace/page.tsx` | ❌ Mockup (hardcoded data) |
| Trace-back API | — | ❌ Does not exist |
| API Key Mgmt | `tests/shared/test_api_key_store.py` | ⚠️ Backend tested, frontend unclear |

---

## Sources

- [ReposiTrak Q2 FY2026 Earnings — $5.9M Revenue, +7%](https://www.stocktitan.net/news/TRAK/reposi-trak-second-quarter-fiscal-2026-revenue-increases-7-to-5-9-ghmj1zstv89w.html)
- [ReposiTrak Q2 FY2026 Earnings Call Transcript](https://www.fool.com/earnings/call-transcripts/2026/02/17/repositrak-trak-q2-2026-earnings-call-transcript/)
- [ReposiTrak First End-to-End FSMA 204 Traceability](https://repositrak.com/press-release/first-retailer-achieves-end-to-end-fsma-204-traceability/)
- [ReposiTrak Touchless Error Correction — 500+ Algorithms, Patent-Pending](https://www.food-safety.com/articles/11124-repositrak-introduces-automated-error-correction-technology-for-traceability-data)
- [ReposiTrak Second Patent-Pending — Touchless Traceability](https://www.stocktitan.net/news/TRAK/reposi-trak-announces-second-patent-pending-within-its-enterprise-13agryoa7ju1.html)
- [ReposiTrak Cost Calculator (ROI estimator, not pricing)](https://repositrak.com/resources/cost-calculator/)
- [ReposiTrak "Lowest Cost" FSMA 204 Positioning + NGA Partnership](https://www.streetinsider.com/Business+Wire/ReposiTrak+Responds+to+the+FDA+FSMA+204+Announcement+with+the+Lowest-Cost,+Easiest-to-Adopt+and+Industry-Backed+Traceability+Solution/20815213.html)
- [iFoodDS Trace Exchange Solution Options (Data Link vs. Core)](https://info.ifoodds.com/kb-trace-exchange/trace-exchange-solution-options)
- [iFoodDS Trace Navigator FDA Spreadsheet Export](https://info.ifoodds.com/kb-trace-exchange/how-to-access-trace-navigator-and-generate-a-fda-sortable-spreadsheet)
- [iFoodDS + TraceGains Alliance — 100K+ Supplier Locations](https://tracegains.com/newsroom/tracegains-and-ifoodds-extend-strategic-alliance-turn-fsma-204-compliance-into-competitive-advantage/)
- [iFoodDS "Start Now to Hit July 2028" — 2.5yr Timeline](https://www.ifoodds.com/blog-h2q4-2025-lay-the-foundation-for-fsma-204-start-now-to-hit-july-2028/)
- [iFoodDS 2026 Blog — "Build the Infrastructure"](https://www.ifoodds.com/blog-2026-build-the-infrastructure/)
- [Trustwell FoodLogiQ Q1 2025 — Supplier Invitations + Variance Requests](https://blog.trustwell.com/q1-2025-foodlogiq-release-supplier-invites-traceability-variance-requests)
- [Trustwell FoodLogiQ Q2 2025 — Operator Dashboard, CSV Upload All CTEs](https://blog.trustwell.com/foodlogiq-q2-2025-release-new-tools-to-enable-traceability-supplier-relationships-and-product-specifications)
- [Trustwell FoodLogiQ Q4 2025 — Custom Tables, Cooling/Receiving Dates](https://blog.trustwell.com/foodlogiq-q4-2025-release-stronger-foundations-for-product-data-specifications-and-traceability)
- [Trustwell FSMA Consulting — Julie McGill](https://www.trustwell.com/services/fsma-204-consulting/fsma-in-focus-consult/)
- [Trustwell 25,000 Suppliers in Network](https://www.food-safety.com/articles/10167-trustwell-announces-25-000-suppliers-now-part-of-its-network-for-traceability)
- [FDA FSMA 204 Final Rule](https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods)
- [FDA Electronic Sortable Spreadsheet Template](https://www.fda.gov/media/179616/download)
