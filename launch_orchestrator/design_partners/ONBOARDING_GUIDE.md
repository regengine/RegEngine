# RegEngine Design Partner Program - Onboarding Guide

## Welcome to the RegEngine Design Partner Program!

You've been selected to participate in our 8-week design partner evaluation program. This guide will help you get started with RegEngine's regulatory intelligence API platform.

---

## Program Overview

**Duration**: 8 weeks (with option to extend)
**Commitment**: Non-production evaluation use only
**Support**: Dedicated Slack channel + bi-weekly check-ins
**Goal**: Validate product-market fit and gather feedback for production roadmap

---

## What You'll Get

### 1. Sandbox Environment Access
- **Sandbox URL**: `https://sandbox.regengine.ai`
- **API Key**: Will be provided via secure channel (1Password/email)
- **Rate Limits**: 60 requests/minute (adjustable on request)
- **Document Limits**: 1,000 regulatory documents
- **Jurisdictions**: United States (SEC, FINRA), European Union (MiFID II, GDPR), United Kingdom (FCA)

### 2. API Documentation
- **OpenAPI Spec**: https://docs.regengine.ai/openapi.yaml
- **Interactive Docs**: https://docs.regengine.ai (Swagger UI)
- **Code Examples**: Python, Node.js, cURL available at https://docs.regengine.ai/examples

### 3. Technical Support
- **Slack Channel**: #regengine-design-partners (invite sent separately)
- **Response SLA**: < 4 business hours for technical questions
- **Bi-weekly Check-ins**: 30-minute video calls on Wednesdays
- **Emergency Contact**: support@regengine.ai (for critical issues)

---

## Week 1: Getting Started

### Day 1-2: Environment Setup

1. **Verify API Key**
   ```bash
   curl -X GET "https://sandbox.regengine.ai/health" \
     -H "X-RegEngine-API-Key: YOUR_API_KEY"
   ```
   Expected response:
   ```json
   {
     "status": "healthy",
     "version": "1.0.0",
     "services": ["ingestion", "nlp", "graph", "opportunity"]
   }
   ```

2. **Install Client Library** (optional but recommended)
   ```bash
   pip install regengine-sdk  # Python
   # or
   npm install @regengine/sdk  # Node.js
   ```

3. **Review Sample Data**
   - Pre-loaded jurisdictions: US SEC, EU MiFID II, UK FCA
   - Sample regulatory documents: Capital requirements, liquidity rules
   - Example queries provided in `sandbox_queries.sh`

### Day 3-5: First Integration

1. **Ingest Your First Document**
   ```bash
   curl -X POST "https://sandbox.regengine.ai/ingest/url" \
     -H "X-RegEngine-API-Key: YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "url": "https://www.sec.gov/rules/final/example.pdf",
       "jurisdiction": "United States",
       "source_type": "sec_release",
       "effective_date": "2024-01-15"
     }'
   ```

2. **Query Extracted Obligations**
   ```bash
   curl -X GET "https://sandbox.regengine.ai/obligations?jurisdiction=United%20States" \
     -H "X-RegEngine-API-Key: YOUR_API_KEY"
   ```

3. **Explore Graph Relationships**
   ```bash
   curl -X GET "https://sandbox.regengine.ai/graph/relationships?concept=capital_requirements" \
     -H "X-RegEngine-API-Key: YOUR_API_KEY"
   ```

### Day 6-7: Use Case Validation

**Choose one primary use case to validate**:

#### Option A: Regulatory Change Monitoring
- Goal: Get alerted when new regulations affect your business
- Test: Ingest 5-10 recent regulatory updates from your jurisdiction
- Success metric: Can you identify which obligations changed vs. prior version?

#### Option B: Multi-Jurisdiction Comparison
- Goal: Compare how different jurisdictions treat the same concept (e.g., capital requirements)
- Test: Query `/opportunities/arbitrage` endpoint with 2 jurisdictions
- Success metric: Can you identify regulatory differences/gaps?

#### Option C: Compliance Gap Analysis
- Goal: Map your internal controls to regulatory obligations
- Test: Upload 3-5 policy documents, query for coverage gaps
- Success metric: Can you identify which obligations lack controls?

---

## Week 2-3: Integration Development

