# Trust Publication Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make RegEngine's public trust, DPA, privacy, security, pricing, docs, and procurement copy ready for conservative pre-production/design-partner publication.

**Architecture:** Treat `docs/security/TRUST_CLAIMS_MATRIX.md` and `frontend/src/lib/trust-subprocessors.ts` as the control spine for trust claims. Public pages must use conservative wording; internal docs must be clearly marked as planning/reference material; automated copy checks must prevent high-risk claim regressions.

**Tech Stack:** Next.js App Router, TypeScript, Markdown docs, JSON OpenAPI specs, Python copy-check script, npm lint/Vitest verification.

---

### Task 1: Dispatch Specialist Review Agents

**Files:**
- Review: `frontend/src/app/trust/page.tsx`
- Review: `frontend/src/app/trust/architecture/page.tsx`
- Review: `frontend/src/app/trust/retention/page.tsx`
- Review: `frontend/src/app/security/page.tsx`
- Review: `frontend/src/app/dpa/page.tsx`
- Review: `frontend/src/app/privacy/page.tsx`
- Review: `frontend/src/app/terms/TermsClient.tsx`
- Review: `frontend/src/app/pricing/page.tsx`
- Review: `frontend/src/components/pricing/PricingPageClient.tsx`
- Review: `frontend/src/app/integrations/page.tsx`
- Review: `frontend/src/lib/customer-readiness.ts`
- Review: `frontend/src/lib/trust-subprocessors.ts`
- Review: `docs/security/TRUST_CLAIMS_MATRIX.md`
- Review: `docs/security/TRUST_FRAMEWORK.md`
- Review: `docs/DATA_PROCESSING_AGREEMENT.md`
- Review: `sales/procurement_trust_packet_template.md`
- Review: `scripts/check_trust_safety_copy.py`

- [ ] **Step 1: Dispatch legal/DPA risk reviewer**

Prompt: "Review public DPA, Privacy, Terms, markdown DPA, and trust pages for binding-contract overclaims, governing-law conflicts, audit-rights risk, international-transfer claims, deletion/export commitments, and subprocessor notice language. Return only actionable findings with file/line references, severity, and allowed wording."

- [ ] **Step 2: Dispatch FDA/FSMA regulatory reviewer**

Prompt: "Review public pages, blog pages, API docs, OpenAPI specs, product docs, and sales collateral for FDA/FSMA overclaims. Verify language against current FDA sources: original compliance date January 20, 2026; FDA proposed a 30-month extension to July 20, 2028; Congress directed FDA not to enforce before July 20, 2028. Flag 'FDA-ready', 'FDA-compliant', '§1.1455(c)-formatted', 'exact format', 'automates compliance', fixed FTL counts, and unsupported EPCIS/FDA preference claims."

- [ ] **Step 3: Dispatch security/trust claims reviewer**

Prompt: "Review Trust Center, Security, Trust Architecture, Trust Retention, Trust Framework, NFRs, CI/security workflow claims, tenant isolation language, SOC 2/pentest/DAST/SBOM/container-scan statements, and subprocessors. Flag any claim not repo-backed or not correctly scoped to core PostgreSQL-backed paths."

- [ ] **Step 4: Dispatch procurement/corporate reviewer**

Prompt: "Review pricing, procurement packet, claims matrix, case studies, product positioning, competitor comparison, design-partner terms, and sales enablement copy for buyer-facing commercial or diligence risk. Flag absolute pricing guarantees, unsupported competitor claims, public-availability promises, and claims matrix gaps."

- [ ] **Step 5: Dispatch engineering QA reviewer**

Prompt: "Review TypeScript/React integration risk from this diff: status taxonomy/class names, shared subprocessor rendering, public OpenAPI changes, layout metadata, and route render risk. Run targeted static searches if useful. Return bugs with file/line references and verification commands."

- [ ] **Step 6: Dispatch guardrail/release reviewer**

Prompt: "Review scripts/check_trust_safety_copy.py and the manual forbidden-term search strategy. Flag false negatives, false positives, skipped paths that should be scanned, and missing publication-readiness checks. Return patch recommendations and exact verification commands."

### Task 2: Integrate Findings

**Files:**
- Modify as needed: files listed in Task 1 findings

