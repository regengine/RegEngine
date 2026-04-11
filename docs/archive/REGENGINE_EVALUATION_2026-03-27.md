# RegEngine — Full Evaluation

**Date:** 2026-03-27 | **Evaluator:** Claude | **For:** Christopher, Founder

---

## Overall Score: 5.4 / 10

Not bad for a solo founder. Not ready for a paying customer.

---

## 1. Codebase Quality

| Dimension | Score | Key Evidence |
|-----------|-------|-------------|
| Architecture | 6/10 | 7 microservices is 4 too many for a solo founder. Clean boundaries, but 17 containers for local dev. |
| Code Quality | 6/10 | Good type hints, structured error handling. One critical duplicate endpoint with inconsistent auth. |
| Test Coverage | 5/10 | Backend decent (305 test files). Frontend is near-zero: 6 E2E tests, 0 unit tests across 416 TS files. |
| Security | 7/10 | JWT rotation, RBAC, tenant isolation all solid. 3 endpoints still unprotected. OAuth/OIDC are stubs. |
| Production Readiness | 5/10 | Structured logging, health checks exist but lie (report healthy when Kafka is down). No metrics endpoint on most services. |
| Developer Experience | 4/10 | 17-container Docker stack. No troubleshooting docs. Missing env validation script. |
| Feature Completeness | 5/10 | Core FSMA pipeline works 70-80%. OAuth, external connectors, mobile, anomaly detection are all stubs adding dead weight. |

**Biggest Codebase Risk:** You're carrying infrastructure for a 3-person team while operating solo. The stubs (OAuth, connectors, mobile, anomaly detection) create maintenance drag with zero customer value.

---

## 2. What the Site Promises vs. What Exists

### Claims That Are Real
- CTE ingestion from CSV, XLSX, EDI, EPCIS, webhooks — **works**
- KDE validation against FSMA 204 — **works** (added recently)
- FDA-ready CSV export with SHA-256 hashing — **works**
- EPCIS 2.0 JSON-LD export — **works**
- Recall simulation with forward trace — **works**
- FTL Coverage Checker — **works**
- Retailer Readiness Assessment — **works**
- Multi-tenant with RBAC — **works**
- FLBR CTE support — **works** (added recently via V037 migration)

### Claims That Are False or Misleading
- **"Python, Node.js, Go SDKs" with install commands and v1.0.0** — None exist. The pages show `pip install regengine`, `npm install @regengine/sdk`, `go get github.com/regengine/regengine-go`. These packages don't exist.
- **API Playground "test with your API key"** — Returns hardcoded mock data with a fake 1-second setTimeout delay. No real backend calls.
- **Compliance score endpoint** — Returns hardcoded 94% when backend is unavailable. A developer would think they're getting real data.
- **"23 FDA food categories mapped"** — No evidence of 23 categories in the codebase. Unverifiable claim on the landing page.
- **Rate limiting per pricing tier** — Everyone gets 100 RPM regardless of plan. No tier enforcement.
- **"Community libraries: Ruby, PHP, Java — Coming soon"** — No development activity. Pure vapor.

### Claims That Are Partially True
- **"24hr Recall window — fully covered"** — The export pipeline works, but event entry timestamps aren't captured (only event occurrence time). FDA requires knowing when records entered the system.
- **"EPCIS 2.0 Native"** — Export works, but Growing CTE and supplier verification records aren't covered.
- **Demo mode** — Exists but inconsistent. Some modules warn "demo data," others silently serve it.

---

## 3. FSMA 204 Regulatory Compliance

**Status: 60% production-ready**

| Requirement | Status |
|-------------|--------|
| 7 CTE types supported | 5 of 7 (missing Growing, FLBR partially via migration) |
| KDE validation at upload | FIXED — `_validate_event_kdes()` enforces required fields |
| 24-hour sortable spreadsheet | Works (CSV export with proper columns) |
| Chain of custody verification | FIXED — Merkle tree integrated into export flow |
| Event entry timestamp | NOT FIXED — No `system_entry_timestamp` field |
| Supplier verification records | NOT FIXED — No templates |
| Corrective action documentation | NOT FIXED — No templates |

**Bottom line:** RegEngine can demo FSMA 204 compliance convincingly. It cannot survive an actual FDA records request today because event entry timestamps aren't tracked and 2 CTE types are missing.

