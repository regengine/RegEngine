# Competitive Benchmark: RegEngine vs. FSMA 204 Incumbents

> **Last updated:** 2026-03-09 (v2 — refreshed with Q2 FY2026 earnings, latest product releases)
> **Status:** Internal — do not distribute externally without founder approval
> **Author:** Christopher Sellers

---

## Purpose

This document scores RegEngine against the three primary FSMA 204 compliance platforms on the dimensions that actually determine adoption. It exists so the engineering and product team can see where we have real advantages and where we need to close gaps before those advantages matter.

The scoring criteria are chosen from the buyer's perspective: a mid-market food distributor or retailer who needs to be FSMA 204 compliant and is evaluating vendors right now.

---

## Competitors

| Company | Product | Key Numbers | Moat |
|---------|---------|-------------|------|
| **ReposiTrak** (NASDAQ: TRAK) | Traceability Network + Enterprise Platform | $5.9M Q2 rev (+7% YoY), 98% recurring, 9 patents, 4,000+ traceability suppliers, 30K+ compliance network, $25.8M cash | Patent portfolio (Touchless Traceability, auto error correction), 500+ error detection algorithms, first end-to-end FSMA 204 retailer live |
| **iFoodDS** | Trace Exchange + TraceApproved | IBM partnership, TraceGains alliance (access to 100K+ supplier locations), FDA spreadsheet export via Trace Navigator | Data capture at source (mobile labels, SSCC), structured enrollment + certification pipeline, deep EDI/ASN integration |
| **Trustwell** | FoodLogiQ Traceability + Recall | 25,000+ suppliers in network, Genesis Foods nutrition integration, Q4 2025 added cooling/receiving CTE dates | Broadest product suite (recipe-to-recall), Operator Dashboard for investigations, supplier invitation workflow + variance requests |
| **RegEngine** | FSMA 204 compliance API + free tools | Early-stage, demo tenants, 23-category FTL Checker live | Self-service free tools, API-first, zero-signup time-to-value |

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
| **ReposiTrak** | 3 | Requires sales engagement. ReposiTrak manages the entire implementation process for retailers adding suppliers. "Touchless Traceability" eliminates scanning but still needs data format mapping (EDI, CSV, XLSX, XML, JSON, API). Onboarding queue exceeds installed base — meaning there's a backlog of suppliers waiting to be onboarded. Weeks to first compliant record. |
| **iFoodDS** | 2 | Supplier enrollment portal requires company info, GLN setup, trading partner coordination. TraceApproved certification (now included with Trace Exchange Core) adds readiness steps. iFoodDS Q4 2025 blog explicitly advises companies to "start now to hit July 2028" — they're planning 2.5-year onboarding timelines. |
| **Trustwell** | 2 | Enterprise sales cycle. FoodLogiQ requires supplier invitations, network setup, consulting engagement recommended ($). Q4 2025 still adding basic CTE fields (cooling/receiving dates) — platform is still maturing. Months for full deployment. |
| **RegEngine** | 4 | Free tools (FTL Checker, Data Import Hub) available with zero signup. API key generation is self-service. First CTE record can be submitted via CSV upload or API within minutes. No sales call required. **Gap:** No guided onboarding wizard yet; power comes from developer-friendly API, not hand-holding. |

**RegEngine advantage:** Self-service, no-sales-call path to first value. Free tools let prospects validate their FTL coverage before committing. While competitors measure onboarding in weeks-to-months, we measure in minutes.

**RegEngine gap:** Lacks the enterprise onboarding support (white-glove data migration, dedicated CSM) that buyers with 500+ suppliers will demand.

---

### 2. Supplier Onboarding Friction

