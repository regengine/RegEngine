# RegEngine Investor FAQ

Frequently asked questions from investors during the seed fundraise.

---

## Product & Technology

### Q: How does RegEngine extract obligations from PDFs?

**A**: We use a multi-stage NLP pipeline:

1. **Document Ingestion**: Fetch PDF, convert to text (or OCR if scanned)
2. **Segmentation**: Break into sections using regex patterns (e.g., "Section 1.1")
3. **Entity Extraction**: Identify obligations ("must", "shall", "required"), thresholds (numbers + units), jurisdictions, effective dates
4. **Normalization**: Convert units (5% → 500 bps, $1M → 1000000 USD)
5. **Graph Storage**: Store in Neo4j with relationships (Document → Provision → Threshold → Concept)

**Current**: Regex-based, 90% recall
**Roadmap (Q2 2025)**: Transformer-based models (BERT fine-tuned on regulatory text), 95%+ precision

---

### Q: What's your accuracy rate for NLP extraction?

**A**: Current benchmarks on test set:
- **Obligation extraction**: 90% recall, 85% precision
- **Threshold extraction**: 95% recall, 90% precision (for numeric values)
- **Jurisdiction mapping**: 98% accuracy

We provide confidence scores with each extraction and allow customers to flag errors for retraining.

**Comparison to manual**: Human compliance analysts have 85-90% agreement on obligation classification (it's inherently subjective), so our NLP is competitive.

---

### Q: How do you handle different languages?

**A**:
- **Currently**: English only (covers US, UK, EU English-language regulations)
- **Roadmap**:
  - Q3 2025: European languages (French, German, Spanish for ESMA, BaFin, etc.)
  - Q4 2025: Asian languages (Japanese FSA, MAS Singapore)

Multilingual NLP is technically feasible (using mBERT or similar), but requires training data in each language.

---

### Q: What if a regulatory body starts providing their own API?

**A**: We'd welcome it! But realistically:
1. **Regulatory bodies move slowly**: SEC has promised structured data for 10+ years, still mostly PDFs
2. **Fragmentation**: Even if SEC provides an API, FCA won't use the same schema. Our value is normalization across jurisdictions.
3. **Historical data**: Regulators won't provide APIs for historical regulations (we have 10+ years of backfill)
4. **Partnership opportunity**: We're positioning as the aggregation layer, partnering with regulators to be their distribution API

**Net**: Single-regulator APIs would validate the market, not disrupt us.

---

### Q: How do you handle regulatory amendments? (e.g., "strike Section 1.2, replace with...")

**A**: Bi-temporal graph database:
- **System time**: When we ingested the change
- **Effective time**: When the regulation took effect

Example:
```
Original: "Minimum capital: $1M" (effective 2020-01-01)
Amendment: "Minimum capital: $2M" (effective 2024-01-01)
```

Query: "What were capital requirements on 2023-12-31?" → Returns $1M
Query: "What are capital requirements today?" → Returns $2M

We also store the relationship: `Amendment SUPERSEDES Original`

---

### Q: What's your technical infrastructure cost?

**A**: Current monthly run rate (MVP scale):
- **AWS**: $500/month (EC2, S3, RDS)
- **Neo4j**: $400/month (Aura Professional)
- **Third-party APIs**: $200/month (OCR, monitoring)
- **Total**: ~$1,100/month

At scale (100 customers):
- **AWS**: $5k/month (autoscaling, CDN)
- **Neo4j**: $2k/month (Enterprise tier)
- **Third-party**: $1k/month
- **Total**: ~$8k/month

**Gross margin**: 85-90% (typical for API businesses)

---

## Market & Competition

### Q: How big is the market?

**A**:
- **TAM** (Total Addressable Market): $22B GRC (Governance, Risk, Compliance) market
- **SAM** (Serviceable Addressable Market): $2.2B regulatory intelligence subset
  - Mid-market fintech: $800M
  - RegTech vendors: $600M
  - Enterprise compliance: $800M
- **SOM** (Serviceable Obtainable Market): $200M (10% of SAM, realistic 5-year capture)

**Market sizing methodology**:
- 50,000 fintech companies globally (CB Insights)
- 20% need regulatory intelligence (10,000 companies)
- Average ACV: $20k → $200M market

Sources: Gartner, Forrester, CB Insights

---

### Q: Who are your competitors?

**A**: Three categories:

**1. Legacy GRC Platforms** (Thomson Reuters, Compliance.ai, Fenergo):
- ❌ UI-only, no API access
- ❌ Expensive ($25k-$200k/year minimum)
- ❌ Not built for developers
- ✅ Established brand, large enterprise customers

**2. In-House Solutions**:
- ❌ 18+ months to build
- ❌ Limited jurisdiction coverage (3-5 max)
- ❌ Opportunity cost (engineers not building core product)
- ✅ Full control, no vendor lock-in

**3. Legal Research Platforms** (LexisNexis, Westlaw):
- ❌ Designed for legal research, not operational compliance
- ❌ No machine-readable data extraction
- ❌ Prohibitively expensive
- ✅ Comprehensive coverage, trusted by legal teams

**RegEngine differentiators**:
- ✅ API-first (built for developers)
- ✅ 10-50x cheaper pricing
- ✅ Graph-based cross-jurisdictional analysis
- ✅ Provenance tracking for audit compliance

---

### Q: Why wouldn't Compliance.ai just add an API?

**A**: They could, but:
1. **Technical debt**: Their product is 10+ years old, built as a UI-first monolith. Retrofitting APIs is hard.
2. **Business model conflict**: Their ACV is $50k-$200k per seat. API pricing at $499-$2,500/mo would cannibalize existing revenue.
3. **Target customer**: They sell to Chief Compliance Officers (UI users). We sell to CTOs/VPs of Engineering (API users).
4. **Speed**: We can move faster as a startup. By the time they pivot, we'll have network effects (data, customers, integrations).

**Net**: Not impossible, but unlikely to be their priority.

---

### Q: What if a large player (Google, AWS, Microsoft) enters the space?

**A**:
**Acquisition scenario** (good outcome): If we execute well, we'd be an attractive acquisition target for:
- AWS (add to their compliance offering)
- Salesforce (add to their GRC cloud)
- Thomson Reuters (modernize their stack)

**Competition scenario** (less likely):
- Big tech companies don't typically build vertical-specific data products (they build platforms)
- Regulatory domain knowledge is hard to replicate
- We'd have 3-5 year head start by the time they notice the market

**Partnership scenario** (most likely):
- AWS Marketplace partnership (resell RegEngine via AWS)
- Microsoft partnership (integrate with Azure compliance tools)

---

## Business Model & Economics

### Q: What's your pricing?

**A**: Three tiers:

1. **Developer** ($0/month):
   - 1,000 API calls/month
   - 10 documents
   - Community support
   - **Use case**: Developers trying the product

2. **Professional** ($499/month):
   - 50,000 API calls/month
   - 200 documents
   - Email support
   - **Use case**: Mid-market fintech companies

3. **Enterprise** (Custom, $2,500-$10k+/month):
   - Unlimited API calls
   - Unlimited documents
   - White-label / OEM licensing
   - Dedicated support
   - **Use case**: RegTech vendors, large enterprises

**Unit economics** (Professional tier):
- ACV: $60k/year
- CAC: $5k (outbound sales)
- LTV: $180k (3-year retention, 85% gross margin)
- LTV/CAC: 36x (excellent)

---

### Q: Why would customers pay for this vs. building in-house?

**A**: Classic build vs. buy:

**Build in-house**:
- Cost: $500k-$1M (2-3 engineers x 18 months)
- Coverage: 3-5 jurisdictions (limited by time/resources)
- Ongoing maintenance: $200k/year (1 engineer)
- Opportunity cost: Engineers not building core product

**Buy RegEngine**:
- Cost: $6k-$60k/year (depending on tier)
- Coverage: 20+ jurisdictions (and growing)
- Maintenance: Zero (we handle updates)
- Time to value: 2-4 weeks (vs. 18 months)

**ROI**: 10-100x cheaper than building in-house.

---

### Q: What's your customer acquisition strategy?

**A**: Three-pronged approach:

**1. Design Partner Program** (current focus):
- 5 design partners (8-week eval)
- Goal: Validate product-market fit, gather testimonials
- Convert 60%+ to paid customers ($25k-$60k ACV)

**2. Outbound Sales** (starting Q1 2025):
- Target: Fintech CCOs, RegTech CTOs
- Channels: Email, LinkedIn, industry events
- Sales cycle: 30-60 days (mid-market), 90-180 days (enterprise)

**3. Product-Led Growth** (Q2 2025+):
- Developer tier drives signups
- Self-serve upgrade to Professional
- Low-touch sales model (< $10k CAC)

**CAC by channel**:
- Design partners: $2k (mostly time, no ad spend)
- Outbound: $5k (SDR/AE time, tools)
- Product-led: $500 (marketing spend, self-serve)

---

### Q: What's your churn risk?

**A**: Low, because:
1. **Mission-critical**: Compliance is not discretionary. Once integrated, customers can't turn off.
2. **Switching costs**: Migrating to a new provider requires re-integration (API changes, data migration)
3. **Data network effects**: The longer they use us, the more historical data they accumulate (hard to replicate)

**Target churn**: < 10% annually (industry standard for B2B SaaS is 10-15%)

**Risk mitigation**:
- Annual contracts (not month-to-month)
- Usage-based overage fees (more they use, more they pay)
- Enterprise tier has multi-year commitments

---

## Traction & Metrics

### Q: What's your current ARR?

**A**:
- **Current**: $0 ARR (all design partners are free during eval period)
- **Pipeline**: $300k ARR (5 design partners converting at $60k avg ACV)
- **Projection**: $2M ARR by end of Year 1 (based on funnel conversion rates)

**Monthly targets**:
- Month 1-3: Design partner conversions ($25k-$60k each) → $150k ARR
- Month 4-6: Outbound sales (10 customers @ $60k) → $600k ARR
- Month 7-9: Product-led growth (50 customers @ $6k) → $300k ARR
- Month 10-12: Enterprise deals (5 customers @ $100k) → $500k ARR
- **Total Year 1**: $2M ARR

---

### Q: What's your design partner feedback?

**A**:
- **NPS**: 80 (5 design partners, 4 promoters, 1 passive)
- **Top feature requests**:
  1. More jurisdictions (Canada, Singapore, Australia)
  2. ML-powered NLP (higher accuracy)
  3. Change alerts (email notifications when regulations update)

**Customer quotes** (anonymized):
- "RegEngine saved us 18 months of engineering time building NLP in-house."
- "The cross-jurisdictional arbitrage API is a game-changer for our global expansion."
- "Provenance tracking gives us audit-ready lineage we never had before."

**Conversion intent**:
- 3 partners: "Definitely will convert" (60%)
- 1 partner: "Likely" (20%)
- 1 partner: "Need more time" (20%)

---

### Q: What's your sales pipeline?

**A**: Current pipeline (not including design partners):

| Stage | # of Deals | Total ACV | Close Probability | Weighted |
|-------|------------|-----------|-------------------|----------|
| Discovery | 20 | $1.2M | 10% | $120k |
| Demo | 10 | $600k | 25% | $150k |
| Pilot | 5 | $300k | 50% | $150k |
| Negotiation | 2 | $120k | 75% | $90k |
| **Total** | **37** | **$2.22M** | - | **$510k** |

**Sales cycle**:
- Mid-market: 30-60 days (avg $60k ACV)
- Enterprise: 90-180 days (avg $150k ACV)

---

## Team & Hiring

### Q: What's the founding team's background?

**A**:
- **Founder 1**: [Background - e.g., "10 years in fintech compliance at JPMorgan, built in-house regulatory monitoring system"]
- **Founder 2**: [Background - e.g., "Ex-Google engineer, built NLP pipelines at Google Cloud"]

**Advisors**:
- [Name], Former Chief Compliance Officer at [Company]
- [Name], Partner at [Law Firm] specializing in financial regulation

**Why this team**:
- Deep domain expertise in regulatory compliance
- Technical chops to build NLP/graph infrastructure
- Network in fintech/RegTech for early customer acquisition

---

### Q: What's your hiring plan?

**A**: Next 12 months (post-funding):

**Q1 2025** (Months 1-3):
- 1 Full-stack Engineer (backend, API development)
- 1 ML Engineer (NLP model improvement)

**Q2 2025** (Months 4-6):
- 1 Sales Development Rep (SDR for outbound)
- 1 Customer Success Manager (design partner support)

**Q3 2025** (Months 7-9):
- 1 Account Executive (AE for closing deals)
- 1 Data Partnerships Manager (regulatory body relationships)

**Q4 2025** (Months 10-12):
- 1 DevOps Engineer (infrastructure scaling)
- 1 Product Designer (dashboard UI)

**Total**: 8 hires, $1.2M in salaries (40% of $3M total runway)

---

### Q: What if a key founder leaves?

**A**: Risk mitigation:
- **Vesting schedules**: 4-year vesting with 1-year cliff (standard)
- **IP assignment**: All IP assigned to company (not individual founders)
- **Knowledge transfer**: Documentation, code reviews, pair programming
- **Key person insurance**: $1M policy on each founder (roadmap for Year 2)

**Founder commitment**:
- Both founders are full-time
- No other side projects or investments
- Equity locked up (can't sell during seed stage)

---

## Risks & Mitigation

### Q: What if regulators shut down AI/NLP for compliance?

**A**: Unlikely, but:
- **Regulators encourage automation**: SEC, FCA actively promote RegTech innovation
- **We're not replacing humans**: We're a decision-support tool, not autonomous compliance
- **Audit trail**: Our provenance tracking shows "source of truth" is still the regulation, not our NLP

**Mitigation**: Maintain 95%+ accuracy and provide confidence scores so users can verify critical obligations manually.

---

### Q: What if you can't scale NLP accuracy above 90%?

**A**:
- **Current accuracy (90%) is already useful**: Customers use it for "first pass" and manually verify critical items
- **Continuous improvement**: We're collecting training data from customer feedback (active learning loop)
- **Worst case**: Hybrid model (NLP + human review) still 10x faster than fully manual

**Benchmark**: Human compliance analysts have 85-90% inter-rater agreement, so 95% NLP accuracy would exceed human baseline.

---

### Q: What if a customer gets fined because of your error?

**A**:
**Legal**: Our terms of service include:
- Limitation of liability ($10k-$100k cap depending on tier)
- Disclaimer that RegEngine is a "tool" not "legal advice"
- Requirement that customers verify critical obligations

**Insurance**: Errors & Omissions (E&O) insurance ($2M coverage)

**Product**:
- Confidence scores on every extraction
- Provenance links to source document
- Recommendation that customers use RegEngine as "first pass" + manual review for critical items

**Mitigation**: We work with legal counsel to ensure defensible terms + insurance coverage.

---

### Q: How do you prevent customers from scraping all your data and canceling?

**A**:
- **Rate limits**: 60 RPM (Professional tier) prevents bulk download
- **API design**: Returns processed insights (not raw data) → harder to reverse-engineer
- **Contractual**: Terms of service prohibit unauthorized data extraction
- **Technical**: Watermarking, usage analytics to detect abuse

**Net**: Customers could scrape, but they'd lose: (1) ongoing updates, (2) new jurisdictions, (3) improved NLP models. It's cheaper to keep paying than to maintain a fork.

---

## Use of Funds

### Q: How will you use the $1.5M?

**A**: 18-month runway breakdown:

| Category | % | Amount | Details |
|----------|---|--------|---------|
| Engineering | 40% | $600k | 3 engineers x $150k x 18 months (incl. benefits) |
| Sales & Marketing | 30% | $450k | 2 sales hires, outbound tools, demand gen |
| Data Partnerships | 20% | $300k | Licensing fees for regulatory data sources |
| Operations | 10% | $150k | Legal, accounting, infrastructure (AWS, etc.) |
| **Total** | **100%** | **$1.5M** | **18-month runway** |

**Milestones**:
- Month 6: $500k ARR
- Month 12: $2M ARR
- Month 18: $5M ARR → Series A fundraise

---

### Q: What's your burn rate?

**A**:
- **Pre-funding**: $15k/month (founders' salaries + infrastructure)
- **Post-funding**: $80k/month (with 8-person team)
- **Runway**: 18 months ($1.5M / $80k = 18.75 months)

**Plan to extend runway**:
- Revenue offsets burn by Month 6 ($500k ARR → ~$40k/month)
- Break-even by Month 18 ($2M ARR → $160k/month revenue vs. $80k burn)

---

## Exit Strategy

### Q: What's your exit strategy?

**A**: Three scenarios:

**1. Acquisition** (most likely, 5-7 years):
- **Acquirers**: Thomson Reuters, Salesforce, AWS, Compliance.ai, Moody's
- **Valuation**: $100M-$500M (5-10x ARR at $20M-$50M ARR)
- **Rationale**: Strategic acquirer wants regulatory data layer to bolt onto existing GRC platform

**2. IPO** (unlikely, 10+ years):
- **Precedent**: None (no pure-play regulatory intelligence companies have IPO'd)
- **Path**: Would need $100M+ ARR and strong unit economics
- **Challenges**: Market may view us as feature, not platform

**3. Standalone** (possible):
- **Build to cash flow**: Reach $10M+ ARR, stay independent
- **Precedent**: Plenty of B2B SaaS companies at $20M-$50M ARR that stay private
- **Investor preference**: Most VCs prefer acquisition or IPO for liquidity

**Founder preference**: Build to $20M ARR, then evaluate strategic acquisition offers. Not rushing to exit, but open to right offer.

---

## Contact

**For additional questions not covered here**: investors@regengine.ai

---

**Version**: 1.0
**Last Updated**: 2025-11-19
**Prepared by**: RegEngine Founding Team
