# RegEngine Product Roadmap

**Last Updated**: 2025-01-18
**Planning Horizon**: 18 months (Q1 2025 – Q3 2026)

---

## Vision

**Become the de facto regulatory intelligence API layer for the global compliance technology stack.**

By Q3 2026, RegEngine will:
- Power 100+ RegTech and FinTech products
- Cover 50+ jurisdictions with automated ingestion
- Process 10,000+ regulatory documents
- Serve 1M+ API requests/day

---

## Current State (v0.2.0 - January 2025)

### ✅ Shipped
- Four-service microarchitecture (Ingestion, NLP, Graph, Opportunity API)
- Kafka-based event streaming
- Neo4j graph database with provenance tracking
- Basic regex-based NLP extraction (obligations, thresholds, jurisdictions)
- S3 content-addressed storage
- Docker Compose local deployment
- API key authentication & rate limiting
- Prometheus metrics endpoints
- Demo dataset (US SEC, EU MiFID, UK FCA)

### 🔧 Technical Debt / Known Gaps
- NLP is regex-based (not ML-driven)
- No bi-temporal graph support (tx_to/valid_to missing)
- No production Terraform modules (placeholders only)
- No frontend/dashboard
- Limited test coverage (smoke tests only)
- No CI/CD pipeline

---

## Roadmap Overview

```
Q1 2025         Q2 2025         Q3 2025         Q4 2025         Q1 2026         Q2-Q3 2026
│               │               │               │               │               │
├─ MVP Launch   ├─ ML-NLP        ├─ Multi-Juris  ├─ Dashboard    ├─ Enterprise   ├─ Platform
│  • Auth       │  • Transformer │  • 10 sources │  • UI v1      │  • SSO        │  • Webhooks
│  • Demo data  │  • Fine-tuning │  • Auto-ingest│  • Alerts     │  • RBAC       │  • Versioning
│  • Pricing    │  • 90% accuracy│  • Change det.│  • Viz        │  • Audit logs │  • AI Assistant
│  • First sale │                │               │               │               │
```

---

## Q1 2025: MVP & First Enterprise Sale

### Theme: **Ship, Sell, Learn**

**Objectives**:
1. ✅ Ship authentication & secrets management
2. ✅ Create demo dataset & documentation
3. ✅ Define pricing & packaging
4. 🎯 Close first paying customer ($25k–$60k ARR)
5. 🎯 Onboard 3 design partners (free pilot)

### Deliverables

#### Completed (Jan 2025)
- [x] API key authentication with rate limiting
- [x] Environment-based secrets management
- [x] AWS deployment guide (Terraform foundation)
- [x] Demo dataset (3 jurisdictions, 25+ obligations)
- [x] Positioning & messaging guide
- [x] Pricing tiers defined

#### In Progress (Jan–Feb 2025)
- [ ] **Website v1**: Landing page, docs, pricing page
- [ ] **OpenAPI documentation**: Auto-generated API docs
- [ ] **CI/CD pipeline**: GitHub Actions for build/test/deploy
- [ ] **Integration tests**: End-to-end workflow tests
- [ ] **Sales deck**: 10-slide pitch presentation

#### Planned (Feb–Mar 2025)
- [ ] **Design partner program**: 3 pilots with fintech/RegTech
- [ ] **First customer**: Close $25k–$60k enterprise sale
- [ ] **Monitoring dashboard**: Grafana + Prometheus deployment
- [ ] **Customer onboarding playbook**: Docs, scripts, support process
- [ ] **Blog launch**: 3 technical posts on arbitrage detection, gap analysis

**Success Metrics**:
- 1 paying customer
- 3 active design partners
- 10,000 API calls/month
- 500+ documents ingested

---

## Q2 2025: ML-Powered NLP & Accuracy Improvement

### Theme: **From Regex to Intelligence**

**Objectives**:
1. Replace deterministic NLP with transformer-based models
2. Achieve 90%+ precision on obligation extraction
3. Add entity types: Effective dates, penalties, exemptions, definitions
4. Expand to 10 jurisdictions

### Deliverables

