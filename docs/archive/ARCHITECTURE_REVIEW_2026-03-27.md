# RegEngine Architecture & Code Organization Review
**Date:** March 27, 2026
**Audit #7 (Following 6 prior audits)**
**Scope:** Next.js frontend + FastAPI backend monorepo

---

## 1. PROJECT STRUCTURE

### Overall Layout ✓
```
RegEngine/
├── frontend/              Next.js 15 (Vercel)
├── services/              6 FastAPI microservices
│   ├── admin/
│   ├── compliance/
│   ├── graph/
│   ├── ingestion/
│   ├── nlp/
│   ├── scheduler/
│   └── shared/           Shared libraries (78 modules)
├── kernel/               FSMA reporting engine
├── regengine/            Client SDK + swarm agents
├── migrations/           Flyway-style DB migrations
└── scripts/              Dev, CI, stress tests
```

**Assessment:** Clear monorepo boundary between frontend and backend services. Each service has consistent internal structure (main.py → app/ → routes + models).

---

## 2. GOD FILES (500+ lines)

**53 files exceed 500 lines. Top 5 critical:**

### CRITICAL: `/services/admin/app/pcos_models.py` (2,231 lines)
- **What it does:** SQLAlchemy ORM + Pydantic schemas for Production Compliance OS add-on (small film/TV production companies in CA/LA)
- **Contains:** 40+ model classes (PCOSCompanyModel, PCOSProjectModel, PCOSTimecardModel, etc.) + 30+ Pydantic schemas
- **Issue:** All PCOS domain logic (models + validation schemas) bundled in single file. Domain now spans 16 related models with interdependencies.
- **Recommendation:** Split by bounded context:
  - `pcos_company_models.py` (Company, Registration, Insurance, Safety = 8 models)
  - `pcos_project_models.py` (Project, Location, Permit, Task = 8 models)
  - `pcos_schemas.py` (All 30+ Pydantic schemas in one place is acceptable)
  - Keep enums in `pcos_constants.py` (14 enums)
- **Risk:** HIGH — Central PCOS module touched by multiple routes; changes scatter across admin, compliance, and onboarding

### HIGH: `/services/admin/app/supplier_onboarding_routes.py` (1,757 lines)
- **What it does:** All supplier onboarding HTTP endpoints (create, update, list, bulk operations, compliance checks)
- **Contains:** 18 route handlers + 6 helper functions; mixed business logic in route handlers
- **Issue:** Routes + business logic coupled. No separation of concerns (routes, use cases, data access).
- **Recommendation:** Extract `supplier_onboarding_service.py`:
  - Use cases: create_supplier, update_supplier, bulk_import, validate_compliance
  - Routes file becomes thin (20 lines per endpoint, calls service layer)
- **Risk:** HIGH — Onboarding is user-facing; refactor blocks on feature freeze

### HIGH: `/services/ingestion/app/routes.py` (1,511 lines)
- **What it does:** Primary ingestion endpoints (scrape, ingest, discovery, bulk operations, FDA export)
- **Contains:** 28 route handlers + 8 helper validation functions
- **Issue:** Mixed routing + business logic. No router subdirectory pattern (unlike graph service).
- **Recommendation:** Create router subdirectory:
  - `routers/ingest.py` (POST /ingest, /ingest/file, /ingest/url, /ingest/federal-register, /ingest/ecfr, /ingest/fda)
  - `routers/discovery.py` (GET /discovery/queue, POST /discovery/approve, /discovery/reject, /discovery/bulk-*)
  - `routers/audit.py` (GET /audit/jobs/{job_id}, /audit/logs/{job_id}, /verify/{document_id})
  - Keep main routes.py as orchestrator that imports routers
- **Risk:** MEDIUM — Ingestion is stable; refactor can be phased

### MEDIUM: `/services/graph/app/fsma_utils.py` (1,353 lines)
- **What it does:** FSMA graph utility functions (node creation, query helpers, data transformations)
- **Contains:** 40+ utility functions; no clear grouping
- **Issue:** Utility bucket; hard to find specific functions; mixes graph construction, querying, validation
- **Recommendation:** Break into purpose-driven modules:
  - `graph_builders.py` (Node/edge creation, traceability setup)
  - `graph_queries.py` (Traceability search, lineage paths, recall)
  - `fsma_validators.py` (KDE validation, CTE type checks, compliance rules)
- **Risk:** MEDIUM — Used by multiple services; changes need coordination

### MEDIUM: `/services/nlp/app/extractors/fsma_extractor.py` (1,344 lines)
- **What it does:** FSMA-specific document extraction (regulations, guidance, recalls)
- **Contains:** 3 classes (FSMAExtractor, ParagraphExtractor, MetadataExtractor) + extraction logic
- **Issue:** Large extractor class; extraction logic tightly coupled with FSMA domain logic
- **Recommendation:** Extract to strategy pattern:
  - `fsma_extraction_strategies.py` (Regulation vs. guidance vs. recall extraction)
  - Keep FSMAExtractor as facade; delegate to strategies
