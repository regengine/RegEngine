# Mythos Pass — 2026-05-09 (Revised)

**Supersedes:** the conversational mythos report delivered 2026-05-09. That version was never committed and contained one major error (the `kernel/` orphaning claim). This document is the corrected, code-grounded version. All findings are mapped to PRs so any reader can verify on `main`.

**Audience:** Christopher (founder); future hires who need to reconcile what RegEngine *says* with what the code *does*.

---

## 1. TL;DR

- Wave 1 + Wave 2 cleanup landed 13 PRs (#2204–#2218) addressing 9 of the 10 original mythos findings; one finding (kernel orphaning) was wrong on the facts and is corrected here.
- `kernel/` is **not** fully orphaned — 8 live import sites in `services/ingestion` and `services/graph`. Only `kernel/control/` (codegen + RCE) is safely deletable today.
- Marketing/sales surfaces (homepage, sales kit, product description, demo, /contact, /api-keys, sample-data banners) are now consistent with shipped code.
- Two strategic decisions remain open: (a) Partner Gateway — ship (Path A) or kill (Path B); (b) kernel migration plan (multi-PR, tracked under #2205).
- Process change: quarterly mythos pass; verify findings on `main` before declaring a myth (per `project_issue_tracker_drift_2026_04_20`).

---

## 2. Critical myths (status carried forward)

The following findings from the original pass are preserved. The kernel claim and items already fully addressed by individual PRs are moved to the status table (Section 5). The strategic decisions still live here:

### 2.1 Marketing/code contradiction — RESOLVED
`PRODUCT_FEATURE_LIST.md` and `CURRENT_SYSTEM_MAP.md` made claims unsupported by code. Both files were archived in **PR #2204**; the canonical replacement is `docs/PRODUCT_DESCRIPTION.md` (**PR #2208**).

### 2.2 Partner Gateway — sales kit fixed, product decision still open
Sales kit no longer promises Partner Gateway as a shipping feature (**PR #2207**). The router itself is still disabled in production. The underlying decision is unresolved:
- **Path A (ship):** finish auth/rate-limit/idempotency, document, enable in prod.
- **Path B (kill):** remove the router and references; defer until a paying customer requires it.
This is a founder decision, not a doc fix.

### 2.3 "6 microservices" framing — RESOLVED
Old framing implied an active distributed architecture; reality is 6 Railway services trending toward monolith (per `project_target_architecture`). Resolved by **PR #2204** (archived stale arch docs) + **PR #2208** (canonical description states the actual topology).

### 2.4 AI-forward narrative — RESOLVED
Homepage and sales materials previously led with "AI-powered compliance." Reality: rules engine + deterministic graph traceability with NLP as one of several ingestion paths. Resolved by **PR #2206** (homepage hero rewrite) + **PR #2208** (positioning).

### 2.5 `/demo` synthetic data without banner — RESOLVED (pre-Wave 1)
Shipped 2026-05-07 in **PR #2175**.

### 2.6 `api.regengine.co` DNS — RESOLVED
DNS issue + CI guard against the bad hostname in user-visible samples. Code samples shipped in **PR #2175**; CI guard in **PR #2210**.

### 2.7 `/api-keys` fake-key generator — RESOLVED (pre-Wave 1)
Removed 2026-05-07 in **PR #2175**.

### 2.8 `/contact` form had no handler — RESOLVED
Wired to a real Next.js route handler in **PR #2212**.

---

## 3. Corrected: kernel finding

**Original (incorrect) claim:** "`kernel/` is fully orphaned and can be deleted."

**What verification on `main` actually shows:** 8 live import sites across two services. The kernel package is partially live, partially dead. Deleting it wholesale would break ingestion and graph routes.

### Live import sites

| File | Line(s) | Imports |
|---|---|---|
| `services/ingestion/app/routes_ingest.py` | 77 | `kernel.obligation.regulation_loader.RegulationLoader` |
| `services/ingestion/app/routes_scraping.py` | 24 | `kernel.discovery.discovery` |
| `services/ingestion/app/task_handlers_discovery.py` | 17 | `kernel.discovery.discovery` |
| `services/graph/app/routers/regulations.py` | 188 | `kernel.graph.MappingEngine` (function-local) |
| `services/graph/app/routers/fsma/wizard.py` | 25 | `kernel.reporting.fsma_engine.FSMAApplicabilityEngine` |
| `services/graph/app/routers/fsma/traceability.py` | 299, 324, 349 | `kernel.graph_traceability.TraceabilityLinker` (function-local x3) |

### Reconciliation with prior memory

The earlier audit (`project_kernel_audit_2026_04_17`) was **narrower and correct**: it flagged only `kernel/control/` (codegen + RCE) and `obligation/routes` as orphaned. That subset claim still holds. The error in the 2026-05-09 conversational report was generalizing from that audit to "all of `kernel/`" without re-grepping. That generalization is wrong.

### Surgical retire plan (tracked in PR #2205)

- **Safely deletable now:** `kernel/control/` — has the codegen crash and RCE flagged in the prior audit and zero live importers. Drop it in a focused PR.
- **Migrate before deleting:** `kernel/discovery/`, `kernel/obligation/regulation_loader.py`, `kernel/graph/` (`MappingEngine`), `kernel/reporting/fsma_engine.py`, `kernel/graph_traceability.py`. Each has a live consumer in `services/`. The pattern is: move the module under the consuming service, update the import, remove the kernel copy. One PR per module; do not batch.
- **Sequence:** `kernel/control/` deletion first (no consumers, removes RCE surface). Then ingestion-side migrations (3 files). Then graph-side migrations (3 files). Finally the empty `kernel/` package goes.

This is a multi-PR effort. **PR #2205** is the BLOCKED tracking PR documenting the constraint; it must not merge as a single change.

---

## 4. Aspirational vs outdated claims (preserved, lightly edited)

These are not lies — they are timing mismatches.

- **"Real-time recall in under 7 minutes."** Aspirational; the recall-drill *front-end* exists (PR #2215, OPEN), but the backend endpoint is deferred (see Section 6).
- **"FSMA 204 compliant out of the box."** Outdated framing. The Compliance Control Plane (PR #271) ships the rules engine; "compliant out of the box" elides per-tenant configuration and the 6/7 CTE enforcement gaps from `project_regulatory_logic_audit_2026_04_17`.
- **"Production-ready API."** Aspirational without scoping; the public surface gated for proof use cases (PR #2217, OPEN) is production-ready. Internal admin/control-plane endpoints are not.
- **"Six-service architecture."** Outdated; target is monolith. Section 2.3 covers this.

---

## 5. Status table

| # | Finding | Status | Reference |
|---|---|---|---|
| 1 | PRODUCT_FEATURE_LIST.md / CURRENT_SYSTEM_MAP.md contradicted code | SHIPPED | #2204, #2208 |
| 2 | Partner Gateway sales claims | SHIPPED (sales kit) / PENDING (product decision) | #2207 |
| 3 | "6 microservices" framing | SHIPPED | #2204, #2208 |
| 4 | AI-forward homepage narrative | SHIPPED | #2206, #2208 |
| 5 | `/demo` had no synthetic-data banner | SHIPPED (2026-05-07) | #2175 |
| 6 | `api.regengine.co` in code samples | SHIPPED | #2175, #2210 |
| 7 | `/api-keys` fake-key generator | SHIPPED (2026-05-07) | #2175 |
| 8 | `/contact` had no handler | SHIPPED | #2212 |
| 9 | `kernel/` "fully orphaned" claim | FALSE-ALARM (corrected here) | This doc, #2205 |
| 10 | EvidenceEnvelopeV3 / Partner Gateway in sales kit | SHIPPED | #2207 |
| 11 | Sample data integrity | DRAFT | #2218 |
| 12 | Public `/verify` widget | DRAFT | #2213 |
| 13 | Public `/proof/transformation` walkthrough | DRAFT | #2214 |
| 14 | Public `/proof/recall-drill` page | DRAFT | #2215 |
| 15 | Public `/proof` index w/ downloads | DRAFT | #2216 |
| 16 | Public verify-export endpoint | DRAFT | #2217 |
| 17 | `kernel/` migration | RESOLVED — kernel retired in epic-g final cleanup PR | this PR (closes #2223–#2228) |
| 18 | Recall-drill **backend** endpoint | PENDING | deferred from W2.6 |

---

## 6. Remaining myths

Three items still close the gap between claim and code:

1. **Kernel migration (multi-PR).** Section 3 enumerates the 6 modules + 1 deletable subdir. Sequencing matters: `kernel/control/` first (eliminates RCE), then per-module moves. Tracked under PR #2205 (BLOCKED tracking PR — do not merge as one change).
2. **Partner Gateway production decision.** Sales kit is honest; the router decision is not. Founder must pick Path A (ship: complete auth/rate-limit/idempotency) or Path B (kill: remove router + references). Defaulting indefinitely accrues sales-kit drift.
3. **Recall-drill backend endpoint.** PR #2215 ships a public *page* with synthetic data; the actual backend endpoint that powers a real customer recall drill is deferred from Wave 2 sprint 6. Without it, "real-time recall in under 7 minutes" remains aspirational (Section 4).

Everything else either shipped or is in DRAFT and tracked under #2213–#2218.

---

## 7. Process note

Two practices will keep mythos drift from rebuilding silently:

**Quarterly mythos pass.** Calendar this. Each pass re-checks every claim on the marketing surface, sales kit, and product docs against `main`. Output is a status table like Section 5. A pass takes 2–3 hours when done quarterly; left for a year, it took two waves and 13 PRs.

**Verify on `main` before declaring a myth.** From `project_issue_tracker_drift_2026_04_20`: GitHub auto-close fails when PRs merge from non-default branches. Multiple "myths" in the original 2026-04-17 audit batch had already been fixed; the issues just hadn't auto-closed. The kernel error in the 2026-05-09 conversational report is the inverse failure — generalizing from a stale narrower audit instead of re-grepping. **Rule: before asserting any code-state claim, grep `main` directly. Memory notes are starting points, not ground truth.**

---

*End of pass. Next scheduled: 2026-08-09.*
