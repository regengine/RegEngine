# RegEngine Pricing & Packaging

## Pricing Philosophy

RegEngine uses **transparent, usage-based pricing** aligned with customer value:
- Pay for what you use
- No hidden enterprise premiums
- Scale from prototype to production seamlessly
- Self-service signup for Developer and Professional tiers

---

## Pricing Tiers

### 🔧 Developer
**$0/month**

Perfect for evaluation, prototyping, and small-scale use.

**Included**:
- 1,000 API calls/month
- 10 documents ingested/month
- 3 jurisdictions
- Community support (GitHub Discussions)
- Self-hosted OR cloud deployment
- Basic API documentation

**Limits**:
- 100 requests/hour rate limit
- 30-day data retention
- No SLA

**Best for**: Individual developers, students, proof-of-concept projects

**CTA**: [Get Started Free →]

---

### 💼 Professional
**$499/month**

For growing compliance teams and small RegTech vendors.

**Everything in Developer, plus**:
- 50,000 API calls/month
- 200 documents ingested/month
- 20 jurisdictions
- Email support (48-hour response)
- 99% uptime SLA
- 1-year data retention
- API key management (10 keys)
- Slack/email change notifications

**Overages**:
- $0.01 per additional API call
- $2.50 per additional document

**Best for**: Mid-market fintech, compliance teams (10–100 employees), solo RegTech vendors

**CTA**: [Start 14-Day Trial →]

---

### 🏢 Enterprise
**Custom pricing** (starting at $2,500/month)

For large institutions, multi-national firms, and RegTech platforms.

**Everything in Professional, plus**:
- Unlimited API calls
- Unlimited documents
- Global jurisdiction coverage (100+)
- Priority support (4-hour response, dedicated Slack channel)
- 99.9% uptime SLA
- Unlimited data retention
- Unlimited API keys
- Custom ingestion sources
- On-premise deployment option
- SOC 2 compliance
- Custom SLAs available

**Custom Add-Ons**:
- White-label API ($5k/month)
- Dedicated infrastructure ($10k/month)
- Professional services (custom integrations)
- Training and onboarding

**Best for**: Large banks, insurance companies, RegTech platforms (OEM licensing), law firms

**CTA**: [Contact Sales →]

---

## OEM / Platform Licensing
**Custom pricing**

For RegTech vendors who want to embed RegEngine as their regulatory data layer.

**Includes**:
- White-label API
- Custom branding
- Revenue share or flat licensing fee
- Dedicated account manager
- Co-marketing opportunities
- Joint roadmap planning

**Starting at**: $50k/year + $0.005/API call

**Example**: You charge your customers $X/month for compliance management. RegEngine powers the underlying regulatory intelligence. You pay us a revenue share or flat fee.

**CTA**: [Schedule OEM Discussion →]

---

## Detailed Pricing Breakdown

### API Call Pricing

| Tier | Included Calls | Overage Rate | Effective CPM* |
|------|----------------|--------------|----------------|
| Developer | 1,000 | N/A (hard cap) | Free |
| Professional | 50,000 | $0.01/call | $10/1k calls |
| Enterprise | Unlimited | Included | ~$0.005/call |

*CPM = Cost Per Mille (1,000 calls)

### Document Ingestion Pricing

| Tier | Included Docs | Overage Rate | Per-Doc Cost |
|------|---------------|--------------|--------------|
| Developer | 10 | N/A (hard cap) | Free |
| Professional | 200 | $2.50/doc | $2.50 |
| Enterprise | Unlimited | Included | ~$0.25 |

### Jurisdiction Coverage

| Tier | Jurisdictions | Additional Coverage |
|------|---------------|---------------------|
| Developer | 3 (US, EU, UK) | Not available |
| Professional | 20 (major markets) | +$100/month per jurisdiction |
| Enterprise | 100+ (global) | Custom sources available |

---

## Pricing Examples

### Example 1: Mid-Market Fintech (50 employees)
**Use case**: Monitoring US, EU, UK regulations for lending compliance

**Needs**:
- 25,000 API calls/month (policy validation checks)
- 50 new documents/month (regulatory updates)
- 3 jurisdictions

**Recommended tier**: Professional

**Monthly cost**: $499/month

**ROI**: Replaces 1 FTE ($8k/month) → saves $7.5k/month

---

### Example 2: RegTech Vendor (B2B SaaS)
**Use case**: Embedding regulatory intelligence in compliance management platform

**Needs**:
- 500,000 API calls/month (across 100 customers)
- 1,000 documents/month
- 50 jurisdictions

**Recommended tier**: Enterprise or OEM

**Monthly cost**: $5,000–$10,000/month (negotiated)

**Revenue**: Charges $50k/year per customer → 100 customers = $5M ARR

**Gross margin**: 97% (RegEngine costs are minimal vs. revenue)

---