How much work does each supplier in the network need to do to start sharing compliant data?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 4 | "Touchless Traceability" is the key differentiator — suppliers send data in whatever format they already use (EDI, CSV, XLSX, XML, JSON, API). ReposiTrak's canonical data model normalizes it. Flat-fee per-facility pricing (free for retailers, nominal cost for suppliers) removes volume anxiety. Patent-pending auto error correction handles the ~40% error rate in raw traceability data with 500+ detection algorithms. No new hardware required. ReposiTrak handles the entire implementation. |
| **iFoodDS** | 3 | Multiple data-sharing methods (API, flat files, mobile app, EDI). Dedicated enrollment portal. TraceGains alliance gives access to 100K+ supplier locations — but suppliers must still enroll, potentially complete TraceApproved certification. Expert label review is included. More structured = more friction for small suppliers who just want to upload a CSV. |
| **Trustwell** | 2 | Supplier invitation model — suppliers must be invited by their trading partner, then complete onboarding in FoodLogiQ. 25,000 suppliers in network is the second-largest. Operator Dashboard is read-only, limiting supplier autonomy. Variance request workflow (Q1 2025) helps but adds process. Custom tables (Q4 2025) improve data capture flexibility. |
| **RegEngine** | 3 | CSV upload and API ingestion accept common formats. Automatic KDE validation on ingest. **Gap:** No established supplier network or marketplace. No "invite your supplier" workflow. Each supplier currently onboards independently rather than being pulled into a network by their buyer. No format-agnostic normalization layer like ReposiTrak's. |

**RegEngine advantage:** Low-friction data ingestion with automatic validation. No enrollment ceremony, no certification prerequisite, no invitation required.

**RegEngine gap:** No network effect. ReposiTrak's "send us whatever format you have and we'll normalize it" is genuinely easier for non-technical suppliers. Their 4,000+ traceability network and 30K+ compliance network create gravity we can't match yet. We need: (1) a supplier invitation flow, (2) format-agnostic normalization beyond CSV/API.

---

### 3. CTE/KDE Data Quality Controls

How well does the platform ensure the traceability data is actually correct and complete?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 5 | Nine US patents including Touchless Traceability and Touchless Error Correction. Hybrid engine: deterministic expert rules + AI-driven inference. 500+ error detection algorithms identifying structural, semantic, and contextual anomalies. Generates, ranks, and applies candidate corrections using historical records and cross-document correlation. Confidence scoring routes low-confidence corrections to human review. Canonical data model normalizes EDI/CSV/XLSX/XML/JSON/API inputs. Addresses the documented 40% error rate in raw traceability data. This is their deepest technical moat. |
| **iFoodDS** | 3 | Standardized data capture at label production (SSCC pallet labels via mobile app) prevents errors at source. TraceApproved certification includes expert review of case labels before data sharing begins. Good at preventing errors but less sophisticated at catching errors in already-submitted third-party data. Compliance dashboard provides monitoring. |
| **Trustwell** | 3 | Built-in reporting by supplier, location, and product. Operator Dashboard for CTE visibility. Variance request workflow (Q1 2025) formalizes exception handling. Q4 2025 added cooling/receiving dates and custom tables with data type validation (text, number, yes/no). Solid monitoring and structured capture, but no automated correction engine. |
| **RegEngine** | 3 | KDE validation on ingest, FTL coverage verification against all 23 FDA categories, CTE completeness checks. Validation is rules-based and happens at ingest time (fail fast). **Gap:** No AI-driven error correction comparable to ReposiTrak's. No canonical data model documentation. No cross-document correlation. No confidence scoring on corrections. |

**RegEngine advantage:** Validation happens at ingest time (fail fast, not fail later). FTL Checker is a free, standalone quality tool no competitor offers — prospects can verify their FTL coverage before submitting a single record.

**RegEngine gap:** ReposiTrak's 500-algorithm error correction engine with patent protection is a real moat. To compete: (1) Start with the 10 most common error patterns (missing lot codes, mismatched GLNs, date format inconsistencies, invalid TLC formats). (2) Build cross-record correlation (e.g., "this lot code appeared in a shipping CTE from Supplier A but the receiving CTE from Distributor B has a different product description"). (3) Document our canonical data model.

---

### 4. FDA Export & Verification Quality

Can the platform produce the FDA-required electronic sortable spreadsheet within 24 hours, and how trustworthy is the output?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 4 | Explicitly designed to produce the FDA sortable spreadsheet template. Generated hundreds of thousands of KDE records for first end-to-end retailer. Data stored in class-5 secure environment. 24-hour retrieval capability. Full CTE→KDE matrix per FDA template (each tab = one CTE, columns = KDEs). |
| **iFoodDS** | 4 | Trace Navigator generates FDA sortable spreadsheets on demand — documented workflow: click FDA Spreadsheet link → notification when ready → download. Filtering capabilities built in. EDI/ASN integration means data is pre-structured for export. Third-party record maintenance explicitly supported for the "records others maintain on your behalf" FSMA 204 requirement. |
| **Trustwell** | 3 | FoodLogiQ Traceability stores CTE data for retrieval. Operator Dashboard provides read-only CTE access during FDA investigations. Q4 2025 added cooling/receiving dates to improve record completeness. Less emphasis on the specific FDA spreadsheet template format — more focused on network-level visibility and recall management. |
| **RegEngine** | 2 | CTE records are stored and exportable via API. Compliance service can generate reports. **Gaps:** (1) No explicit "FDA sortable spreadsheet" export matching the FDA template format. (2) No documented 24-hour SLA for data retrieval. (3) No cryptographic proof attached to exports despite it being in our positioning copy. (4) No Trace Navigator-style UI for generating exports. Downgraded from 3→2 because both ReposiTrak and iFoodDS have documented, production-tested FDA export workflows and we don't. |

