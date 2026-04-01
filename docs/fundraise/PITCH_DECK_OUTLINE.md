# RegEngine Pitch Deck Outline (10 Slides)

**Target audience:** Pre-seed food/ag-tech VCs (S2G Ventures, Bread & Butter Ventures, Tyson Ventures)
**Format:** 3-minute pitch + 10 minutes Q&A

---

## Slide 1: Title & Hook

**Headline:** RegEngine: API-First FSMA 204 Compliance Infrastructure
**Sub-headline:** Retailer-ready traceability evidence in minutes, not days.
**Tagline:** "The Stripe for Food Traceability"

- Logo, founder name, regengine.co
- "Pre-Seed | March 2026 | Confidential"

---

## Slide 2: The Problem

**Headline:** The food supply chain runs on spreadsheets and hope

**Visual:** Side-by-side: messy mixed-lot warehouse pallet vs. FDA warning letter

**Key points:**
- FDA requires 24-hour turnaround for supply chain tracing across 188,000+ businesses
- Legacy WMS can only track one lot code per pallet; real pallets have mixed lots from multiple growers
- Reagan-Udall Foundation (Sept 2024): "Low awareness is pervasive" + "WMS cannot handle the complexity"
- Current state: spreadsheets, statistical guessing, manual assembly under deadline pressure

**Data point:** FDA estimates $570M/year annualized compliance cost

---

## Slide 3: Why Now? (Retailer Pull-Forward)

**Headline:** Retailers aren't waiting for the FDA

**Visual:** Walmart / Sam's Club / Albertsons logos with enforcement timeline

**Key points:**
- FDA extended deadline to July 2028, but retailers are enforcing NOW
- Walmart requires ASN/EDI 856 with KDEs, SSCC-18 labeling, EPCIS/API transmission
- Non-compliance = freight holds, shipment rejection, financial penalties
- For a $10M/year supplier, one rejected shipment costs more than annual compliance software

**Punchline:** "FSMA 204 compliance is not a future requirement. It's a revenue protection imperative today."

---

## Slide 4: The Solution

**Headline:** RegEngine: Ingest > Validate > Trace > Export

**Visual:** Architecture flow diagram:
```
Supplier data (CSV/EDI/EPCIS/API)
    --> Ingest & Normalize
    --> Validate (KDE completeness, TLC continuity)
    --> Trace (forward/backward lot traversal)
    --> Export (FDA spreadsheet, Walmart ASN, EPCIS 2.0)
```

**Key differentiators:**
- API-first: developers integrate in hours, not months
- Multi-format ingestion: works with whatever systems suppliers already have
- Cryptographic integrity: SHA-256 hash-chained records with Merkle tree verification
- Supplier portal: buyers invite upstream partners via link; suppliers submit data without needing an account

---

## Slide 5: Market Size

**Headline:** $570M forced adoption market

**Visual:** TAM/SAM/SOM concentric circles

| | Size | Basis |
|---|---|---|
| **TAM** | $4.45B (US food traceability software) | Grand View Research 2023 |
| **SAM** | $55-114M (FSMA 204 software-substitutable) | 10-20% of FDA's $570M compliance cost |
| **SOM (Yr 3)** | $3.2M ARR (160 customers x $20K ARPA) | Bottom-up from ICP segments |

**Key stat:** 188,000+ domestic food businesses + 212,000+ foreign exporters must comply

---

## Slide 6: Product & Technical Moat

**Headline:** Feature-complete. Production-deployed. Capital-efficient.

**Visual:** Dashboard screenshot + code metrics

**Proof points:**
- 261,000+ lines of code across 987 files (production-deployed at regengine.co)
- All 8 CTE types + full KDE capture per 21 CFR 1.155
- PostgreSQL-only architecture: recursive CTEs for graph traversal, pg_notify for async, RLS for multi-tenancy
- Replaced Neo4j + Redis + Kafka with PostgreSQL -- 60% lower infrastructure costs
- 78+ encoded FSMA obligations with automated compliance scoring
- Hash-chained audit trail with Merkle tree verification (tamper-evident)

