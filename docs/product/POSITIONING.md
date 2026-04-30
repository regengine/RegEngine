# RegEngine: Product Positioning & Messaging

> Status: FSMA-first positioning update, April 30, 2026. Older regulatory-intelligence language below is retained for historical context, but the current commercial wedge is food traceability under FSMA 204.

## Positioning Statement

**For** food safety, supplier onboarding, and compliance operations teams at food manufacturers, distributors, retailers, and logistics partners **who need** to meet FSMA 204 traceability requirements without relying on spreadsheets and email,

**RegEngine** is a traceability data operating system **that** preflights messy supplier data, scores readiness, routes fixes, and gates only validated records into tenant-scoped FSMA evidence.

**Unlike** legacy food safety platforms that are UI-first, services-heavy, and slow to deploy,

**RegEngine** combines an API-first ingestion hub with deterministic FSMA rules, commit gates, tenant isolation, and audit-ready export paths.

Current proof point: the Inflow Workbench loop now supports Preflight Mode, Commit Gate, Fix Queue, Scenario Library, and dashboard Readiness Score surfacing for design-partner demos and pilot validation.

---

## Core Value Propositions

### 1. **Automate Regulatory Monitoring**
**Problem**: Compliance teams spend 40+ hours/week manually tracking regulatory updates across multiple jurisdictions.

**Solution**: RegEngine automatically ingests regulations from global sources, detects changes, and alerts you to new obligations.

**Value**: Reduce compliance monitoring headcount by 60%. Ensure zero missed regulatory updates.

---

### 2. **Machine-Readable Regulation**
**Problem**: Regulations are published as PDFs and HTML—unusable for automated systems.

**Solution**: RegEngine converts any regulatory document into structured, queryable data with extracted obligations, thresholds, and metadata.

**Value**: Build compliance automation on top of standardized regulatory data. Integrate directly into your risk management systems.

---

### 3. **Cross-Jurisdictional Intelligence**
**Problem**: Global firms waste resources complying with duplicative requirements or miss arbitrage opportunities.

**Solution**: RegEngine's graph database maps relationships across jurisdictions, identifying threshold differences, gaps, and overlaps.

**Value**: Optimize licensing strategy. Identify competitive advantages. Avoid over-compliance.

---

### 4. **Audit-Ready Lineage**
**Problem**: Auditors and regulators demand proof that policies map to specific regulatory requirements.

**Solution**: Every extracted obligation includes provenance: source URL, document offset, page number, and SHA-256 hash.

**Value**: Pass audits faster. Demonstrate compliance with traceable evidence. Reduce audit prep by 50%.

---

## Target Personas

### Primary: Chief Compliance Officer (Financial Services)
- **Pain**: Overwhelmed by regulatory change velocity
- **Goal**: Automate monitoring, reduce manual processes
- **Budget**: $50k–$250k/year for RegTech tools
- **Decision Criteria**: Accuracy, provenance, coverage

### Secondary: RegTech Product Manager
- **Pain**: Building regulatory data infrastructure from scratch
- **Goal**: Embed regulatory intelligence in their product
- **Budget**: $100k–$500k/year for data/API licensing
- **Decision Criteria**: API quality, documentation, scalability

### Tertiary: Risk Officer (Multi-National Corporation)
- **Pain**: Inconsistent compliance across jurisdictions
- **Goal**: Centralized regulatory view
- **Budget**: $75k–$300k/year
- **Decision Criteria**: Coverage, cross-jurisdiction analysis

---

## Competitive Differentiation

| Feature | RegEngine | Compliance.ai | Thomson Reuters | Internal Tools |
|---------|-----------|---------------|-----------------|----------------|
| **Graph-based lineage** | ✅ | ❌ | ❌ | ❌ |
| **API-first** | ✅ | ❌ | ⚠️ (limited) | ❌ |
| **Cross-jurisdiction arbitrage** | ✅ | ❌ | ❌ | ❌ |
| **Self-hostable** | ✅ | ❌ | ❌ | ✅ |
| **Provenance tracking** | ✅ (SHA-256) | ⚠️ (basic) | ⚠️ (basic) | ❌ |
| **Pricing** | Usage-based | Enterprise-only | $$$$ | Dev cost |

---

## Messaging Framework

### Elevator Pitch (30 seconds)
"RegEngine is an API platform that turns regulatory PDFs into machine-readable data. We automatically extract obligations, thresholds, and requirements from global regulations, map them in a graph database, and provide APIs for compliance automation, gap analysis, and regulatory arbitrage detection."