**RegEngine advantage:** API-first architecture means exports can be automated and integrated into customer workflows rather than manual dashboard pulls. Programmatic access > point-and-click for high-volume operations.

**RegEngine gap:** This is more urgent than originally assessed. iFoodDS has a documented click-to-export FDA spreadsheet workflow. ReposiTrak has generated hundreds of thousands of KDE records for a live retailer. We need: (1) FDA sortable spreadsheet template export (match exact FDA format). (2) Evidence hashes on CTE records (the cryptographic proof we already claim in marketing). (3) A 24-hour retrieval SLA documented in our terms.

---

### 5. Evidence Traceability UX

Can a compliance officer trace a specific product back through the supply chain and see verifiable evidence at each step?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 3 | Network-centric view — data flows between trading partners via canonical model. Sortable spreadsheet output is functional but designed for FDA submission, not real-time investigation. No public evidence of citation-level traceability, visual supply chain mapping, or lot-level trace-back UI. Their moat is data quality, not investigation UX. |
| **iFoodDS** | 3 | Trace Navigator provides data access, filtering, and FDA spreadsheet generation. Mobile app captures data at source with label verification. Compliance dashboard monitors readiness. But the UX is oriented around data management and export, not step-by-step investigation of a specific product's journey. |
| **Trustwell** | 4 | Operator Dashboard is purpose-built for investigation context — read-only CTE view per operator, specifically designed for FDA investigations and retailer requests. "Track My Products" feature. FoodLogiQ Recall integrates traceability with recall execution (mobile-accessible since 2025). Best investigation UX of the incumbents. Curated support materials in dashboard (FSMA 204 guides, live FDA RSS feed). |
| **RegEngine** | 2 | API returns CTE chains but no visual trace-back UI. No dashboard for compliance officers to investigate a specific lot. No Operator Dashboard equivalent. **Gap:** This is our weakest dimension. We have the data model for full CTE chain traversal but no visual interface for non-technical users. A compliance officer can't "follow the evidence" through our platform today. |

**RegEngine advantage:** Our data model supports full CTE chain traversal via API. The architecture is ready for a great investigation UX — the data layer exists, the presentation layer doesn't.

**RegEngine gap:** Biggest gap in the benchmark. Compliance officers are not API users. Priority build: a visual trace-back interface showing the evidence chain for any product/lot, with citation-level links to source records (which CTE produced this KDE? what was the source document? when was it submitted and by whom?). This is what "agentic" should actually mean for RegEngine — not AI that hallucinates, but AI that surfaces a verifiable evidence trail a human can follow.

---

### 6. Pricing Bridge (Free Tool → Paid Conversion)

Does the platform offer a credible free-to-paid path that lets prospects experience value before committing budget?

| Platform | Score | Notes |
|----------|-------|-------|
| **ReposiTrak** | 2 | No free tools. Online cost calculator helps estimate spend. Free for retailers/wholesalers (suppliers pay per-facility flat fee) — this creates adoption pressure from buyers but isn't product-led growth. Prospects must engage sales before experiencing the product. 98% recurring revenue model means they're optimized for retention, not acquisition velocity. |
| **iFoodDS** | 1 | No free tier. Enterprise sales process. TraceApproved training is bundled with Trace Exchange Core subscription (not standalone). Enrollment portal requires commitment. Q4 2025 blog says "start now to hit July 2028" — they're selling urgency, not free trials. No way to "try before you buy." |
| **Trustwell** | 2 | Educational resources and FSMA 204 guides are free (including live FDA RSS feed). Consulting services available for purchase. Build-vs-buy content is decent marketing. But no self-service product experience — demo requires sales engagement. 25K supplier network is a lock-in play, not a try-before-you-buy play. |
| **RegEngine** | 5 | FTL Coverage Checker is free, no signup, covers all 23 FDA categories. Data Import Hub is free (CSV upload, IoT import, API guide). These tools solve real problems ("Am I on the FTL?" "Can I format my data correctly?") that naturally lead to "Now I need to actually submit and store these records." API documentation is public. **This is our clearest structural advantage and no incumbent is building toward it.** |