#### ML/NLP Improvements
- [ ] **Fine-tuned BERT/RoBERTa** for regulatory NER (Named Entity Recognition)
- [ ] **Span-based obligation extraction**: Identify full obligation text, not just keywords
- [ ] **Threshold normalization**: Convert "5%" and "500 bps" to comparable values
- [ ] **Effective date extraction**: Parse "60 days after publication", "January 1, 2025"
- [ ] **Penalty extraction**: Identify sanctions, fines, and enforcement actions
- [ ] **Definition extraction**: Capture defined terms and their meanings

#### Data Quality
- [ ] **Extraction confidence scores**: Return 0-1 confidence with each entity
- [ ] **Human-in-the-loop review**: Flag low-confidence extractions for review
- [ ] **Gold standard dataset**: 500 manually annotated documents for training
- [ ] **Continuous learning**: Feedback loop from customer corrections

#### Infrastructure
- [ ] **GPU support**: Enable model inference on GPU instances
- [ ] **Model versioning**: Track NLP model versions with git-lfs or DVC
- [ ] **A/B testing**: Compare regex vs. ML extraction in production

#### Jurisdiction Expansion
- [ ] Add 7 new jurisdictions:
  - **US**: CFTC, FINRA, FDIC, OCC
  - **Asia-Pac**: MAS (Singapore), HKMA (Hong Kong), ASIC (Australia)

**Success Metrics**:
- 90% precision on obligation extraction (measured against gold standard)
- 10 jurisdictions covered
- 2,000+ documents processed
- 3 paying customers

---

## Q3 2025: Multi-Jurisdictional Automation & Change Detection

### Theme: **Real-Time Regulatory Intelligence**

**Objectives**:
1. Automated ingestion from 10 regulatory sources
2. Real-time change detection (notify within 24 hours of publication)
3. Bi-temporal graph support (track regulation history)
4. Expand to 20 jurisdictions

### Deliverables

#### Automated Ingestion
- [ ] **RSS/Atom feed monitoring**: Auto-detect new publications
- [ ] **Web scraping**: Crawl SEC, FCA, ESMA, BaFin websites
- [ ] **API integrations**: Federal Register API, EUR-Lex API
- [ ] **Email parsing**: Monitor regulatory bulletin emails
- [ ] **Deduplication**: Detect when same regulation published in multiple formats

#### Change Detection
- [ ] **Document diffing**: Line-by-line comparison of regulation versions
- [ ] **Change notifications**: Email/Slack alerts for new obligations
- [ ] **Change impact analysis**: "This affects 12 of your policies"
- [ ] **Changelog API**: Query all changes since a specific date

#### Bi-Temporal Graph
- [ ] **Transaction time**: When RegEngine learned about the regulation
- [ ] **Valid time**: When the regulation is legally effective
- [ ] **Historical queries**: "What were the capital requirements on June 1, 2023?"
- [ ] **Audit trail**: Who ingested, who extracted, when

#### Jurisdiction Expansion
- [ ] Add 10 new jurisdictions:
  - **Europe**: BaFin (Germany), AMF (France), CNMV (Spain), CONSOB (Italy)
  - **Americas**: ASIC (Canada), CNBV (Mexico), CVM (Brazil)
  - **Middle East**: DFSA (Dubai), SAMA (Saudi Arabia)
  - **Asia**: FSA (Japan)

**Success Metrics**:
- 20 jurisdictions with automated ingestion
- 24-hour change detection SLA
- 5,000+ documents processed
- 10 paying customers ($500k ARR)

---

## Q4 2025: Dashboard & Visualization

### Theme: **Democratize Regulatory Intelligence**

**Objectives**:
1. Launch web dashboard (no-code access to RegEngine)
2. Visualization of regulatory graphs
3. Custom alerts and saved searches
4. Expand to 30 jurisdictions

### Deliverables

#### Dashboard v1 (React + TypeScript)
- [ ] **Search interface**: Query regulations by keyword, jurisdiction, date
- [ ] **Arbitrage explorer**: Visual comparison of thresholds across jurisdictions
- [ ] **Gap analysis viewer**: Interactive gap reports
- [ ] **Obligation timeline**: Visualize when obligations take effect
- [ ] **Provenance viewer**: Click any obligation → see source PDF + offset
- [ ] **Export**: Download results as CSV, JSON, or PDF report

