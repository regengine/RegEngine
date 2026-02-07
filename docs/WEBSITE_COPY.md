# RegEngine Website Copy

Complete website copy for marketing pages, product pages, and landing pages.

---

## Homepage

### Hero Section

**Headline (H1)**:
# Automate Regulatory Monitoring with Machine-Readable Regulation

**Subheadline (H2)**:
RegEngine converts regulatory PDFs into structured, queryable data. Extract obligations, detect changes, and analyze cross-jurisdictional requirements—all via API.

**Primary CTA**: [Start Free Trial →]
**Secondary CTA**: [Schedule Demo]
**Tertiary CTA**: [View API Docs]

**Hero Image/Animation**:
Visual showing:
```
PDF Document → RegEngine API → JSON Response
[Regulation graphic] → [⚙️ Process] → [Code snippet]
```

---

### Problem Section

**Headline**:
## Compliance Teams Are Drowning in Regulatory PDFs

**Body**:
Financial institutions, fintech companies, and RegTech vendors face an impossible challenge:

- 📄 **50,000+ pages** of regulations published annually
- 🌍 **200+ regulatory bodies** globally
- ⏰ **40 hours/week** spent manually tracking changes
- 💸 **$500k+ penalties** for missing regulatory updates

Manual tracking doesn't scale. Legacy GRC tools are expensive and UI-only. Legal research platforms weren't built for automation.

**You need machine-readable regulation.**

---

### Solution Section

**Headline**:
## Introducing RegEngine: The Regulatory Intelligence API

**Columns (3-column layout)**:

#### 1️⃣ Ingest Any Source
Automatically fetch regulations from SEC, FCA, ESMA, and 20+ other regulators. We handle PDFs, HTML, and structured data.

#### 2️⃣ Extract Obligations
Our NLP engine identifies obligations, thresholds, dates, and jurisdictions—with provenance linking every fact back to the source document.

#### 3️⃣ Query via API
REST API with endpoints for arbitrage detection, gap analysis, and regulatory lineage. Integrate with your compliance systems in minutes.

**Visual**: Architectural diagram showing data flow

---

### Features Section

**Headline**:
## Built for Developers, Designed for Compliance

**Feature Grid (2x3 layout)**:

### 🔗 Graph-Based Intelligence
Map relationships across jurisdictions. Identify threshold differences and regulatory overlaps automatically.

### 📍 Audit-Ready Provenance
Every extracted obligation includes source URL, document offset, page number, and SHA-256 hash.

### 🌍 Cross-Jurisdictional Analysis
Compare capital requirements in US vs. EU. Detect policy gaps. Optimize licensing strategy.

### ⚡ Real-Time Change Detection
Get notified within 24 hours when regulations change. Never miss a compliance deadline.

### 🔐 Enterprise-Ready
API key auth, rate limiting, role-based access control. Self-host or use our cloud. SOC 2 certified (roadmap).

### 📊 Queryable History
Bi-temporal graph database tracks transaction time and valid time. Ask: "What were the rules on June 1, 2023?"

---

### Use Cases Section

**Headline**:
## Who Uses RegEngine?

**Tabs or Cards**:

### Fintech Companies
**Challenge**: Expanding into 10 new markets requires understanding capital requirements, licensing rules, and AML regulations.

**Solution**: Query RegEngine API for jurisdiction-specific requirements. Compare thresholds across markets.

**Result**: Reduce time-to-market from 6 months to 6 weeks.

---

### RegTech Vendors
**Challenge**: Building regulatory data infrastructure requires 18 months and $1M+ in engineering costs.

**Solution**: Embed RegEngine as your regulatory data layer. Focus on UX, not data engineering.

**Result**: Launch your product 12 months faster. Offer better coverage than competitors.

---

### Enterprise Compliance Teams
**Challenge**: Manually tracking 30+ jurisdictions doesn't scale. Missed updates lead to penalties.

**Solution**: Automated monitoring + change alerts. Graph-based gap analysis.

**Result**: 60% reduction in compliance FTEs. Zero missed regulatory updates.

---

### Social Proof Section

**Headline**:
## Trusted by Compliance Teams at

[Logo Grid]
- [Company A] (with permission)
- [Company B]
- [Company C]
- [Design Partner logos]

*(If pre-revenue, use "Designed for teams at" and show target company types)*

---

### Pricing Teaser

**Headline**:
## Transparent, Usage-Based Pricing

**Cards (3 tiers)**:

#### Developer
**$0/month**
- 1,000 API calls/month
- 10 documents
- 3 jurisdictions
- Community support

[Get Started Free →]

---

#### Professional
**$499/month**
- 50,000 API calls/month
- 200 documents
- 20 jurisdictions
- Email support, 99% SLA

[Start 14-Day Trial →]

---

#### Enterprise
**Custom**
- Unlimited API calls
- Global coverage (100+ jurisdictions)
- Priority support
- On-premise deployment

[Contact Sales →]

**Link**: [View Full Pricing →]

---

### CTA Section

**Headline**:
## Ready to Automate Regulatory Monitoring?

**Subheadline**:
Join the fintech companies and RegTech vendors building on RegEngine.

**Primary CTA**: [Start Free Trial →]
**Secondary CTA**: [Schedule Demo]

---

### Footer

**Company**:
- About Us
- Careers (We're hiring!)
- Contact

**Product**:
- How It Works
- Pricing
- API Documentation
- Status Page

**Resources**:
- Blog
- Case Studies
- Developer Guides
- Changelog

**Legal**:
- Privacy Policy
- Terms of Service
- Security

**Social**:
- Twitter
- LinkedIn
- GitHub

---

## Product Page: API Documentation

### Hero

**Headline**:
# API Documentation: Regulatory Intelligence for Developers

**Subheadline**:
RESTful API with OpenAPI 3.0 spec. Authenticate with API keys. Get started in 5 minutes.

**Code Example**:
```bash
curl "https://api.regengine.ai/opportunities/arbitrage?j1=US&j2=EU&concept=capital" \
  -H "X-RegEngine-API-Key: your-api-key"
```

**Response**:
```json
{
  "items": [
    {
      "concept": "minimum capital",
      "v1": 1000000,
      "v2": 750000,
      "unit": "USD",
      "citation_1": {
        "doc_id": "sec-capital-req-2024-001",
        "source_url": "https://www.sec.gov/...",
        "start": 450,
        "end": 520
      }
    }
  ]
}
```

**CTA**: [View Full API Docs →] [Get API Key →]

---

### Endpoints Overview

**Ingestion API**:
- `POST /ingest/url` - Ingest a regulatory document from URL

**Opportunity API**:
- `GET /opportunities/arbitrage` - Find threshold differences across jurisdictions
- `GET /opportunities/gaps` - Detect concepts present in one jurisdiction but not another

**Admin API**:
- `POST /admin/keys` - Create API keys (requires admin auth)
- `GET /admin/keys` - List all API keys

**Full documentation**: [api.regengine.ai/docs]

---

## Pricing Page

*(Use content from PRICING.md, formatted for web)*

**Headline**:
# Pricing Built for Growth

**Subheadline**:
Start free. Scale to millions of API calls. No hidden enterprise fees.

*(Display pricing tiers with feature comparison table)*

**FAQ Section**:
- What counts as an API call?
- What happens if I exceed my limit?
- Can I self-host on the Professional tier?
- Do you offer discounts for nonprofits?

---

## About Page

**Headline**:
# We're Building the Regulatory Intelligence Layer for the World

**Mission**:
RegEngine exists to make regulatory compliance automatable. We believe every compliance system should have access to machine-readable regulation, not just expensive enterprise platforms.

**Team**:
*(Add team photos and bios)*

**Careers**:
We're hiring! Join us in building the future of regulatory intelligence.

[View Open Roles →]

---

## Blog Post Ideas (Content Marketing)

### Technical Deep Dives
1. **"How We Built a Graph Database for Regulatory Lineage"**
2. **"From Regex to Transformers: Improving NLP Accuracy by 40%"**
3. **"Content-Addressed Storage: Why We Hash Every Regulation"**

### Use Case Showcases
4. **"How Fintech Companies Use RegEngine to Enter New Markets 10x Faster"**
5. **"RegTech OEM Case Study: Powering Compliance Management with Our API"**
6. **"Detecting $500k in Capital Requirement Arbitrage Opportunities"**

### Thought Leadership
7. **"The Case for API-First Regulatory Intelligence"**
8. **"Why Legacy GRC Tools Will Lose to Developer-First Platforms"**
9. **"MiCA, DORA, AI Act: Why 2025 is the Year of RegTech Automation"**

---

## Landing Pages (for Paid Ads)

### Landing Page: Fintech
**Headline**: Automate Global Compliance for Your Fintech

**Pain Points**:
- Launching in EU but unsure of MiFID requirements?
- Wasting weeks decoding capital adequacy rules?
- Compliance team of 1 tracking 10 jurisdictions?

**Solution**: RegEngine gives you machine-readable regulations via API.

**CTA**: [Start Free Trial →]

---

### Landing Page: RegTech Vendors
**Headline**: Embed Regulatory Intelligence in Your Product

**Pain Points**:
- Building regulatory data infrastructure from scratch?
- Spending $1M+ on engineering instead of your core product?
- Can't compete with incumbents on data coverage?

**Solution**: White-label RegEngine as your regulatory data layer.

**CTA**: [Schedule OEM Discussion →]

---

### Landing Page: Enterprise Compliance
**Headline**: Centralize Regulatory Monitoring Across 30+ Jurisdictions

**Pain Points**:
- Compliance team overwhelmed by manual tracking?
- Board demanding proof of regulatory coverage?
- Worried about missing critical updates?

**Solution**: Automated monitoring + audit-ready provenance.

**CTA**: [Request Enterprise Demo →]

---

## Email Campaigns

### Email 1: Welcome (after free signup)

**Subject**: Welcome to RegEngine! Here's how to get started

**Body**:
Hi [Name],

Thanks for signing up for RegEngine!

You now have access to:
- 1,000 free API calls/month
- Demo dataset (US, EU, UK regulations)
- Full API documentation

**Get started in 3 steps**:
1. [Generate your API key](link)
2. [Try the quick-start guide](link)
3. [Run your first query](link)

Need help? Reply to this email or join our [Slack community](link).

Best,
[Founder Name]

---

### Email 2: Upgrade Prompt (30 days after signup)

**Subject**: You've used 80% of your free API calls—ready to upgrade?

**Body**:
Hi [Name],

You've made 800 API calls this month (80% of your free tier).

To avoid hitting the limit, consider upgrading to **Professional** ($499/month):
- 50,000 API calls/month
- 20 jurisdictions
- Email support + 99% SLA

[Upgrade Now →]

Questions? Let's chat: [Schedule a call](link)

---

### Email 3: Onboarding (for paid customers)

**Subject**: Your RegEngine account is live! Next steps

**Body**:
Hi [Name],

Welcome to RegEngine Professional! 🎉

Your account includes:
- 50,000 API calls/month
- 20 jurisdictions
- Dedicated support: [support@regengine.ai](mailto:support@regengine.ai)

**Recommended next steps**:
1. [Upload your first regulation](link)
2. [Set up change alerts](link)
3. [Schedule onboarding call with our team](link)

We're here to help you succeed.

Best,
[Customer Success Team]

---

## Ads Copy (Google/LinkedIn)

### Google Search Ad
**Headline 1**: Automate Regulatory Monitoring
**Headline 2**: Machine-Readable Regulation API
**Headline 3**: Start Free | No Credit Card

**Description**:
RegEngine converts regulatory PDFs into queryable JSON. Extract obligations, detect changes, and analyze cross-jurisdictional requirements via API. Try free.

**CTA**: Start Free Trial

---

### LinkedIn Sponsored Content
**Headline**: Compliance Teams: Stop Manually Tracking Regulations

**Body**:
RegEngine automates regulatory monitoring with an API-first platform. Extract obligations, detect changes, and analyze jurisdictions—all via REST API.

**CTA**: Learn More

---

## SEO-Optimized Content

### Target Keywords
- "regulatory intelligence API"
- "automated compliance monitoring"
- "machine-readable regulation"
- "regulatory change detection"
- "cross-jurisdictional compliance"

### Meta Tags (Homepage)
**Title Tag**: RegEngine | Regulatory Intelligence API for Compliance Automation
**Meta Description**: Automate regulatory monitoring with machine-readable regulation. Extract obligations, detect changes, and analyze jurisdictions via API. Start free.

---

## Call-to-Action Variations

**Primary CTAs**:
- Start Free Trial
- Schedule Demo
- Get API Key
- Contact Sales

**Secondary CTAs**:
- View Pricing
- Read Documentation
- See Use Cases
- Watch Video Demo

**Urgency CTAs**:
- Start 14-Day Free Trial (No Credit Card)
- Book a Demo Today
- Get Started in 5 Minutes

---

**End of Website Copy**

**Next Steps**:
1. Design mockups using this copy
2. Build website (Next.js, Tailwind, Vercel)
3. Integrate with Stripe for billing
4. Launch marketing site + self-service signup