**RegEngine advantage:** Only platform with genuine product-led growth. Free tools create natural upgrade moments. Prospects self-qualify before we ever talk to them. None of the three competitors show any movement toward free-tier offerings — they're doubling down on enterprise sales.

**RegEngine gap:** The bridge from free tools to paid API usage needs to be explicit and instrumented. Add clear CTAs: "You've verified 847 SKUs against the FTL — now submit your first CTE record in 2 minutes." Track conversion funnel: FTL Checker → Data Import → API key generation → first CTE submission.

---

## Summary Scorecard

| Dimension | ReposiTrak | iFoodDS | Trustwell | RegEngine |
|-----------|-----------|---------|-----------|-----------|
| Time-to-first-value | 3 | 2 | 2 | **4** |
| Supplier onboarding friction | **4** | 3 | 2 | 3 |
| CTE/KDE data quality | **5** | 3 | 3 | 3 |
| FDA export quality | **4** | **4** | 3 | 2 |
| Evidence traceability UX | 3 | 3 | **4** | 2 |
| Pricing bridge | 2 | 1 | 2 | **5** |
| **Total** | **21** | **16** | **16** | **19** |

---

## Score Changes from v1

| Dimension | v1 Score | v2 Score | Reason |
|-----------|----------|----------|--------|
| FDA export quality (RegEngine) | 3 | **2** | Downgraded. iFoodDS Trace Navigator has a documented click-to-export FDA spreadsheet workflow. ReposiTrak generated hundreds of thousands of KDE records live. Our gap is larger than initially assessed. |

**Net effect:** RegEngine total dropped from 20 → 19. The gap vs. ReposiTrak widened from 1 point to 2 points.

---

## What This Tells Us

**RegEngine is competitive on total score despite being pre-revenue and early-stage, but the gap vs. ReposiTrak is real and growing.** ReposiTrak shipped two patent-pending technologies in Q1 2026 and has a live end-to-end retailer deployment. Their Q2 FY2026 financials show 7% revenue growth, 98% recurring, and an onboarding queue that exceeds their installed base — meaning demand is outpacing their capacity. That's our window.

### Where We Win

1. **Pricing bridge (5 vs. max 2):** No competitor offers free tools that solve real problems. None are building toward it. This is our moat for developer and SMB adoption. The incumbents are enterprise-sales-only by design.
2. **Time-to-first-value (4 vs. max 3):** Self-service beats sales-led in speed. ReposiTrak has an onboarding backlog; iFoodDS tells prospects to plan 2.5 years. We can get a first CTE record in minutes. This matters for the long tail of food companies who can't wait.

### Where We Must Improve (Priority Order)

1. **Evidence traceability UX (score: 2):** Build a visual trace-back interface. Compliance officers need to click through a supply chain, not query an API. This is what "agentic" means for RegEngine: AI that surfaces a verifiable evidence trail a human can follow and cite. Every CTE should link to its source record, its submitter, its timestamp, and its validation result. Table stakes for any enterprise deal.

2. **FDA export quality (score: 2, downgraded):** Ship the FDA sortable spreadsheet template export. Match the exact FDA format (tabs per CTE, columns per KDEs). iFoodDS already has a click-to-download workflow in Trace Navigator. ReposiTrak has generated hundreds of thousands of records live. We need: (a) template export, (b) evidence hashes on CTE records, (c) documented 24-hour retrieval SLA.

3. **CTE/KDE data quality (score: 3):** Move beyond rules-based validation. ReposiTrak's 500-algorithm engine with patent protection is the benchmark. Start with the 10 most common error patterns. Build cross-record correlation. Document the canonical data model.

4. **Supplier onboarding (score: 3):** Build a "invite your supplier" flow. Network effects are what make ReposiTrak (4,000+ traceability suppliers) and Trustwell (25,000 suppliers) sticky. iFoodDS's TraceGains alliance gives them access to 100K+ supplier locations. We need our own network play — even if it's just "send this link to your supplier so they can upload their CTEs to your account."

### The Honest Assessment