#### Alerts & Notifications
- [ ] **Custom alerts**: "Notify me when EU capital requirements change"
- [ ] **Saved searches**: Bookmark queries for recurring analysis
- [ ] **Email digests**: Weekly summary of new regulations
- [ ] **Slack/Teams integration**: Post alerts to team channels

#### Graph Visualization
- [ ] **Interactive graph explorer**: Navigate regulation relationships
- [ ] **Concept clustering**: Group similar obligations across jurisdictions
- [ ] **Dependency mapping**: Show which regulations reference others

#### Admin Features
- [ ] **User management**: Invite team members, manage permissions
- [ ] **Usage analytics**: API call volume, most-queried jurisdictions
- [ ] **Billing dashboard**: Current usage, projected costs

**Success Metrics**:
- 100 dashboard users
- 30 jurisdictions covered
- 20 paying customers ($1M ARR)
- 10,000+ documents processed

---

## Q1 2026: Enterprise Features & Compliance

### Theme: **Enterprise-Ready**

**Objectives**:
1. SSO (SAML, OIDC)
2. Role-based access control (RBAC)
3. Audit logs & compliance certifications
4. On-premise deployment hardening

### Deliverables

#### Authentication & Authorization
- [ ] **SSO support**: SAML 2.0, OIDC (Okta, Azure AD, Google Workspace)
- [ ] **RBAC**: Admin, Editor, Viewer roles
- [ ] **API key scopes**: Read-only vs. read-write keys
- [ ] **IP whitelisting**: Restrict access to specific networks

#### Compliance & Security
- [ ] **SOC 2 Type II certification**: Audit and certification process
- [ ] **Audit logs**: Immutable log of all actions (who, what, when)
- [ ] **Data residency**: EU/US data isolation options
- [ ] **Encryption at rest**: KMS-managed encryption for S3, Neo4j
- [ ] **Penetration testing**: Annual third-party pen test

#### On-Premise Deployment
- [ ] **Kubernetes Helm charts**: Production-ready K8s deployment
- [ ] **Air-gapped installation**: Offline deployment support
- [ ] **HA configuration**: Multi-AZ, auto-scaling
- [ ] **Backup & DR**: Automated backups, disaster recovery playbook

#### Enterprise Integrations
- [ ] **ServiceNow plugin**: Create tickets from regulation changes
- [ ] **Jira integration**: Link obligations to compliance tasks
- [ ] **Salesforce connector**: Sync regulatory data to CRM
- [ ] **Tableau/PowerBI connectors**: Business intelligence integration

**Success Metrics**:
- SOC 2 Type II certified
- 5 enterprise customers with on-premise deployments
- 50 paying customers ($2M ARR)
- 99.9% uptime achieved

---

## Q2-Q3 2026: Platform & Ecosystem

### Theme: **Regulatory Data Platform**

**Objectives**:
1. Webhooks for real-time integration
2. Versioned API (v2.0)
3. AI-powered regulatory assistant
4. Marketplace for third-party data enrichment

### Deliverables

#### Platform Features
- [ ] **Webhooks**: Push notifications to customer systems
- [ ] **GraphQL API**: Alternative to REST for complex queries
- [ ] **Bulk export API**: Download entire jurisdiction datasets
- [ ] **API versioning**: v1 (stable), v2 (new features), deprecation policy
- [ ] **SDK libraries**: Python, JavaScript, Java, C# client libraries

#### AI Assistant (Experimental)
- [ ] **Chatbot interface**: "What are the capital requirements in the UK?"
- [ ] **LLM-powered summarization**: Generate plain-English summaries
- [ ] **Compliance Q&A**: Ask regulatory questions, get AI-generated answers
- [ ] **Citation validation**: Verify that AI responses have valid provenance

#### Marketplace
- [ ] **Third-party data sources**: Community-contributed jurisdiction parsers
- [ ] **Premium datasets**: IASB, PCAOB, IOSCO standards (licensed)
- [ ] **Custom extractors**: Buy/sell NLP models for niche regulations

