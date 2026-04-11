# RegEngine — Remediation Sprint Plan

**Created:** February 7, 2026  
**Last Updated:** February 8, 2026  
**Status:** Sprints 1-5 substantially complete  

---

## Sprint 1: Security Hardening (P0 + P1 Security) ✅ COMPLETE
**Issues:** #1, #2, #3, #4, #5, #8  
**Goal:** Eliminate all critical security vulnerabilities  

- [x] 1.1 Remove hardcoded credentials from `verify_migration.py` and `debug_rls.py`
- [x] 1.2 Fix automotive auth stub → integrate with shared auth
- [x] 1.3 Fix gaming auth stub → integrate with shared auth
- [x] 1.4 Fix bare `except:` in `ingestion/app/routes.py`
- [x] 1.5 Fix hardcoded `userId` in `compliance/status/page.tsx`
- [x] 1.6 Re-enable Owner Dashboard auth gate

---

## Sprint 2: Reliability & Integrity Fixes (P1) ✅ COMPLETE
**Issues:** #6, #7, #9, #10, #12, #13, #14  
**Goal:** Fix broken features, remove stubs from production paths  

- [x] 2.1 Implement review queue database logic (`admin/review_routes.py`)
- [x] 2.2 Label PCOS stubbed components as "Demo Preview"
- [x] 2.3 Fix Sentry — clean dead config, keep safe stubs until SDK is installed
- [x] 2.4 Fix NLP resource path fragility (`consumer.py`)
- [x] 2.5 Add Kafka DLQ strategy for poison pills in NLP consumer

---

## Sprint 3: Code Quality & Type Safety (P2) ✅ COMPLETE
**Issues:** #15, #16, #17, #25, #32  
**Goal:** Clean up type holes, debug logs, mock data, and monolithic files  

- [x] 3.1 Fix `: any` type holes (8 API routes + PCOS budget parser — 13 `any` → `unknown`)
- [x] 3.2 Remove `console.log` from API routes (2 instances)
- [x] 3.3 Label mock-data dashboards as "Demo Preview"
- [x] 3.4 `print()` audit — only in CLI debug scripts, not production code

---

## Sprint 4: Dependencies & DevOps (P1/P2) ✅ COMPLETE
**Issues:** #11, #18, #19, #22, #24, #31, #34  
**Goal:** Fix dependency vulnerabilities, expand CI, clean artifacts  

- [x] 4.1 Replace `xlsx` with `exceljs` (ExportButton + budget_parser)
- [x] 4.2 Pin dependencies — `internal/requirements.txt` + `scheduler/requirements.txt`
- [x] 4.3 Expand CI matrix — test: 7→15, security: 4→15, docker: 4→7
- [x] 4.4 Clean stale root artifacts
- [x] 4.5 Add OTel conditional init — graceful no-op + `OTEL_ENABLED` kill-switch

---

## Sprint 5: Architecture & Testing (P2/P3) ✅ SUBSTANTIALLY COMPLETE
**Issues:** #20, #21, #23, #26, #27, #28, #29, #30, #33  
**Goal:** Standardize patterns, add tests, document architecture  

- [x] 5.1 Implement PPAP Vault file storage (local FS with SHA-256 verification)
- [x] 5.2 Standardize Kafka worker boilerplate (`shared/kafka_consumer_base.py`)
- [x] 5.3 Convert TODO comments to tracked issues (`docs/TRACKED_ISSUES.md` — 4 open)
- [x] 5.4 Document database topology (`docs/DATABASE_TOPOLOGY.md`)
- [x] 5.5 Replace placeholder tests — scheduler (config, webhook, circuit breaker, Kafka) + compliance (config, analysis engine, notifications)
- [x] 5.6 PCOS decomposition — plan created (`docs/PCOS_DECOMPOSITION_PLAN.md`), duplicate bug fix applied. Full extraction tracked as a future task.

### Additional fixes in Sprint 5:
- Fixed hardcoded `sys.path.insert` in `ppap_vault.py` → relative `Path` resolution
- Fixed duplicate error check in `pcos_routes.py` (`extract_fact_from_authority`)

---

## Verification Log

| Checkpoint | Result | Timestamp |
|------------|--------|-----------|
| Sprint 3 complete — build | ✅ exit 0 | Feb 8, 2026 |
| Sprint 4 complete — build | ✅ exit 0 | Feb 8, 2026 |
| Sprint 5 complete — build | ✅ exit 0 | Feb 8, 2026 |

---

## Deliverables Created

| Document | Path | Purpose |
|----------|------|---------|
| Sprint Plan | `docs/SPRINT_PLAN.md` | This file — progress tracking |
| Database Topology | `docs/DATABASE_TOPOLOGY.md` | Service→DB mapping, schemas, RLS, Kafka topics |
| Tracked Issues | `docs/TRACKED_ISSUES.md` | 4 remaining TODOs converted to structured issues |
| PCOS Decomposition | `docs/PCOS_DECOMPOSITION_PLAN.md` | 10-phase split plan for 3,266-line monolith |
| Kafka Base | `services/shared/kafka_consumer_base.py` | Shared DLQ, health monitor, topic creation |
| OTel Conditional | `services/shared/observability.py` | Graceful no-op when SDK absent |