### Two-Sentence Pitch (Email/LinkedIn)
"RegEngine converts regulatory documents into machine-readable data with queryable obligation extraction and cross-jurisdictional analysis. We provide the regulatory intelligence layer that powers automated compliance."

### Problem-Agitate-Solve (Sales Call Opener)
**Problem**: "You're tracking regulations across 12 jurisdictions manually, using spreadsheets and PDFs, right?"

**Agitate**: "And when a regulation changes, you have 30 days to update internal policies, train staff, and notify the board—while also monitoring 50 other regulatory bodies."

**Solve**: "RegEngine automates this. We ingest regulations from any source, extract every obligation automatically, and alert you to changes within 24 hours. Plus, our graph database shows you exactly how your requirements differ across jurisdictions."

---

## Key Messages by Audience

### For Compliance Teams
- **Headline**: "Automate Regulatory Monitoring. Never Miss an Update."
- **Key Points**:
  - Reduce manual tracking by 60%
  - Automated obligation extraction
  - Real-time change detection
  - Audit-ready provenance

### For RegTech Vendors
- **Headline**: "Embed Regulatory Intelligence in Your Product"
- **Key Points**:
  - REST API with health monitoring
  - Machine-readable regulation
  - OEM licensing available
  - No infrastructure build required

### For Risk Officers
- **Headline**: "Optimize Compliance Across Jurisdictions"
- **Key Points**:
  - Identify regulatory arbitrage opportunities
  - Detect policy gaps automatically
  - Centralized regulatory view
  - Cross-jurisdiction threshold comparison

---

## Verified Capabilities

### Quantified Value
- **Automated** regulatory change detection and obligation extraction
- **SHA-256** cryptographic audit trail — independently verifiable
- **21 FTL categories** with CTE/KDE mapping per 21 CFR Part 1 Subpart S
- **GS1 EPCIS 2.0** export for Walmart/Kroger supplier compliance

### Technical Credibility
- Graph database with bitemporal tracking
- SHA-256 content-addressed storage
- API-first architecture (OpenAPI 3.0)
- Open-source verification script (`verify_chain.py`)
- Row-Level Security (RLS) multi-tenant isolation

### Use Cases
1. **FSMA 204 compliance**: Automated CTE/KDE tracking for food supply chains
2. **Retailer readiness**: GS1 EPCIS 2.0 exports for Walmart/Kroger suppliers
3. **FDA audit response**: 24-hour electronic sortable spreadsheet generation
4. **Supply chain verification**: Cryptographic proof of traceability data integrity

---

## Objection Handling

### "We already use [Competitor]"
**Response**: "Great! Many of our customers use [Competitor] for policy management and use RegEngine for the upstream regulatory intelligence layer. We provide the machine-readable regulation; they handle the downstream workflow. Would you like to see how they integrate?"

### "We can build this internally"
**Response**: "Absolutely, and some of our customers did exactly that. They discovered it took 18 months and 3 engineers just to get basic ingestion working—before tackling NLP, graph databases, and multi-jurisdiction normalization. We've already solved those problems. How quickly do you need this capability?"

### "Regulatory data is free/public"
**Response**: "True—the PDFs are free. But making them machine-readable, extractable, queryable, and provenance-tracked? That's the engineering challenge. You're not paying for the data; you're paying for the infrastructure that makes it usable."

### "This seems expensive"
**Response**: "Let's do the math: If your team spends 40 hours/week on manual regulatory tracking, that's $120k/year in labor cost alone. RegEngine costs [pricing], automating 60% of that work. You're ROI-positive in [X] months."

### "How do we know the extractions are accurate?"
**Response**: "Great question. Every extraction includes provenance—the exact document offset, page number, and source URL. You can verify any obligation in seconds. Plus, we're currently at [X]% precision on obligation extraction, and we continuously improve with customer feedback."

---

## Brand Voice & Tone

- **Professional, not stuffy**: We talk like engineers, not lawyers
- **Transparent**: We're upfront about what works and what's on the roadmap
- **Evidence-based**: We lead with data, not hyperbole
- **Helpful**: We're here to solve problems, not sell enterprise licenses

**Examples**:
- ✅ "Automate regulatory monitoring"
- ❌ "Revolutionary AI-powered compliance transformation"
- ✅ "SHA-256 cryptographic audit trail"
- ❌ "Enterprise-grade world-class platform"

---

## Next Steps for GTM

1. **Website**: Use messaging framework to draft homepage, product pages
2. **Sales deck**: Build pitch deck using positioning + verified capabilities
3. **Outbound**: Create LinkedIn/email templates for each persona
4. **Content**: Blog posts demonstrating arbitrage detection, gap analysis
5. **Pricing page**: Transparent, usage-based pricing (see PRICING.md)
