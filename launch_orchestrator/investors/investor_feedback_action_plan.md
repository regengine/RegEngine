# Investor Feedback Action Plan

**Date:** 2026-04-05
**Source:** Pre-meeting diligence feedback (American Dynamism lens)
**Verdict:** "Would take the meeting. Would not underwrite from this surface area alone."

---

## Priority 1: Fix Today (Credibility Blockers)

### 1A. CTE Taxonomy Drift — "Precision is product"

**Problem:** Multiple surfaces claim different CTE counts. FDA's rule defines 7 CTEs. RegEngine's code has 9 in fsma_rules.json, says "7" on the login and trust pages, says "100%" on the landing page, and only implements 6 in csv_templates.py.

**FDA's 7 CTEs (per 21 CFR 1.1310):**
1. Harvesting
2. Cooling (before initial packing)
3. Initial Packing
4. Transformation
5. Shipping
6. Receiving
7. First Land-Based Receiving (FLBR)

**What's wrong in the code:**

| File | Current State | Fix |
|------|--------------|-----|
| `services/compliance/app/fsma_rules.json` (lines 309-319) | Lists 9 types: adds GROWING and CREATION | Remove GROWING and CREATION. Keep 7. |
| `services/ingestion/app/csv_templates.py` | Has 6 templates (missing FLBR) | Add FLBR template with correct KDEs per §1.1325 |
| `frontend/src/app/page.tsx` (line 20) | "100% of FSMA 204 CTEs covered" | Keep — becomes accurate once FLBR template exists |
| `frontend/src/app/trust/page.tsx` (line 224) | "7 CTE types" | Correct — leave as-is |
| `frontend/src/app/login/LoginClient.tsx` (line 260) | "all 7 FSMA 204 CTE types" | Correct — leave as-is |
| `frontend/src/app/readiness/page.tsx` (line 111) | "All 7 CTE types covered" | Correct — leave as-is |
| `frontend/src/app/onboarding/supplier-flow/shared/styles.js` (line 38) | Has shipping, receiving, transforming, harvesting, cooling, initial_packing | Correct 6 of 7 — add FLBR |
| README.md | Doesn't claim "8/8" (reviewer may have seen an older version or the landing page "100%") | Audit and confirm no "8/8" language |

**Execution (2-3 hours):**
1. Remove GROWING and CREATION from fsma_rules.json allowed_cte_types
2. Add first_land_based_receiving template to csv_templates.py with KDEs from §1.1325
3. Add FLBR to supplier-flow CTE_TYPES
4. Grep for any remaining "8/8" or "8 CTE" references and fix
5. Run compliance service tests to verify nothing breaks

### 1B. Agent Directories Publicly Tracked — "Consistency QA hasn't caught up"

**Problem:** 29 files in .agent/, .agents/, .claude/, .gemini/ are committed to the public repo. Reveals internal tooling, personas, and workflows.

**Files to remove from tracking:**
- `.agent/` — 18 files (personas, protocols, workflows)
- `.agents/` — 8 files (skills, rules, workflows)
- `.claude/launch.json` — 1 file
- `.gemini/` — 2 files (MCP setup, artifacts)

**Execution (15 minutes):**
1. Add to .gitignore: `.agent/`, `.agents/`, `.claude/`, `.gemini/`
2. `git rm -r --cached .agent .agents .claude/launch.json .gemini`
3. Commit: "chore: remove agent/tooling config from version control"

### 1C. OpenAPI Metadata Drift — "Little inconsistencies auditors use to decide trust"

**Problem:** Admin service contact URL points to the wrong repository URL. Other services have no license/contact metadata. LICENSE says proprietary.

**Execution (20 minutes):**
1. Fix admin/main.py contact URL → `https://regengine.co`
2. Add consistent metadata to ingestion, compliance, nlp, server main.py files:
   - `license_info={"name": "Proprietary", "url": "https://regengine.co/terms"}`
   - `contact={"name": "RegEngine Support", "url": "https://regengine.co"}`

---

## Priority 2: Fix This Week (Competitive Positioning)

### 2A. Pricing Page vs ReposiTrak

**Problem:** Reviewer flagged that if the attack line is "incumbents are too expensive," the comparison must be airtight. ReposiTrak starts at $59/mo. RegEngine starts at $425/mo (design partner).