**Cost to duplicate:** $800K-$1.5M and 12-18 months of regulatory research

---

## Slide 7: Go-To-Market

**Headline:** Free tool --> Design partner --> Paid SaaS --> Viral expansion

**Visual:** Funnel diagram

**The funnel:**
1. **Free FTL Checker** -- self-serve applicability assessment ("Am I affected?")
2. **Readiness Assessment** -- automated gap analysis against Walmart/FDA requirements
3. **30-Day "Retailer Ready" Pilot** -- design partner package at discounted rate
4. **Paid Annual SaaS** -- $3,600-$25,000+ based on integration depth
5. **Supplier Portal** -- each customer invites 5-50 upstream suppliers via portal links --> viral loop

**The network effect:** Every paying customer creates 5-50 supplier touchpoints. Each supplier submission is a conversion opportunity. This is the same supply-side pull that drove TraceGains to $350M.

---

## Slide 8: Competition

**Headline:** We're not another FSMA tool. We're the compliance evidence engine.

**Visual:** 2x2 matrix

|  | Legacy / Procurement-Heavy | Modern / API-First |
|---|---|---|
| **Network / UI** | ReposiTrak, Trustwell | iFoodDS |
| **Infrastructure / API** | (empty) | **RegEngine** |

**Key competitors:**
- **ReposiTrak:** Network lock-in; 18-month procurement cycles
- **Trustwell:** Heavy consulting model; RegEngine competes on speed-to-first-export
- **iFoodDS:** $78.7M funded; hired FSMA 204 co-author; strongest competitor
- **SafetyChain:** Plant-floor operations; not traceability-first

**Our wedge:** Fastest time-to-retailer-accepted-compliance. Transparent pricing. Developer-first.

---

## Slide 9: Financial Trajectory

**Headline:** Capital-efficient path to $3M+ ARR

**Visual:** Bar chart (ARR) + line chart (customers)

| | Year 1 | Year 2 | Year 3 |
|---|---|---|---|
| **Customers** | 15 | 70 | 160 |
| **Blended ARPA** | $14,000 | $17,000 | $20,000 |
| **ARR** | $210K | $1.19M | $3.20M |
| **Gross Margin** | 70-80% | 80-85% | 85%+ |
| **Team** | 2-3 | 5-8 | 10-15 |

**The comp:** TraceGains exited at $350M on ~$30M revenue with only $6M in total VC raised. 11.7x revenue multiple.

---

## Slide 10: The Ask

**Headline:** Raising $750K-$1.5M Pre-Seed

| | |
|---|---|
| **Instrument** | Post-money SAFE |
| **Target cap** | $10M-$12M post-money |
| **Use of funds** | Security hardening, design partners, initial GTM |
| **Milestones** | 3 signed design partners, 15 paying customers, seed-ready |

**Use of proceeds ($1M raise):**
- 50% Engineering & Product ($500K) -- security fixes, evidence pack hardening, EPCIS/ASN integration
- 25% GTM ($250K) -- design partner recruitment, first GTM hire (month 6), content-led acquisition
- 25% Operations ($250K) -- SOC 2 roadmap, legal (DPA, contracts), cloud infrastructure

**Why now:** Retailer enforcement is creating non-discretionary demand today. The compliance cliff (July 2028) accelerates urgency every quarter. First-mover in API-first compliance infrastructure captures the integration moat.

---

## Appendix Slides (for Q&A)

### A1: Detailed Competitive Landscape
Full competitive benchmarking table with exit comparables

### A2: Reagan-Udall Foundation Validation
Feature mapping table (Appendix A from prospectus)

### A3: Unit Economics
- Per-tenant infrastructure cost: <$5/month on PostgreSQL
- $200-$500/month pricing = 95%+ gross margins
- CAC recovery within 3-4 months at design partner conversion rates

### A4: Technical Architecture
PostgreSQL-only diagram showing RLS, recursive CTEs, pg_notify, hash chain

### A5: Regulatory Timeline
FDA enforcement milestones, retailer deadlines, FTL expansion schedule