ReposiTrak is pulling ahead. Their Q2 FY2026 numbers are strong ($5.9M revenue, 98% recurring, profitable), their patent portfolio is expanding (9 patents, 2 filed in 2026), and they have the only live end-to-end FSMA 204 deployment. Their biggest vulnerability is that their onboarding queue exceeds their installed base — they literally can't onboard suppliers fast enough. That's our opening.

iFoodDS is the most credible mid-market alternative. The TraceGains alliance (100K+ supplier locations) gives them distribution we can't match, and the Trace Navigator FDA export workflow is production-tested.

Trustwell has the broadest suite (recipe-to-recall) but the weakest traceability-specific technology. They're a good fit for companies that want one vendor for everything but not the best at any one thing.

**Our path:** We don't out-enterprise any of them. We win by being the fastest, cheapest, most transparent path to FSMA 204 compliance for the thousands of mid-market food companies who can't afford a 6-figure platform, a 3-month implementation, or a 2.5-year plan. Our free tools are the top of the funnel no one else has. The engineering priority is closing the gap on FDA export and evidence UX so we can convert that top-of-funnel into paying customers.

---

## Sources

- [ReposiTrak Q2 FY2026 Earnings — Revenue $5.9M, +7%](https://www.stocktitan.net/news/TRAK/reposi-trak-second-quarter-fiscal-2026-revenue-increases-7-to-5-9-ghmj1zstv89w.html)
- [ReposiTrak Q2 FY2026 Earnings Call Transcript](https://www.fool.com/earnings/call-transcripts/2026/02/17/repositrak-trak-q2-2026-earnings-call-transcript/)
- [ReposiTrak First End-to-End FSMA 204 Traceability](https://repositrak.com/press-release/first-retailer-achieves-end-to-end-fsma-204-traceability/)
- [ReposiTrak Touchless Error Correction — 500+ Algorithms](https://www.food-safety.com/articles/11124-repositrak-introduces-automated-error-correction-technology-for-traceability-data)
- [ReposiTrak Second Patent-Pending (Touchless Traceability)](https://www.stocktitan.net/news/TRAK/reposi-trak-announces-second-patent-pending-within-its-enterprise-13agryoa7ju1.html)
- [ReposiTrak Traceability Network — 4,000 Suppliers](https://www.food-safety.com/articles/9812-repositrak-traceability-network-grows-to-4-000-suppliers-furthering-fsma-204-compliance)
- [ReposiTrak + Upshop Partnership](https://www.businesswire.com/news/home/20250114222704/en/ReposiTrak-and-Upshop-Partner-to-Deliver-Unprecedented-FSMA-204-Solution)
- [ReposiTrak Adds 20 Beverage Suppliers (Jan 2026)](https://www.businesswire.com/news/home/20260120193694/en/ReposiTrak-Traceability-Network-Adds-20-Beverage-Suppliers-to-Queue-Preparing-for-Traceability)
- [iFoodDS Trace Navigator — FDA Sortable Spreadsheet Export](https://info.ifoodds.com/kb-trace-exchange/how-to-access-trace-navigator-and-generate-a-fda-sortable-spreadsheet)
- [iFoodDS Food Traceability Software](https://www.ifoodds.com/software-solutions/food-traceability-software/)
- [iFoodDS + TraceGains Alliance Extended (100K+ Supplier Locations)](https://tracegains.com/newsroom/tracegains-and-ifoodds-extend-strategic-alliance-turn-fsma-204-compliance-into-competitive-advantage/)
- [iFoodDS Q4 2025 — "Start Now to Hit July 2028"](https://www.ifoodds.com/blog-h2q4-2025-lay-the-foundation-for-fsma-204-start-now-to-hit-july-2028/)
- [Trustwell FoodLogiQ Traceability](https://www.trustwell.com/products/foodlogiq/traceability/)
- [Trustwell FoodLogiQ Q4 2025 Release](https://blog.trustwell.com/foodlogiq-q4-2025-release-stronger-foundations-for-product-data-specifications-and-traceability)
- [Trustwell 2025 Year in Review](https://blog.trustwell.com/trustwells-2025-in-review)
- [Trustwell 25,000 Suppliers](https://www.food-safety.com/articles/10167-trustwell-announces-25-000-suppliers-now-part-of-its-network-for-traceability)
- [FDA FSMA 204 Final Rule](https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods)
- [FDA Electronic Sortable Spreadsheet Template](https://www.fda.gov/media/179616/download)