- **Risk:** LOW — Stable extractor; refactor is internal

---

## 3. CIRCULAR DEPENDENCIES

**Analysis:** Checked 200+ imports across services.

**Finding: NO direct circular imports detected** ✓

**However, high-risk import chains exist:**

### Chain 1: Admin → Ingestion → Shared
```python
# services/admin/app/supplier_onboarding_routes.py
from services.ingestion.app.onboarding import create_supplier_edi

# services/ingestion/app/onboarding.py
from services.shared.audit_logging import log_action
from services.admin.app.pcos_models import PCOSCompanyModel  # CROSS-SERVICE COUPLING
```

**Impact:** Admin models exposed to ingestion service. Change to PCOS models requires ingestion review.

### Chain 2: Ingestion ↔ Graph (Bidirectional imports)
```python
# services/ingestion/app/routes.py
from services.graph.app.fsma_utils import build_traceability_graph

# services/graph/app/consumers/fsma_consumer.py
from services.ingestion.app.models import NormalizedEvent  # INGESTION MODELS EXPORTED
```

**Impact:** Graph depends on ingestion's event model; ingestion data structures ripple across services.

### Mitigation Recommended:
- Create `services/shared/models/events.py` — NormalizedEvent lives in shared, not ingestion
- Create `services/shared/models/pcos.py` — PCOS enums + base schemas in shared (not admin)
- Services depend only on shared, not peer services

**Risk:** MEDIUM — No runtime crashes (Python imports resolve), but hard to test services in isolation

---

## 4. DEAD CODE

### A. Disabled/Deprecated Folders

#### Frontend: `/frontend/src/app/_disabled/` (13 folders)
```
_disabled/
├── about/                     (3 files)
├── checkout/                  (4 files, old billing flow)
├── design-partner/           (1 file)
├── founding-design-partners/  (4 files, old onboarding)
├── get-started/              (1 file)
├── mobile/                    (1 file, old native attempt)
├── owner/                     (18 files, old multi-tenant design)
├── partners/                  (1 file)
├── portal/                    (1 file)
├── status/                    (1 file, old status page)
└── walkthrough/               (1 file)
```

**Issue:** 13 disabled page suites; owner/ alone has 18 files. Combined, these represent 40+ old page routes never imported.

**Recommendation:** Archive to git history, remove from codebase:
```bash
git rm -r frontend/src/app/_disabled/
git log --all -- frontend/src/app/_disabled/  # Still accessible via git history
```

**Risk:** CRITICAL (visibility only, not runtime) — Next.js might attempt to build these routes in some edge cases.

#### Backend: `/services/shared/_dead_code/` (5 files, 2.6K lines)
```
_dead_code/
├── deserialization_security.py  (15K)
├── jwt_security.py              (19K, 617 lines) — REPLACED by jwt_auth.py
├── password_security.py          (17K, 543 lines)
├── session_security.py           (16K, 509 lines)
└── template_security.py          (17K, 521 lines)
```

**Finding:** Dead security modules archived in March 2020. New modules (`jwt_auth.py`, `session_management.py`, etc.) are in active use.

**Status:** Properly archived. Can be removed if no legacy code depends on them.

### B. Unused Exported Frontend Components (49 identified)

**High-risk unused exports:**

```
❌ DocumentUploadModal        (514 lines)  — Defined in pcos/ but not imported anywhere
❌ BudgetAnalysis            (501+ lines) — Defined in pcos/ but not referenced
❌ AuditPackDownload         (500+ lines) — Defined in pcos/ but orphaned
❌ GlobalSearch              (500+ lines) — Defined in layout/ but no route calls it
❌ AnalysisResults           (500+ lines) — Defined in ingestion/ but dead
```

