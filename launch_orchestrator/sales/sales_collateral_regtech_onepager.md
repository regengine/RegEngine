# RegEngine – RegTech Vendor One-Pager

## Who We Help

RegTech platform vendors and GRC software companies who need to:

- Rapidly expand regulatory coverage to new jurisdictions
- Maintain complex ingestion and NLP infrastructure
- Differentiate with deeper regulatory intelligence

---

## What RegEngine Provides (OEM/API Licensing)

RegEngine is the **regulatory data infrastructure layer** that powers your compliance platform, providing:

1. **Turnkey ingestion** – from 20+ jurisdictions out of the box
2. **Battle-tested NLP** – obligation extraction with provenance tracking
3. **Graph-based persistence** – bitemporal relationships and lineage queries
4. **API-first architecture** – seamless integration with your existing stack

---

## Why Build vs. Buy Doesn't Make Sense

### If You Build In-House

- **18+ months** to first production-ready jurisdiction
- **$500k-$1M** in engineering costs (2-3 FTEs)
- **Ongoing maintenance** – regulatory sources change, NLP models drift
- **Limited coverage** – realistically 3-5 jurisdictions max
- **Opportunity cost** – engineers not building your differentiated UX

### If You License RegEngine

- **2-4 weeks** to first integration
- **$50k-$200k/year** (vs. $500k+ to build)
- **Automatic updates** – we maintain ingestion pipelines and models
- **20+ jurisdictions** – US, EU, UK, APAC, and growing
- **Focus on differentiation** – your team builds what makes you unique

**ROI**: 10-100x cheaper than building, 10x faster to market

---

## How It Works (OEM Integration)

### 1. White-Label API Access

You get:
- Dedicated API keys with your branding
- Custom rate limits and quotas
- Priority support and SLAs

### 2. Seamless Integration

```python
import regengine

# Initialize with your OEM credentials
client = regengine.Client(api_key="your_oem_key")

# Ingest regulation
doc = client.ingest_url("https://www.sec.gov/rules/final/example.pdf")

# Extract obligations
obligations = client.extract_obligations(doc.id)

# Query gaps
gaps = client.find_gaps(
    jurisdiction="United States",
    customer_controls=your_controls
)
```

### 3. Your Brand, Your UX

- RegEngine runs in the background (invisible to your customers)
- You present insights in your UI/dashboard
- You own the customer relationship

---

## Use Cases for RegTech Vendors

### Use Case 1: Multi-Jurisdiction Expansion

**Problem**: Customer wants coverage for EU MiFID II, but you only support US regulations

**Solution**: License RegEngine's EU module
- Instant access to EBA, ESMA, and national regulator content
- Pre-extracted obligations and thresholds
- Cross-jurisdictional comparison APIs

**Time to market**: 2-4 weeks vs. 18+ months

### Use Case 2: Enhanced Gap Analysis

**Problem**: Customers want "which of our controls are missing?" insights

**Solution**: Use RegEngine's gap detection API
- Feed in customer's internal control catalog
- Get back obligations with no matching controls
- Surface actionable remediation steps

**Customer value**: Quantifiable risk reduction

### Use Case 3: Audit-Ready Lineage

**Problem**: Auditors ask "why does this control exist?" for 100+ controls

**Solution**: Query RegEngine's graph for provenance
- Trace control → obligation → regulation → source document (PDF + page number)
- Export lineage reports for audit committees

**Customer value**: Pass audits faster, reduce compliance overhead

---

## Business Models We Support

### 1. Usage-Based Licensing

- Pay per API call or per document ingested
- Align costs with your customer growth
- Predictable pricing, no surprises

### 2. Revenue Share

- Percentage of revenue from customers using RegEngine-powered features
- Win together as you scale

### 3. Fixed Annual License

- Unlimited usage for a fixed fee
- Simple budgeting, high-volume use cases

---

## Technical Architecture

### RegEngine Backend (We Manage)

```
┌─────────────────────────────────────┐
│         RegEngine Platform          │
│  ┌────────┐  ┌────────┐  ┌────────┐│
│  │Ingest  │─▶│  NLP   │─▶│ Graph  ││
│  │Engine  │  │Extract │  │ DB     ││
│  └────────┘  └────────┘  └────────┘│
│              ▲                      │
│              │ REST API             │
└──────────────┼──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│      Your GRC Platform (You Manage) │
│  ┌────────────────────────────────┐ │
│  │   Your UI / Dashboard          │ │
│  │  - Customer-facing features    │ │
│  │  - Branded experience          │ │
│  │  - Your differentiation        │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### Integration Options

- **REST API** – Most common, easiest to integrate
- **Webhook subscriptions** – Get notified of new regulations/changes
- **Batch export** – Periodic data dumps for offline processing
- **Embedded graph queries** – Direct Neo4j access for power users

---

## Competitive Differentiation

With RegEngine as your backbone, you can:

- **Expand faster** – New jurisdictions in weeks, not years
- **Go deeper** – Obligation-level granularity (not just document summaries)
- **Prove provenance** – Every insight linked to source regulation
- **Reduce costs** – No infrastructure to maintain

Without RegEngine:
- **Slower expansion** – Build ingestion for each new jurisdiction
- **Shallow coverage** – Document-level only (no NLP extraction)
- **No lineage** – Can't trace obligations back to source
- **High OpEx** – Ongoing maintenance of ingestion pipelines

---

## Pricing (OEM Licensing)

We structure pricing based on:

1. **Number of jurisdictions** you need
2. **Volume of API calls** (or fixed unlimited tier)
3. **Support level** (standard vs. priority)
4. **Revenue share vs. fixed fee**

**Typical range**: $50k-$200k/year for mid-market vendors, custom pricing for enterprise

**Volume discounts available** for multi-year commitments

---

## Getting Started

### Step 1: Technical Evaluation (Week 1-2)

- Sandbox access with demo data
- Integration POC with your platform
- Technical architecture review

### Step 2: Commercial Discussion (Week 3-4)

- Finalize pricing model
- Agree on SLAs and support
- Execute OEM agreement

### Step 3: Go-Live (Week 5-8)

- Production API keys provisioned
- Launch first jurisdiction
- Monitor usage and optimize

---

## Customer Success Stories (Anonymized)

**Mid-Market GRC Platform** (Europe)
- **Challenge**: Wanted to expand from UK-only to EU-wide coverage
- **Solution**: Licensed RegEngine's EU module
- **Result**: Launched 5 new markets in 6 weeks, won 3 enterprise deals in first quarter

**Compliance Automation Startup** (US)
- **Challenge**: Needed obligation extraction for SEC/FINRA regulations
- **Solution**: Embedded RegEngine's NLP API
- **Result**: Reduced customer onboarding time from 90 days to 14 days

---

## Contact & Next Steps

**Interested in OEM licensing?**

1. **Schedule a technical demo** – See RegEngine's capabilities on your use cases
2. **Review integration guide** – Assess effort required for your stack
3. **Discuss commercial terms** – Find a pricing model that aligns with your business

**Contact**: {SALES_EMAIL} | {WEBSITE_URL}

**Technical documentation**: {API_DOCS_URL}
