# REGENGINE — 60-DAY EXECUTION PLAN

**Created:** 2026-02-08
**Status:** ACTIVE
**Audience:** Founder / Board / Advisors

---

## 0. Current Verified State (Ground Truth)

Before planning what's next, here is what **actually exists today**, verified against code:

| Dimension                    | Verified Count / Status                                                       |
|------------------------------|-------------------------------------------------------------------------------|
| Backend services             | 17 service directories (admin, ingestion, nlp, graph, compliance, opportunity, scheduler, energy, aerospace, automotive, construction, entertainment, gaming, manufacturing, shared, internal, test_data) |
| Test files                   | 281 test files                                                                |
| Frontend routes (pages)      | 130 `page.tsx` files                                                          |
| Database migrations          | 55 SQL migration files                                                        |
| Docker services              | 9 buildable services in `docker-compose.yml`                                  |
| Industry verticals (frontend)| 14 vertical pages (aerospace, automotive, construction, energy, entertainment, finance, food-safety, gaming, healthcare, manufacturing, nuclear, technology, + dashboard, + index) |
| Demo scripts                 | 13 scripts in `scripts/demo/` — **all now passing** (fixed 2026-02-08)        |
| SDK                          | `sdk/` directory exists; `tools/verification_sdk/` has chain verifier          |
| RLS enforcement              | 5+ migration files with `ROW LEVEL SECURITY` policies                         |
| Cryptographic evidence       | SHA-256 hashing in verification SDK + graph provision upserts                  |
| Knowledge Graph              | Neo4j-backed with Provision→Document→Jurisdiction relationships               |
| Alpha waitlist               | `/alpha` page live with signup form, perks, and roadmap timeline              |
| Production URL               | `regengine.vercel.app` / `regengine.co` (Vercel-deployed frontend)            |

### Known Gaps (Honest Assessment)

| Gap                                                  | Severity | Impact                                    |
|------------------------------------------------------|----------|-------------------------------------------|
| Full CI suite not verified green post-today's fixes   | HIGH     | Cannot claim "622 passing tests" until re-run |
| `load_demo_data.py` had async bug until today         | FIXED    | Was a demo-blocker; now resolved           |
| Kafka publisher crashed on non-Docker execution       | FIXED    | Was crashing graph service from host       |
| NLP + compliance-worker not running = partial pipeline| KNOWN    | E2E ingestion works; graph trace times out |
| Alpha signup form is client-only (no backend)         | MEDIUM   | Needs API or email integration to capture leads |
| No automated patent claim traceability                | LOW      | Patent filing is legal work, not code      |

---

## 1. PHASE 1 — STABILIZE & VERIFY (Days 1–7)

**Goal:** Establish an auditable, board-presentable baseline.

### 1.1 Full CI Green Light

| # | Task                                                    | Owner     | Status |
|---|--------------------------------------------------------|-----------|--------|
| 1 | Push today's fixes to `origin/main`                    | Eng       | ☐      |
| 2 | Run full test suite across all 17 services             | CI/Eng    | ☐      |
| 3 | Fix any remaining test failures                        | Eng       | ☐      |
| 4 | Record exact passing test count for board materials    | Eng       | ☐      |
| 5 | Generate CI badge / screenshot for pitch materials     | Eng       | ☐      |

**Deliverable:** Single-line claim: *"X passing tests across Y services, verified [date]"*

### 1.2 Demo Script Suite (Completed)

| # | Script                 | Status | Notes                                            |
|---|------------------------|--------|--------------------------------------------------|
| 1 | `quick_demo.sh`        | ✅     | POSIX-compatible (tr instead of bash 4+ syntax)   |
| 2 | `investor_demo.sh`     | ✅     | Was already passing                               |
| 3 | `load_demo_data.py`    | ✅     | Async/await fix + Kafka graceful degradation       |
| 4 | `test_recall_flow.py`  | ✅     | Graceful partial pipeline (exit 0)                |

### 1.3 Alpha Waitlist Backend

| # | Task                                                    | Owner     | Status |
|---|--------------------------------------------------------|-----------|--------|
| 1 | Wire `/alpha` form to email capture (Resend / Loops)   | Eng       | ☐      |
| 2 | Add submission to Supabase `alpha_signups` table        | Eng       | ☐      |
| 3 | Auto-reply email with confirmation                      | Eng       | ☐      |
| 4 | Admin view of signups in `/owner` dashboard             | Eng       | ☐      |

---

## 2. PHASE 2 — COMMERCIAL PACKAGING (Days 8–21)

