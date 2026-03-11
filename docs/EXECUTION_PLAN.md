# Archived Execution Plan

This file contained a broader execution snapshot that referenced non-FSMA product surfaces.

Use these files instead:

- `README.md`
- `docs/PRODUCT_ROADMAP.md`
- `docs/specs/FSMA_204_MVP_SPEC.md`
- `docs/AI_ENGINEERING_STANDARDS.md`

Do not use this file as active planning guidance.
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