### Key Endpoints to Integrate

#### 1. Document Ingestion
- **Endpoint**: `POST /ingest/url` or `POST /ingest/upload`
- **Use case**: Automatically ingest new regulations as they're published
- **Integration pattern**: Webhook from regulatory source → RegEngine ingestion

#### 2. Obligation Extraction
- **Endpoint**: `GET /obligations`
- **Filters**: jurisdiction, effective_date, concept, threshold_min/max
- **Use case**: Retrieve machine-readable obligations for your workflows

#### 3. Cross-Jurisdiction Analysis
- **Endpoint**: `GET /opportunities/arbitrage`
- **Parameters**: `j1`, `j2`, `concept`, `rel_delta`
- **Use case**: Identify regulatory differences between jurisdictions

#### 4. Gap Detection
- **Endpoint**: `GET /opportunities/gaps`
- **Parameters**: `jurisdiction`, `current_coverage` (your internal policies)
- **Use case**: Find obligations not covered by your controls

#### 5. Provenance Tracking
- **Endpoint**: `GET /provenance/{obligation_id}`
- **Use case**: Audit trail from obligation back to source document + page number

### Sample Integration Architecture

```
┌─────────────────┐
│ Your Application│
│  (Dashboard)    │
└────────┬────────┘
         │
         │ REST API calls
         ▼
┌─────────────────────────┐
│  RegEngine Sandbox API  │
│  sandbox.regengine.ai   │
└─────────────────────────┘
         │
         │ Pre-loaded data:
         │ - US SEC regulations
         │ - EU MiFID II
         │ - UK FCA rules
         └─────────────────
```

---

## Week 4-5: Feedback & Feature Requests

### Structured Feedback Sessions

**Week 4 Check-in Topics**:
- API usability: Are endpoints intuitive?
- Data quality: Is NLP extraction accurate enough?
- Coverage gaps: Which jurisdictions/concepts are missing?
- Performance: Are response times acceptable?

**Week 5 Check-in Topics**:
- Roadmap prioritization: What features would unlock production use?
- Pricing feedback: Does our proposed pricing model work for you?
- Integration complexity: What tooling/SDKs would help?

### Feature Request Process

1. **Submit via Slack**: Post in #regengine-design-partners
2. **Include**:
   - Use case description
   - Current workaround (if any)
   - Business impact (blocker vs. nice-to-have)
3. **Response SLA**: Within 2 business days with roadmap placement

---

## Week 6-7: Advanced Use Cases

### Multi-Jurisdiction Workflow Example

**Scenario**: You operate in US, UK, and EU. New capital requirements published in US.

```bash
# 1. Ingest new US regulation
curl -X POST "https://sandbox.regengine.ai/ingest/url" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \
  -d '{"url": "https://sec.gov/new-capital-rule.pdf", "jurisdiction": "United States"}'

# 2. Extract obligations
curl -X GET "https://sandbox.regengine.ai/obligations?jurisdiction=United%20States&concept=capital_requirements&since=2024-11-01" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"

# 3. Compare to UK version
curl -X GET "https://sandbox.regengine.ai/opportunities/arbitrage?j1=United%20States&j2=United%20Kingdom&concept=capital_requirements" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"

# 4. Identify gaps in your controls
curl -X POST "https://sandbox.regengine.ai/opportunities/gaps" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \
  -d '{
    "jurisdiction": "United States",
    "current_policies": ["policy-123", "policy-456"]
  }'
```

### Graph Query Example

**Scenario**: Understand all regulations related to "minimum net capital"

```bash
curl -X GET "https://sandbox.regengine.ai/graph/traverse?start_concept=minimum_net_capital&max_depth=2" \
  -H "X-RegEngine-API-Key: YOUR_API_KEY"
```

Response shows:
- Related concepts: liquidity ratio, capital adequacy, risk-weighted assets
- Jurisdictions with similar requirements
- Historical changes to the concept

---

## Week 8: Production Readiness Discussion

### Topics to Cover

1. **Commercial Terms**
   - Transition from design partner to paid customer
   - Pricing tier (Developer / Professional / Enterprise)
   - Volume commitments

2. **Production Infrastructure**
   - Migration from sandbox → production API
   - SLA commitments (99.9% uptime)
   - Security certifications (SOC 2 roadmap)