**Goal:** Everything a prospect or acquirer sees must be polished and verifiable.

### 2.1 FSMA 204 Sales Demo

| # | Task                                                    | Priority | Status |
|---|--------------------------------------------------------|----------|--------|
| 1 | Record 3-minute video demo: Ingest → Trace → Export    | P0       | ☐      |
| 2 | Create guided demo script (Rizo Lopez recall scenario)  | P0       | ☐      |
| 3 | Ensure demo tenant has 430+ seeded records              | P0       | ✅     |
| 4 | FTL Checker → 23 categories confirmed in production     | P0       | ✅     |
| 5 | FDA Request Mode export generates valid CSV              | P1       | ☐      |
| 6 | One-click "Request Demo" flow from `/alpha`              | P1       | ☐      |

### 2.2 Developer Portal & SDK Polish

| # | Task                                                    | Priority | Status |
|---|--------------------------------------------------------|----------|--------|
| 1 | Verify `sdk/` Python package installs cleanly           | P1       | ☐      |
| 2 | Publish verification SDK to PyPI (or private index)     | P2       | ☐      |
| 3 | API docs at `/docs` — ensure all endpoints documented   | P1       | ☐      |
| 4 | Quickstart guide: "First CTE in 5 minutes" walkthrough  | P0       | ☐      |
| 5 | Sandbox environment for prospects (read-only demo data) | P2       | ☐      |

### 2.3 Pricing & Onboarding Flow

| # | Task                                                    | Priority | Status |
|---|--------------------------------------------------------|----------|--------|
| 1 | Pricing page at `/pricing`                              | P0       | ✅     |
| 2 | Onboarding flow at `/onboarding`                        | P1       | ✅     |
| 3 | Stripe integration for payment capture                  | P2       | ☐      |
| 4 | Tenant provisioning automation                           | P2       | ☐      |

---

## 3. PHASE 3 — IP & LEGAL (Days 8–30, parallel)

**Goal:** File provisional patents, establish IP moat.

### 3.1 Provisional Patent Bundle

| # | Patent Title                                    | Code Evidence                                        | Status |
|---|-------------------------------------------------|------------------------------------------------------|--------|
| 1 | Database-Enforced Tenant Isolation              | `auth_utils.py`, `rls_migration_v1.sql`, V12–V22    | ☐ File |
| 2 | Cryptographic Evidence Chains                   | `verify_snapshot_chain.py`, `verify_chain.py`         | ☐ File |
| 3 | Automated Statutory Recall Marshalling          | `test_recall_flow.py`, `fsma_mock_recall.sh`, FDA export | ☐ File |
| 4 | Regulatory Arbitrage Knowledge Graph            | `neo4j_utils.py`, `overlay_writer.py`, opportunity svc | ☐ File |
| 5 | Multi-Framework Evidence Reuse                  | `load_demo_data.py` (NIST/SOC2/ISO), control mappings | ☐ File |

**Action:** Engage patent attorney with code evidence package. Each provisional needs:
- Technical description (from code)
- Claims (from architecture docs)
- Diagrams (from `docs/ARCHITECTURE.md`)

### 3.2 Trade Secret Inventory

| Asset                          | Protection Method | Location                                |
|-------------------------------|-------------------|-----------------------------------------|
| NLP extraction prompts         | Trade secret      | `services/nlp/`                         |
| Confidence scoring heuristics  | Trade secret      | `services/compliance/`                  |
| Arbitrage opportunity scoring  | Trade secret      | `services/opportunity/`                 |

---

## 4. PHASE 4 — GTM EXECUTION (Days 14–45)

**Goal:** First paying customer or LOI signed.

### 4.1 Outreach Sequence

| Week | Action                                         | Target                                            |
|------|-------------------------------------------------|--------------------------------------------------|
| 3    | LinkedIn outreach to FSMA 204 compliance leads  | 50 SMB food producers                             |
| 3    | Cold email sequence (3-touch)                   | VP Compliance / Quality at target companies       |
| 4    | FTL Checker as lead magnet ("Is your product on the list?") | Organic / SEO                        |
| 4    | Partner outreach to food ERPs                   | 5 niche ERP vendors                              |
| 5    | Design partner offer (free Alpha, case study)   | Best 3–5 responders                              |
| 6    | Demo calls with warm leads                      | Convert to LOI / paid pilot                      |

### 4.2 Content & SEO