**Impact:** 49 exported components add to bundle size (even if tree-shaken, they're visible in source). Some are large (500+ lines).

**Recommendation:** Audit and prune:
1. Run `npm run build --analyze` to confirm tree-shaking removes unused components
2. If still in bundle: move unused components to a `_deprecated/` folder or remove
3. Add ESLint rule to catch unused exports

**Risk:** MEDIUM — Code complexity for developers; minimal runtime impact if tree-shaking works.

### C. Unused Routes (possible)

**Status:** No dead routes found in FastAPI services. All 211 `@router.*` endpoints in `/services/*/app/*.py` are intentional API routes.

---

## 5. SHARED CODE ORGANIZATION

### Size & Scale
```
services/shared/
├── Total: 3.4M, 78 .py files, 85 items (including subdirs)
├── Categories:
│   ├── Security modules        30 files (40%)  ← Heavy security focus
│   ├── Logging/Monitoring      12 files (15%)
│   ├── Data/Query              10 files (13%)
│   ├── API/HTTP                12 files (15%)
│   ├── Infrastructure           5 files (6%)
│   └── Other                   15 files (11%)
```

### Assessment: Well-Organized but Approaching Limits

**Strengths:**
- Clear categorization by domain (security, logging, data)
- Single source of truth for RBAC, JWT, encryption, audit logging
- No duplicate implementations across services

**Weaknesses:**
1. **78 modules is at inflection point** — Shared should be 40-50 files ideally
2. **"Other" category is vague** (15 files):
   - `digital_signatures.py`, `key_management.py`, `permissions.py`, `rate_limit.py`, `retry.py`, etc.
   - Some belong in Security (key_management, digital_signatures)
   - Some belong in Infrastructure (rate_limit, retry)
3. **External connectors** — `/services/shared/external_connectors/` is a subdirectory. Is this module-heavy or a single file?

**Recommendation:**
- Reorganize "Other" 15 files:
  - Move `key_management.py` → with security modules
  - Move `digital_signatures.py` → with crypto_signing.py (similar domain)
  - Move `rate_limit.py`, `retry.py`, `circuit_breaker.py` → into new `services/shared/infrastructure/` subdir
- Cap shared at 60 files (currently 78). Future modules should live in service-specific `app/shared/` subdir
- Audit external_connectors: are there unused connectors?

**Risk:** LOW-MEDIUM — Shared is functional; organizational improvement won't impact runtime.

---

## 6. ONBOARDING CLARITY

### Entry Points: CLEAR ✓

Each service has a documented entry point:
```
services/admin/main.py         → app = FastAPI(); @app.on_event("startup")
services/ingestion/main.py     → Kafka consumer + FastAPI app
services/graph/main.py         → Neo4j + FastAPI router setup
services/nlp/main.py           → FastAPI + extractors
services/scheduler/main.py     → APScheduler + FastAPI health endpoint
```

### README Coverage: GOOD

**Main README** (`README.md`):
- High-level architecture ✓
- Quick start with docker-compose ✓
- Tech stack ✓
- Service descriptions (2 lines each) ✓
- Recent changes (March 2026) ✓

**Per-service READMEs:**
- `services/admin/README.md` exists, minimal
- `services/ingestion/README.md` missing
- `services/graph/README.md` missing
- `services/nlp/README.md` missing
- `services/scheduler/README.md` missing

### File Naming Consistency: INCONSISTENT

**Routing/Handler files have mixed naming:**
- `routes.py` (ingestion, admin/app/*, scheduler)
- `router.py` (graph/app/routers/fsma/*)
- `routers/` subdirectory (graph service uses this pattern; ingestion doesn't)
- `_routes.py` suffix (services/ingestion/app/routes_health_metrics.py)

**Models/Schemas have mixed patterns:**
- `pcos_models.py` + `pcos_schemas.py` (admin)
- `models.py` + separate `<domain>_models.py` (graph)
- `sqlalchemy_models.py` (admin, for ORM base)

**Recommendation:**
```
Standardize across all services:
✓ routes.py          (top-level, uses @router.post etc)
✓ routers/           (subdirectory for domain-specific routers)
✓ models.py          (SQLAlchemy ORM)
✓ schemas.py         (Pydantic validation schemas)
✓ service.py         (Business logic; e.g., SupplierOnboardingService)
```

**Risk:** MEDIUM — Developers hunt for files; no runtime impact.

### Documentation of Service Boundaries: MISSING

**What's missing:**
- No `ARCHITECTURE.md` per service (what can this service do, what can't it do)
- No `DEPENDENCY_MAP.md` (which services call which)
- No `ONBOARDING_GUIDE.md` for new devs

**Examples that exist:**
- `docs/specs/FSMA_204_MVP_SPEC.md` ✓
- `docs/LOCAL_SETUP_GUIDE.md` ✓
- `PRODUCTION_ENV_CHECKLIST.md` ✓

**Recommendation:** Add to `/docs/`:
- `DEVELOPER_GUIDE.md` — "New dev: start here"
- `SERVICE_ARCHITECTURE.md` — "What each service does and its API"
- `SERVICE_DEPENDENCY_MAP.md` — Service-to-service call graph

**Risk:** MEDIUM — New developers take 1-2 days to grok service boundaries vs. 2-4 hours with docs.

---

## 7. TESTING & TEST ORGANIZATION

### Structure: CLEAR ✓
```
tests/                          # Root-level integration tests
services/{service}/tests/       # Per-service unit/integration tests
frontend/__tests__/             # Jest tests
```

### Coverage: GOOD
- 16 test directories across 6 backend services
- Example: `services/admin/tests/test_pcos_routes.py` (582 lines)
- Frontend: e2e tests exist (`frontend/tests/e2e/security-audit-fixes.spec.ts`, 678 lines)

### Issue: Test File Size
- `tests/shared/test_audit_logging.py` (893 lines) — Monolithic test file
- `tests/shared/test_data_access_logging.py` (878 lines)
- `tests/shared/test_anomaly_detection.py` (845 lines)

**Recommendation:** Break large test files into smaller suites:
```
tests/shared/audit_logging/
├── test_audit_logging_models.py         (50 lines)
├── test_audit_logging_routes.py         (150 lines)
├── test_audit_logging_integration.py    (200 lines)
```

**Risk:** MEDIUM — Large test files are hard to navigate; test failures are hard to isolate.

---

## SUMMARY TABLE: FINDINGS BY SEVERITY

| Severity | Category | Finding | File/Folder | Action |
|----------|----------|---------|-------------|--------|
| **CRITICAL** | God Files | PCOS domain models in single file | `/services/admin/app/pcos_models.py` (2,231 lines) | Split into 3 files: company/project/schemas |
| **CRITICAL** | Dead Code | Frontend disabled routes never removed | `/frontend/src/app/_disabled/` (13 folders) | Remove from codebase; accessible via git history |
| **HIGH** | God Files | Supplier onboarding routes + logic | `/services/admin/app/supplier_onboarding_routes.py` (1,757 lines) | Extract service layer; routes become thin wrappers |
| **HIGH** | God Files | Ingestion routes lack organization | `/services/ingestion/app/routes.py` (1,511 lines) | Create `routers/` subdirectory; split by domain |
| **HIGH** | Circular Imports | Admin models exposed to ingestion | Admin ↔ Ingestion cross-service coupling | Move PCOS to shared; dependency inversion |
| **MEDIUM** | Dead Code | Unused frontend components | 49 exported components not imported | Audit tree-shaking; prune or move to _deprecated |
| **MEDIUM** | Shared Code | 78 modules approaching limits | `/services/shared/` | Reorganize "Other" 15 files; cap at 60 files |
| **MEDIUM** | File Naming | Inconsistent naming (routes vs. routers) | All services | Standardize: routes.py + routers/ subdirectory |
| **MEDIUM** | Documentation | Missing per-service architecture docs | All services | Add `ARCHITECTURE.md` per service |
| **MEDIUM** | Testing | Test files exceed 800+ lines | `tests/shared/test_*.py` | Break into smaller, focused test files |
| **LOW** | Shared Code | "Other" category miscategorization | `/services/shared/` | Move 5-7 files to proper security/infra buckets |

---

## RECOMMENDATIONS BY PRIORITY

### Sprint 1 (Next 1-2 weeks):
1. ✅ **Move PCOS models to shared** — Removes admin ↔ ingestion coupling
2. ✅ **Create router subdirectory in ingestion** — 211 routes across 1.5 files → organized subdir
3. ✅ **Remove `/frontend/src/app/_disabled/`** — Clean git history, reduce surface area

### Sprint 2 (Weeks 3-4):
4. ✅ **Extract supplier_onboarding_service.py** — Separate concerns in admin routes
5. ✅ **Standardize file naming** across all services (routes.py, models.py, schemas.py, service.py pattern)
6. ✅ **Add per-service README files** (ingestion, graph, nlp, scheduler)

### Sprint 3+ (Weeks 5+):
7. ✅ **Reorganize services/shared** — Move 15 "Other" files into proper categories
8. ✅ **Create developer guide** — DEVELOPER_GUIDE.md, SERVICE_ARCHITECTURE.md
9. ✅ **Refactor large test files** — Break 800+ line test files into 3-4 smaller modules
10. ✅ **Refactor fsma_utils.py** — Split into builders/queries/validators

---

## CONCLUSION

**Overall Assessment: SOLID with maintainability debt**

RegEngine's architecture is well-intentioned: clear service boundaries, shared security libraries, organized testing. However, after 6 prior audits, several god files remain (2,231 lines in pcos_models), cross-service dependencies are tightly coupled, and dead code isn't aggressively pruned.

**Time to grok as new dev:** 2-4 days (with README) vs. 4+ days (without docs)

**Refactor effort to production-ready:** 2-3 sprints (3-4 weeks) for all recommendations.

**Risk of not refactoring:** Increasing friction on feature velocity; PCOS models become increasingly hard to change; cross-service debugging becomes painful.

**Recommend:** Prioritize Sprints 1-2 (entry point clarity, shared ownership model) in next 2-3 weeks before FSMA 204 deadline (July 2028).