### Example 3: Enterprise Bank
**Use case**: Global regulatory monitoring across 30 countries

**Needs**:
- 2M API calls/month (integrated into risk systems)
- 5,000 documents/month
- 100 jurisdictions
- On-premise deployment
- SOC 2 compliance

**Recommended tier**: Enterprise + On-Premise

**Monthly cost**: $15,000–$25,000/month

**ROI**: Replaces 5 FTEs ($50k/month) + avoids $500k regulatory penalty → ROI in <1 month

---

## Add-On Services

### Professional Services
**$250/hour** or **packaged engagements**

- Custom ingestion pipeline development
- Jurisdiction-specific tuning
- Integration with existing GRC tools
- Data migration assistance
- Training and workshops

**Typical engagement**: $10k–$50k for custom integrations

---

### Managed Services
**Starting at $5k/month**

- Managed cloud deployment
- Monitoring and alerting
- Performance optimization
- Quarterly business reviews
- Proactive capacity planning

---

## Volume Discounts

**Annual prepay discounts**:
- 12-month commitment: 10% off
- 24-month commitment: 20% off
- 36-month commitment: 30% off

**Volume discounts** (Enterprise tier only):
- >5M API calls/month: 15% off
- >10M API calls/month: 25% off
- >50M API calls/month: Custom pricing

---

## Free Tier (Alternative to Developer)

If we want to maximize adoption, consider a permanent free tier:

**RegEngine Free**
- 500 API calls/month (forever)
- 5 documents/month
- 1 jurisdiction (US only)
- Community support
- Public roadmap visibility

**Goal**: Drive developer adoption, create grassroots demand within enterprises

---

## Pricing FAQs

### What counts as an API call?
Each request to any RegEngine endpoint (ingestion, opportunity, gaps, arbitrage) counts as one API call. Health checks and metrics endpoints do not count.

### What counts as a document?
A document is a single regulatory file (PDF, HTML, JSON) ingested via the ingestion API. Updates to the same document count as new documents if the content changes.

### Can I switch tiers mid-month?
Yes. Upgrades are prorated and take effect immediately. Downgrades take effect at the next billing cycle.

### What happens if I exceed my limits?
**Developer**: Hard cap—API returns 429 error.
**Professional**: Overages are charged at the rates listed above.
**Enterprise**: No limits.

### Do you offer discounts for nonprofits/academia?
Yes. 50% discount on Professional tier for qualifying organizations. Contact us for verification.

### Can I self-host on the Professional tier?
Yes, but you're responsible for infrastructure costs. We provide Docker Compose and Kubernetes manifests.

### What payment methods do you accept?
Credit card (Stripe), ACH, wire transfer (Enterprise only).

### Is there a setup fee?
No setup fee for Developer or Professional. Enterprise may include one-time onboarding fee ($5k–$10k) for custom deployments.

---

## Competitive Pricing Comparison

| Provider | Entry Price | Mid-Tier Price | API Access | Self-Hosted |
|----------|-------------|----------------|------------|-------------|
| **RegEngine** | $0 | $499/mo | ✅ Full | ✅ Yes |
| Compliance.ai | $25k/year | $100k/year | ❌ No | ❌ No |
| Thomson Reuters | Custom ($$$$) | $200k+/year | ⚠️ Limited | ❌ No |
| LexisNexis | Custom ($$$$) | $150k+/year | ❌ No | ❌ No |
| Internal Build | - | $500k+ (dev cost) | ✅ Yes | ✅ Yes |

**RegEngine advantage**: 10-50x cheaper than incumbents, with better API access.

---

## Pricing Strategy Rationale

### Why usage-based?
- **Aligns with value**: You pay based on how much you use, not arbitrary "seats"
- **Low barrier to entry**: Free tier enables experimentation
- **Scales with customer**: As they grow, we grow
- **Predictable**: Customers can forecast costs based on usage

### Why not per-seat pricing?
- Regulatory data doesn't scale with seats—a 10-person team might query 1M times/month
- Per-API-call pricing is more defensible and transparent

### Why offer a free tier?
- **Developer adoption**: Free tier creates bottom-up demand in enterprises
- **Land-and-expand**: Free users convert to paid when they go to production
- **Marketing**: Developers blog/tweet about tools they can try for free

---

## Sales Process

### Developer → Self-Service
- Sign up online
- Credit card required (after free tier)
- No sales call needed

### Professional → Self-Service or Sales-Assisted
- Self-service available
- Optional sales call for Enterprise evaluation

### Enterprise → Sales-Led
- Required discovery call
- Custom SOW and pricing
- Procurement process (30–90 days typical)

---

## Next Steps

1. **Create pricing page** on website using this framework
2. **Set up Stripe integration** for self-service billing
3. **Build quote calculator** for sales team
4. **Create TCO comparison tool** (vs. manual compliance or competitors)
5. **Test pricing** with first 10 design partners
