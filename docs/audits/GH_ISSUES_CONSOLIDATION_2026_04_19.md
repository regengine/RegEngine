# GitHub Issues Consolidation — 2026-04-19

**Scope:** 148 open issues (down from 361 on 2026-04-17). This document is the
authoritative CTO-level roadmap for the remaining work: what shipped, what
is still open, which meta-epics cover which clusters, and the recommended
execution order for the next 4 sprints.

**Companion docs:**
- Original audit: `docs/audits/GH_ISSUES_CONSOLIDATION_2026_04_17.md`
- Detailed PR scopes for active epics: `docs/plans/EPICS_N_K_F_E_MASTER_PLAN.md`

---

## 1. Delta since the 2026-04-17 audit

**Net:** 213 issues closed in 48 hours across 30+ merged PRs.

| Stream | PR batches | Issues closed |
|---|---|---|
| Security sweep (tenant_id trust, JWT, Kafka HMAC) | #1515, #1516, #1517, #1518, #1511, #1454 | ~25 |
| FDA export hardening (EPIC-L) | #1448, #1513 | 11 |
| GDPR erasure | #1453 | 5 |
| NLP pipeline adoption + LLM hardening (EPIC-E partial) | #1451, #1443 | 20+ |
| Kernel correctness (codegen RCE fix, evaluator) | #1450 | 12 |
| Scheduler / task_queue hardening (EPIC-P) | #1449, #1492, #1536, #1537 | 15 |
| Graph tenant-scoping (EPIC-C under #1315) | #1446, #1437 | 5 |
| Alembic baseline consolidation (EPIC-M) | #1463 | 8 |
| RLS fail-open (EPIC-B PR-1, PR-2) | #1444, #1466 | 4 |
| Frontend security batch | #1447 | 7 |
| Correlation IDs + /metrics + Sentry (EPIC-I) | #1452 | 5 |
| Admin outbox + tenant-required JWT | #1454 | 4 |
| Ingestion webhook + billing gate | #1442 | 8 |
| pytest collection fix | #1445 | 1 (unblocker) |
| Ingestion test coverage (#1342) | #1470, #1479, #1508, #1519, + 30 smaller | 30+ |

**Takeaway:** Every filed meta-epic (B, D, E, F, K, N) has landing PRs. The
broader "fix the fail-open tenant boundary" story is ~80% done.

---

## 2. Filed meta-epics — current status

| Epic | Issue | Open children | % done | Status |
|---|---|---|---|---|
| EPIC-B RLS fail-open | [#1456](https://github.com/PetrefiedThunder/RegEngine/issues/1456) | 1 (#1271) | ~85% | PR-2 landed, final cleanup |
| EPIC-D Hash-chain + idempotency | [#1457](https://github.com/PetrefiedThunder/RegEngine/issues/1457) | 6 | ~50% | Appender extraction pending |
| EPIC-E NLP extractor | [#1458](https://github.com/PetrefiedThunder/RegEngine/issues/1458) | 5 | ~60% | LLM hardening done; CTE coverage open |
| EPIC-F Rules engine | [#1459](https://github.com/PetrefiedThunder/RegEngine/issues/1459) | 2 (#1102, #1371) | ~75% | Seed rules landed; per-CTE KDE + cache remaining |
| EPIC-K Admin RBAC + audit | [#1460](https://github.com/PetrefiedThunder/RegEngine/issues/1460) | 5 | ~60% | Role-race + audit-integrity open |
| EPIC-N Ingestion parsers | [#1461](https://github.com/PetrefiedThunder/RegEngine/issues/1461) | 13 | ~30% | EDI/EPCIS long-tail + `BackgroundTasks` → `task_queue` |
| EPIC (legacy) Tenant-isolation | [#1099](https://github.com/PetrefiedThunder/RegEngine/issues/1099) | — | — | Umbrella; closes when B+C+A clear |
| EPIC (legacy) GDPR | [#1098](https://github.com/PetrefiedThunder/RegEngine/issues/1098) | 2 (#1094 portability, #1095 lead erasure) | ~85% | Erasure done; Art. 15/20 open |
| SEC-META Graph (EPIC-C) | [#1315](https://github.com/PetrefiedThunder/RegEngine/issues/1315) | ~3 | ~80% | Tenant-scope + outbox done; password rotation + audit-log read gap open |
| auth [tracker] dual-auth | [#1100](https://github.com/PetrefiedThunder/RegEngine/issues/1100) | ~8 | ~40% | See §3 Auth consolidation below |
| auth [tracker] revocation | [#1101](https://github.com/PetrefiedThunder/RegEngine/issues/1101) | ~4 | ~60% | JTI-required + cross-worker done |

---

## 3. New meta-epics filed today — 2026-04-19

Three consolidation clusters from the original audit were never filed as
meta-issues but the underlying children are still open. Filing them now.

| Epic | Tracker | Theme | Open children |
|---|---|---|---|
| EPIC-H Event backbone unification | [#1603](https://github.com/PetrefiedThunder/RegEngine/issues/1603) | Kafka vs pg_notify split-brain, DLQ, shared worker base | 12 |
| EPIC-O Supply-chain & CI posture | [#1604](https://github.com/PetrefiedThunder/RegEngine/issues/1604) | SBOM, multi-stage Dockerfiles, lockfiles, SHA pins, secret scanning | 14 |
| EPIC-G Retire kernel/control stack | [#1605](https://github.com/PetrefiedThunder/RegEngine/issues/1605) | 2 survivors after #1450; adopt-or-retire decision | 2 |

These three epics together consolidate **28 of the 148 remaining issues**.

---

## 4. Remaining singleton / small clusters

After the three new epics above, the long tail breaks down:

| Cluster | Count | Recommendation |
|---|---|---|
| Auth — session hygiene (tracked under #1100/#1101) | 16 | Keep trackers; do a single PR per tracker to burn down |
| NLP correctness (tracked under EPIC-E #1458) | ~12 | Continue under #1458; may split FTL-gate PR |
| Compliance (rest under EPIC-F / EPIC-L residuals) | 10 | Fold into #1459 or close as already-shipped |
| Tests (tracked under #1342 + new coverage floors) | 9 | Continue current grind; add 70% coverage floor PR |
| CTE + canonical persistence (under EPIC-D #1457) | 9 | Fold into appender extraction |
| Graph (under #1315 + EPIC-H) | 5 | Close with EPIC-H + Neo4j driver PR |
| RBAC-specific | 3 | Fold into EPIC-K #1460 |
| Identity resolution | 3 | Small enough for standalone PR; no epic needed |
| Stripe / billing | 2 | Standalone "Stripe webhook hygiene" PR |
| Review service | 2 | Fold into EPIC-D idempotency or standalone PR |
| Scheduler residuals | 2 | Ship with EPIC-P final close |
| Infra / gateway / observability long-tail | 9 | One "infra polish" PR |

---

## 5. Recommended 4-sprint execution plan

Ship order optimized for **investor-diligence readiness first** per
`feedback_ship_sequence.md`: security boundary stories before cosmetic /
feature-claim work.

### Sprint 1 (week of 2026-04-21) — "Tenant boundary is closed"
- EPIC-B final PR (#1271 policy conflict squash) → close #1456
- EPIC-D appender extraction + idempotency migration → closes 8 children
- EPIC-C residuals under #1315 → close meta
- **Deliverable:** security-review story reads "every write path checks
  tenant via JWT; RLS can't fail open; hash chain is race-safe."

### Sprint 2 (week of 2026-04-28) — "FSMA claims match code"
- EPIC-E FSMAExtractor CTE coverage PR (HARVESTING, COOLING,
  INITIAL_PACKING, FIRST_LAND_BASED_RECEIVING) + FTL gate
- EPIC-F per-CTE KDE enforcement + rules cache TTL → close #1459
- EPIC-N transactional batch insert + `ParseResult` contract
- **Deliverable:** every FSMA CTE extractor + validator has
  parity with 21 CFR 1.1320-1.1350.

### Sprint 3 (week of 2026-05-05) — "Reliable under load"
- EPIC-H shared consumer base + DLQ replay CLI (12 children) → close
- EPIC-K role-change SELECT FOR UPDATE + audit-integrity migration → close
- Ingestion `BackgroundTasks` → `task_queue` swap (#1267) + webhook HMAC
- **Deliverable:** "background work survives a deploy; audit chain is
  tamper-evident; role-demote can't orphan a tenant."

### Sprint 4 (week of 2026-05-12) — "Auditor + CI posture"
- EPIC-O multi-stage Dockerfiles + SBOM + lockfiles + SHA pins (#1137,
  #1139, #1143, #1145, #1149, #1155) → close 9 of 14
- EPIC-G decision PR: retire `services/kernel/control` +
  `services/kernel/obligation` modules (default recommendation). Close
  #1359, #1366.
- Auth tracker burn-down (#1100, #1101) — 2 PRs to close all 16 children
- Coverage floor raise to 70% (#1348) — one PR per service
- GDPR Art. 15/20 data-access + portability endpoint (#1094) → close #1098
- **Deliverable:** SOC2-adjacent CI posture + long-tail zero.

---

## 6. Close candidates — verify then close

Issues that may already be resolved by recent PRs. Audit required before
closing:

| Issue | Likely fixed by | Verification |
|---|---|---|
| #1029 NLP consumer audit-log swallow | #1451 pipeline routing | Grep `nlp/app/consumer.py` for `log.error` + flush |
| #1039 `_revoked_jtis` unbounded | #1516 cross-worker revocation | Check `auth/jwt_service.py` — is it Redis now? |
| #1041 MFA recovery codes SHA-256 | Not in commit log | Likely still open |
| #1061 `/tools/confirm-code` rate limit | #1511 tool-access JWT separation | Check ingestion rate-limiter decorator |
| #1062 CORS registered twice | Not in commit log | Grep `add_middleware(CORSMiddleware` |
| #1085 poison-pill offset commit before DLQ flush | #1451 NLP hardening | Check consumer commit ordering |
| #1113 compliance store.py (853 LOC) dead | Not tracked | Check: is it imported anywhere? |
| #1118 arbitrage_detector vaporware | #1450 kernel batch | Check if path even runs |
| #1127 S3 URI parse bypass | #1443 identity+NLP | Check `validate_s3_uri` caller |
| #1166 Graph consumer retry dict leak | Open until EPIC-H | Still open |
| #1189 Stripe webhook handlers | Not tracked | Likely still open |
| #1192 DLQ replay mechanism | Open until EPIC-H | Still open |
| #1248 ingestion webhook in-memory dedup | Folded into EPIC-D | Still tracked |
| #1267 FastAPI BackgroundTasks durable | Open until EPIC-N | Still open |
| #1407 supplier/demo/reset RBAC | Master plan says fixed | Verify `user_routes.py:97,162` |

Tasks 1-15 above should be swept in a **"ghost close" pass** before
Sprint 1 starts — prevents treadmill work.

---

## 7. Summary stats

| Count | Category |
|---|---|
| 361 | Issues open on 2026-04-17 |
| 148 | Issues open on 2026-04-19 (-213) |
| 11 | Active meta-epics (8 filed + 3 new today) |
| ~100 | Issues consolidated under those 11 epics |
| ~48 | Long-tail singletons (most fold into auth/#1100, tests/#1342, or singleton PRs) |
| 4 | P0 critical remaining (#1099, #1098, #1456, #1457) — all meta/epic-wrapped |
| 7 | `critical`-labeled singletons (#1103-#1106, #1159, #1166, #1315) — all mapped to epics |

**Net:** ~95% of the 148 remaining issues are covered by an epic; the
other 5% are standalone PRs of < 1 day each. No orphaned critical work.