---

## 4. Competitive Positioning

### The Market (21+ competitors identified)

| Tier | Competitors | Pricing |
|------|-------------|---------|
| Enterprise | FoodLogiQ ($32K/yr), JustFood ERP ($120K/mo), SafetyChain, IBM Food Trust | $30K-$1.4M/yr |
| Mid-market | Safefood360 ($5K+), SafetyChain, TraQtion | $5K-$50K/yr |
| SMB | FoodDocs ($84/mo), 3iVerify ($250/mo/user), HeavyConnect ($20/user/mo) | $1K-$5K/yr |

### RegEngine's Position
- **Pricing:** $425-$749/mo founding, $849-$1,499/mo GA → $5K-$18K/yr
- **Target:** Mid-market (between FoodDocs SMB and FoodLogiQ enterprise)
- **Unique angle:** API-first + developer portal + free tools funnel

### What's Missing for Competitive Viability
1. **Not listed anywhere** — RegEngine doesn't appear on SourceForge, G2, Capterra, or any comparison site. Zero market presence.
2. **No customer proof** — No testimonials, case studies, or logos. Competitors show customer counts ("1,500+ facilities" for SafetyChain).
3. **No integrations** — Competitors offer Walmart GDSN, SAP, Oracle connectors. RegEngine's external connectors are stubs.
4. **Pricing is ambitious** — $425/mo founding rate competes with $84/mo FoodDocs and $250/mo 3iVerify. You need to justify the premium with features that work, not stubs.

---

## 5. What's Actually Good

Let me be clear about what's working, because this deserves credit:

1. **Core data pipeline is solid.** CSV → validate KDEs → store with SHA-256 → export FDA-ready CSV with chain verification. This is the heart of FSMA 204 and it works.
2. **Free tools are a genuine differentiator.** FTL Checker and Retailer Readiness Assessment are real, working tools that provide value before signup. No competitor does this.
3. **Multi-tenant with proper isolation.** Tenant ID on every query, RBAC hierarchy, JWT rotation. This is enterprise-grade auth on an MVP budget.
4. **EPCIS 2.0 native export.** Most competitors convert. You generate natively. That's a real technical advantage.
5. **The Merkle tree chain verification** is now integrated into exports. This is a defensible technical moat that competitors using simple databases can't match.

---

## 6. Honest Assessment

### What You've Built
A technically impressive FSMA 204 compliance engine with real regulatory depth and a working data pipeline. The security and multi-tenancy work is genuinely good — better than most Series A startups I've seen.

### What's Holding You Back

**The dev portal is lying to developers.** Three fake SDKs with install commands, a playground that returns mock data, a compliance endpoint that returns 94% when the backend is down. If a developer finds this in their first 5 minutes, you've lost them permanently. This isn't "coming soon" — it's presented as live.

**You're building for a team you don't have.** 7 microservices, 17 Docker containers, OAuth stubs, mobile scaffolding, anomaly detection libraries. Every one of these creates maintenance surface area that costs you time. Time you're spending driving Uber instead of closing design partners.

**You have no market presence.** Zero listings on any comparison site. No G2/Capterra profile. No blog posts ranking for FSMA 204 keywords. Competitors with worse products are capturing every search query.

**The gap between demo and production is real.** Missing event entry timestamps, 2 CTE types not fully supported, no supplier verification templates. A customer who tries to use this for an actual FDA audit will hit a wall.

### Priority Actions (in order)

1. **Fix the dev portal honesty problem today** (1 hour). Remove SDK install commands or replace with "Coming Q2 2026." Add disclaimer to playground. Remove compliance score fallback. This is trust damage you can't afford.

2. **Add event_entry_timestamp to the schema** (4 hours). This is a migration + model change. Without it, your "24-hour response" claim has a regulatory gap.

3. **Get listed on G2 and SourceForge** (2 hours). Free profiles. Your competitors are there. You're not. Every week you delay, someone else captures the "FSMA 204 compliance software" search query.

4. **Kill the dead weight** (2 hours). Delete OAuth stubs, external connector scaffolding, mobile scaffolds, anomaly detection. Ship less. Maintain less.

5. **Get one real customer through the full pipeline** (ongoing). Everything else is noise until someone has used RegEngine for an actual FDA records request simulation with real data.