**Options:**
- **Option A:** Don't attack on price. Attack on completeness, speed, and API-first. ReposiTrak at $59/mo is supplier-traceability-only (barcode scanning + basic record keeping). RegEngine does ingestion, validation, lot tracing, FDA export, and recall drills. Different products.
- **Option B:** Add a footnote to the competitor comparison: "Supplier traceability plan. Full compliance platform pricing not publicly available."
- **Option C:** Create a free tier or lower-entry plan for single-facility operations.

**Recommendation:** Option A + B. Don't compete on price with a $59 plan. Compete on "time to first FDA-ready export." Add an asterisk footnote explaining ReposiTrak's $59 plan scope.

### 2B. Retention Language Gap

**Problem:** FSMA 204 requires 2-year record retention. RegEngine's trust center says subscription term + 90-day post-cancellation window. This is legally honest but strategically weak — the customer still owns the archive problem.

**Options:**
- **Option A:** Extend default retention to 2 years, included in pricing. This becomes a selling point.
- **Option B:** Keep current policy but add a one-click "export full archive" tool and explicitly market: "Your data, your archive, our format."
- **Option C:** Add a 2-year retention add-on tier.

**Recommendation:** Option A is the strongest competitive move. 2-year retention aligns with the rule and removes a buyer objection. Storage cost is negligible at this scale.

---

## Priority 3: This Month (Proof Points for the Next Meeting)

### 3A. Vertical Beachhead

**Reviewer's ask:** "One narrow vertical beachhead."

**Best candidate:** Fresh produce. Highest FSMA 204 risk (most outbreak-prone FTL categories), most fragmented supply chains (small growers → packers → distributors → retailers), and least digitized. The FTL checker tool already maps produce categories.

**Action:** Pick 3-5 produce distributors or packers for design partner outreach. They have the most urgent pain (July 2028 deadline) and the messiest data (handwritten lot codes, paper BOLs).

### 3B. First Public Case Study

**Reviewer's ask:** "One public case study showing accepted retailer/FDA-ready outputs from messy upstream data."

**Action:** Run a mock end-to-end with a design partner: take their actual messy CSV data (mixed date formats, inconsistent UoMs), ingest it, produce an FDA export package, and time the whole flow. Document: "From raw CSV to FDA-ready export in [X] hours, not [Y] weeks."

### 3C. "Between Audits" Usage Story

**Reviewer's ask:** "One story showing the product is used between audits, not only during them."

**Action:** This is the recall drill simulator + readiness dashboard. Position it as: "Monthly 15-minute drill that keeps your team audit-ready year-round." The drill simulator already exists. The readiness page already has a scoring rubric. Wire them together as a recurring workflow, not a one-time compliance checkbox.

---

## Priority 4: Strategic (Next Quarter)

### 4A. Path to System of Record

The reviewer correctly identified that RegEngine's honesty about being an "evidence layer, not a system-of-record replacement" caps defensibility. The path forward:

1. **Short term:** Evidence layer with best-in-class export (current)
2. **Medium term:** Become the canonical record format — if your FDA export is what gets submitted, you are the de facto SoR for compliance
3. **Long term:** Trading partner network (if you're the layer between suppliers and retailers, you become the exchange, not just the archive)

### 4B. Integration Moat

CSV/SFTP is fine for design partners. The moat comes from:
- Pre-built retailer export templates (Walmart, Kroger, Costco each have specific requirements)
- Webhook API that ERP vendors can integrate against
- The sandbox/playground (already built) becoming the onboarding path

---

## Execution Order

| # | Task | Effort | Impact | Do When |
|---|------|--------|--------|---------|
| 1 | Fix CTE taxonomy (1A) | 2-3 hrs | Critical | Today |
| 2 | Remove agent dirs (1B) | 15 min | High | Today |
| 3 | Fix OpenAPI metadata (1C) | 20 min | Medium | Today |
| 4 | ReposiTrak footnote (2A) | 30 min | High | This week |
| 5 | 2-year retention decision (2B) | 1 hr decision | High | This week |
| 6 | Pick produce vertical (3A) | 2 hrs research | High | This week |
| 7 | Mock case study run (3B) | 4-6 hrs | Critical | Before meeting |
| 8 | Wire drill → readiness (3C) | 4-8 hrs | Medium | This month |
| 9 | Finish GitHub Actions cleanup | 10 min | Low | After rate limit resets |