3. **Feature Roadmap**
   - Which features from your feedback are prioritized?
   - Timeline for missing jurisdictions
   - ML accuracy improvements

4. **Case Study / Reference**
   - Would you be willing to be a public reference customer?
   - Co-authored blog post or case study?

---

## Technical Reference

### Authentication

All API requests require the `X-RegEngine-API-Key` header:

```bash
X-RegEngine-API-Key: dp_sandbox_abc123...
```

### Rate Limits

- **Default**: 60 requests/minute
- **Burst**: Up to 100 requests in 10-second window
- **Headers**:
  - `X-RateLimit-Limit`: Your rate limit
  - `X-RateLimit-Remaining`: Requests remaining
  - `X-RateLimit-Reset`: Unix timestamp when limit resets

### Error Handling

| Status Code | Meaning | Action |
|-------------|---------|--------|
| 401 | Unauthorized | Check API key |
| 429 | Rate limit exceeded | Implement exponential backoff |
| 500 | Server error | Contact support if persistent |

### Data Model

**Key Entities**:
- **Document**: Source regulatory text (PDF, HTML, etc.)
- **Obligation**: Machine-readable requirement extracted via NLP
- **Concept**: Normalized term (e.g., "capital requirements")
- **Jurisdiction**: Geographic scope (e.g., "United States")
- **Threshold**: Quantitative requirement (e.g., "$250,000 minimum")

**Relationships**:
- Document → contains → Obligation
- Obligation → maps_to → Concept
- Obligation → applies_in → Jurisdiction
- Obligation → supersedes → Prior_Obligation (temporal tracking)

---

## Sandbox Limitations

**Important**: The sandbox environment has these constraints:

1. **Non-Production Use Only**: Do not build production systems on sandbox
2. **Data Persistence**: Sandbox data may be reset with 48-hour notice
3. **Performance**: Not SLA-backed (production will have 99.9% uptime commitment)
4. **Features**: Some advanced features may be disabled (e.g., ML re-training)
5. **Document Limits**: 1,000 documents max (production: unlimited)

---

## Support & Contact

### During Onboarding

- **Slack**: #regengine-design-partners (fastest response)
- **Email**: support@regengine.ai
- **Video calls**: Calendly link sent via email

### After Hours / Emergencies

- **Email**: oncall@regengine.ai (critical issues only)
- **Response SLA**: Best-effort (no guarantee during design partner phase)

---

## Success Metrics

We'll measure design partner success by:

1. **API Integration Depth**
   - Did you integrate at least 2 core endpoints?
   - Did you query sandbox API ≥ 100 times?

2. **Feedback Quality**
   - Did you provide specific feature requests?
   - Did you identify data quality issues?

3. **Use Case Validation**
   - Did RegEngine address your core use case?
   - Would you recommend us to peers?

4. **Commercial Intent**
   - Would you transition to paid customer?
   - What's your timeline to production?

---

## Next Steps After Onboarding

1. **Complete Feedback Survey** (sent Week 8)
2. **Schedule Production Planning Call** (sales + engineering)
3. **Negotiate Commercial Terms** (if moving forward)
4. **Migration to Production API** (typically 1-2 weeks)

---

## Frequently Asked Questions

### Can I test with real regulatory documents from my industry?
Yes! Upload any publicly available regulatory documents. For proprietary/confidential documents, please discuss with our team first.

### What if I need more than 1,000 documents?
Contact us via Slack and we can increase your limit for the design partner program.

### Can I share API access with my team?
Yes, up to 5 teammates. Each should use the same API key (we'll provide separate keys for production).

### What happens to my data after the design partner program?
- **Sandbox data**: Deleted 30 days after program end (unless you transition to production)
- **Feedback/discussions**: Retained (anonymized) for product development
- **Your uploaded documents**: You retain all rights; we use only for providing the service

### What if I want to extend beyond 8 weeks?
Contact your design partner manager. Extensions are typically granted on a case-by-case basis.

---

## Document Version

- **Version**: 1.0
- **Last Updated**: 2025-11-19
- **Contact for Updates**: partnerships@regengine.ai

---

**Welcome aboard! We're excited to have you as a design partner. Let's build the future of regulatory intelligence together.**