- [ ] **Step 1: Read all agent findings**

Expected: every finding is triaged as fix-now, document-risk, or not-applicable.

- [ ] **Step 2: Patch fix-now issues**

Use `apply_patch` for manual edits. Keep copy conservative:

```text
Use "FDA-oriented", "aligned to 21 CFR 1.1455 where applicable", "helps support", "contracted workspaces", "executed agreement controls", "active-system deletion", and "provider backup expiry/legal-retention caveats".
Avoid "FDA-ready", "FDA-compliant", "FDA approved", "exact format", "ensures compliance", "guarantees", "production SLA", "completed pentest", "SOC 2 Type II", "Native Bidirectional", "paid tenants", and default Redpanda processor language.
```

- [ ] **Step 3: Update the claims matrix**

For each accepted claim category, ensure `docs/security/TRUST_CLAIMS_MATRIX.md` includes claim, status, access tier, source of truth, owner, evidence path, last verified date, allowed wording, prohibited wording, and review cadence.

- [ ] **Step 4: Update guardrails**

Ensure `scripts/check_trust_safety_copy.py` scans public frontend source, public OpenAPI JSON, non-archived docs, sales collateral, and scripts while excluding intentional negative tests, archived/internal files, generated local sales scratch, and the claims matrix.

### Task 3: Verify

**Files:**
- Verify: changed files from Task 2

- [ ] **Step 1: Run frontend lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: command exits 0. Existing warnings may remain if unrelated.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd frontend && npm run test:run
```

Expected: command exits 0.

- [ ] **Step 3: Run trust copy gate**

Run:

```bash
python3 scripts/check_trust_safety_copy.py
```

Expected:

```text
Trust-and-safety copy gate passed.
```

- [ ] **Step 4: Run manual forbidden-term sweep**

Run:

```bash
rg -n "FDA-ready|FDA-compliant|FDA formatted|FDA-formatted|§1\\.1455\\(c\\)-formatted|SOC 2 Type II|pentest summary|completed pentest|FDA certified|FDA approved|exact format|Redpanda|session replay|production SLA|Native Bidirectional|paid tenants|a FDA-oriented|sortable sortable" frontend docs sales scripts --glob '!docs/archive/**' --glob '!docs/_archive/**' --glob '!docs/internal/**' --glob '!docs/superpowers/**' --glob '!frontend/playwright-report/**' --glob '!docs/security/TRUST_CLAIMS_MATRIX.md' --glob '!frontend/src/lib/constants.ts' --glob '!frontend/src/data/fsma-target-market.ts' --glob '!scripts/check_trust_safety_copy.py' --glob '!scripts/trust_safety_copy_allowlist.txt' --glob '!frontend/src/__tests__/**' --glob '!sales/local/**'
```

Expected: no matches.

- [ ] **Step 5: Check whitespace**

Run:

```bash
git diff --check
```

Expected: no output, exit 0.

- [ ] **Step 6: Render public routes locally**

Run:

```bash
cd frontend && npm run dev -- --hostname 127.0.0.1 --port 3210
```

In another shell, run:

```bash
node - <<'NODE'
const paths = ['/trust','/trust/architecture','/trust/retention','/security','/dpa','/privacy','/terms','/pricing','/integrations','/case-studies','/blog/fda-food-traceability-requirements','/blog/fsma-204-compliance-guide','/developers','/docs','/docs/api','/supplier-compliance','/walkthrough','/why-regengine','/proof/recall-drill','/proof/transformation','/retailer-readiness'];
let failed = false;
for (const path of paths) {
  const response = await fetch(`http://127.0.0.1:3210${path}`);
  console.log(`${response.status} ${path}`);
  if (!response.ok) failed = true;
}
process.exit(failed ? 1 : 0);
NODE
```

Expected: every route returns `200`.

### Task 4: Final Readiness Report

**Files:**
- Read: `git status --short`
- Read: `git diff --stat`

- [ ] **Step 1: Summarize specialist review outcomes**

Include each lane: legal/DPA, FDA/FSMA, security/trust, procurement/corporate, engineering QA, guardrail/release.

- [ ] **Step 2: Report implementation status**

Include files changed, what changed, tests run, what passed, what was not tested, remaining risks, and recommended next step.