| # | Asset                                           | Status   |
|---|-------------------------------------------------|----------|
| 1 | "FSMA 204 Compliance Checklist" blog post       | ☐        |
| 2 | "What is a CTE?" educational page               | ☐        |
| 3 | FTL Checker shareable results page               | ☐        |
| 4 | Comparison page: RegEngine vs. FoodLogiQ et al  | ✅ (on /pricing) |

### 4.3 KPIs

| Metric                        | Day 30 Target | Day 60 Target |
|-------------------------------|---------------|---------------|
| Alpha signups                 | 25            | 75            |
| Demo calls completed          | 5             | 15            |
| Design partner LOIs           | 1             | 3             |
| Paid pilot revenue            | $0            | $2,400 (1 Starter annual) |

---

## 5. PHASE 5 — M&A READINESS (Days 30–60)

**Goal:** Diligence-ready materials for Corp Dev conversations.

### 5.1 Diligence Package

| # | Material                                        | Source                                    | Status |
|---|-------------------------------------------------|-------------------------------------------|--------|
| 1 | Architecture diagram                            | `docs/ARCHITECTURE.md`                     | ✅     |
| 2 | Security whitepaper (Double-Lock model)          | `docs/` + RLS migration evidence           | ☐      |
| 3 | Test coverage report (with exact counts)         | CI output                                  | ☐      |
| 4 | Patent pending claims (5 provisionals)           | Patent attorney output                     | ☐      |
| 5 | Customer traction proof (LOIs, usage metrics)   | Alpha signups + pilot data                 | ☐      |
| 6 | Financial model (ARR projections)                | Spreadsheet                                | ☐      |
| 7 | Team bios + org chart                            | Internal                                   | ☐      |

### 5.2 Buyer-Specific One-Pagers

| Buyer Category         | Hook                          | Key Evidence to Feature              |
|-----------------------|-------------------------------|--------------------------------------|
| Big 4 / Audit          | Write-once compliance reuse   | Multi-framework mapping, evidence chains |
| ERP (SAP, Oracle)      | FSMA 204 recall mandate       | FDA export, 24-hour recall logic      |
| GRC Vendors            | Tenant isolation architecture | Double-Lock RLS, adversarial tests   |
| Cloud / FinTech        | Security-first infra          | JWT + RLS, cryptographic proofs       |

---

## 6. DECISION GATES

| Gate       | Date        | Criteria                                             | Decision                          |
|-----------|-------------|------------------------------------------------------|-----------------------------------|
| **G1**    | Day 7       | CI green, all demo scripts pass                      | Approve external outreach         |
| **G2**    | Day 21      | Demo video recorded, SDK installable, Alpha live     | Begin sales outreach              |
| **G3**    | Day 30      | ≥1 design partner LOI, patents filed                 | Decide: bootstrap vs. seed raise  |
| **G4**    | Day 45      | ≥3 active pilots, diligence package complete        | Open Corp Dev conversations       |
| **G5**    | Day 60      | Revenue proof, acquisition interest, or pivot signal | Commit to GTM or M&A track        |

---

## 7. RISK REGISTER

| Risk                                              | Likelihood | Impact | Mitigation                                              |
|---------------------------------------------------|-----------|--------|--------------------------------------------------------|
| Full CI suite reveals widespread test failures     | Medium    | High   | Budget Days 1–7 entirely for stabilization              |
| Alpha signups don't convert to demos              | Medium    | Medium | Iterate messaging; add FTL Checker as lead magnet       |
| Patent attorney pushback on claim scope            | Low       | Medium | Code evidence is strong; file narrow provisionals first |
| Acquirer interest without revenue proof             | Medium    | Low    | Revenue is optionality, not requirement for acquisition |
| FSMA 204 deadline pushed back by FDA               | Low       | High   | Platform is vertical-agnostic; pivot to next mandate    |

---

## 8. IMMEDIATE NEXT ACTIONS (This Week)

| # | Action                                                 | Owner | ETA       |
|---|--------------------------------------------------------|-------|-----------|
| 1 | `git push origin main` (today's fixes + Alpha page)   | Eng   | Today     |
| 2 | Full CI test suite run + record results                | Eng   | Day 1     |
| 3 | Wire Alpha form to email capture (Resend API)          | Eng   | Day 2–3   |
| 4 | Record 3-minute FSMA 204 demo video                    | Eng   | Day 3–5   |
| 5 | Draft patent evidence packages (5 one-pagers)          | Eng   | Day 5–7   |
| 6 | Begin LinkedIn outreach (50 targets)                   | GTM   | Day 7     |

---

*This plan is a living document. Update status columns weekly.*

*Last Updated: 2026-02-08 · Author: RegEngine Engineering*