#### Ecosystem
- [ ] **Partner program**: Certified RegTech integrators
- [ ] **Developer community**: Forums, Discord, office hours
- [ ] **Annual conference**: RegEngine Summit for customers & partners

**Success Metrics**:
- 100 paying customers ($5M ARR)
- 50+ jurisdictions
- 50,000+ documents
- 5M+ API calls/day
- 10 technology partners

---

## Long-Term Vision (2027+)

### Global Regulatory Graph
- Cover all G20 jurisdictions + top 50 financial markets
- Multi-language support (auto-translate regulations)
- Regulatory taxonomy standardization (map EU "own funds" to US "net capital")

### AI-Native Compliance
- Predictive analytics: "EU is likely to update MiFID in Q3 based on consultation papers"
- Policy auto-generation: "Draft a policy that complies with these 5 regulations"
- Continuous compliance: Real-time monitoring that obligations are still met

### Industry Expansion
- Beyond finance: Healthcare (FDA, EMA), Energy (EPA, FERC), Data Privacy (GDPR, CCPA)
- Vertical-specific packages: "RegEngine for Banking", "RegEngine for Pharma"

---

## Feature Requests & Community Input

We track feature requests in [GitHub Discussions](https://github.com/regengine/regengine/discussions).

**Top community requests** (as of Jan 2025):
1. ⭐ **200 votes**: ML-based NLP (→ Q2 2025)
2. ⭐ **150 votes**: Dashboard/UI (→ Q4 2025)
3. ⭐ **120 votes**: More jurisdictions (→ ongoing)
4. ⭐ **100 votes**: Change notifications (→ Q3 2025)
5. ⭐ **80 votes**: GraphQL API (→ Q2 2026)

**Submit your feature request**: [GitHub Discussions →]

---

## How We Prioritize

### Prioritization Framework

We evaluate features across three dimensions:

1. **Customer Value**: Does this solve a top-3 pain point?
2. **Business Impact**: Does this unlock new revenue or prevent churn?
3. **Technical Feasibility**: Can we ship this in one quarter?

**Priority Matrix**:
- **P0 (Now)**: High value, high impact, feasible → Ship this quarter
- **P1 (Next)**: High value, medium impact → Next quarter
- **P2 (Backlog)**: Medium value or low feasibility → Future consideration
- **P3 (Parking Lot)**: Low value or too speculative → Revisit in 6 months

### Customer-Driven Roadmap

- **Enterprise customers** get input on prioritization (quarterly planning calls)
- **Design partners** get early access to beta features
- **Community** votes on features via GitHub Discussions

---

## Dependencies & Risks

### Key Dependencies
- **ML talent**: Need to hire NLP engineer for Q2 2025 work
- **Jurisdiction partnerships**: May need legal/data partnerships for some countries
- **Compliance certifications**: SOC 2 requires 6-month audit process

### Risks
- **Data quality**: If NLP accuracy doesn't improve, customer trust erodes
- **Regulatory access**: Some jurisdictions may block automated scraping
- **Competition**: Incumbents (Thomson Reuters, Bloomberg) could launch APIs
- **Pricing pressure**: Race to bottom if competitors undercut

### Mitigations
- **ML talent**: Start recruiting in Q1 2025
- **Partnerships**: Explore licensing agreements with regulatory publishers
- **Moat**: Focus on graph-based intelligence, not just raw data
- **Value-based pricing**: Justify costs with ROI, not market rates

---

## Changelog

**v0.2.0** (Jan 2025)
- Added API authentication & rate limiting
- Created demo dataset (US, EU, UK)
- Defined pricing & positioning
- AWS deployment guide (foundation)

**v0.1.0** (Dec 2024)
- Initial microservices architecture
- Regex-based NLP extraction
- Neo4j graph database
- Docker Compose deployment

---

## Get Involved

- **Roadmap questions**: [GitHub Discussions](https://github.com/regengine/regengine/discussions)
- **Feature requests**: [Submit here](https://github.com/regengine/regengine/issues/new?template=feature_request.md)
- **Customer input**: [Join design partner program](mailto:partnerships@regengine.ai)
