# PCOS Routes Decomposition Plan

**File:** `services/admin/app/pcos_routes.py`  
**Original:** 3,266 lines, 86 outline items, single file  
**Final:** 28-line shim (re-exports `app.pcos.router`)  
**Status:** ✅ COMPLETE — all endpoints extracted  

---

## Strategy: Sub-Router Package

Created `services/admin/app/pcos/` as a package with domain-specific sub-routers.
The barrel `__init__.py` re-exports a unified `router` object. `main.py` imports
directly from `app.pcos`:

```python
# main.py
from app.pcos import router as pcos_router
app.include_router(pcos_router)
```

The original `pcos_routes.py` is a backward-compatible shim:

```python
# pcos_routes.py (transition shim)
from .pcos import router  # noqa: F401
```

---

## Final Module Split

| Module | Routes | Lines | Description |
|--------|--------|-------|-------------|
| `pcos/_shared.py` | `get_pcos_tenant_context` | 39 | Shared dependency |
| `pcos/dashboard.py` | 1 endpoint | 102 | Dashboard metrics |
| `pcos/entities.py` | 16 endpoints | 596 | Companies, Projects, Locations, People, Engagements, Tasks |
| `pcos/gate.py` | 2 endpoints | 142 | Gate status & greenlight |
| `pcos/evidence.py` | 7 endpoints | 131 | Evidence, documents, risks, guidance |
| `pcos/budget.py` | 7 endpoints | 176 | Budgets, rate validation, tax credits, fringes |
| `pcos/compliance.py` | 12 endpoints | 262 | Forms, classification, paperwork, snapshots, audit |
| `pcos/authority.py` | 8 endpoints | 350 | Authority docs, facts, lineage, verdicts |
| `pcos/governance.py` | 6 endpoints | 170 | Schema version, analysis runs, corrections |
| `pcos/__init__.py` | Barrel | 34 | Merges all 8 sub-routers |

**Total:** 59 endpoints across 10 files (2,002 lines) + 28-line shim.

---

## Barrel Pattern (`pcos/__init__.py`)

```python
from fastapi import APIRouter
from .governance import router as governance_router
from .authority import router as authority_router
from .dashboard import router as dashboard_router
from .gate import router as gate_router
from .entities import router as entities_router
from .evidence import router as evidence_router
from .budget import router as budget_router
from .compliance import router as compliance_router

router = APIRouter(prefix="/pcos", tags=["Production Compliance OS"])
router.include_router(governance_router)
router.include_router(authority_router)
router.include_router(dashboard_router)
router.include_router(gate_router)
router.include_router(entities_router)
router.include_router(evidence_router)
router.include_router(budget_router)
router.include_router(compliance_router)
```

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Tests import `app.pcos_routes.router` | Shim `pcos_routes.py` re-exports the barrel router |
| Tests mock `app.pcos_routes.get_pcos_tenant_context` | `_shared.py` exports it; shim re-exports too |
| Route ordering matters for path conflicts | Sub-routers don't have prefix conflicts (each has unique paths) |
| 5 test files depend on current structure | Run full test suite after each sub-module extraction |

---

## Execution Order

1. ✅ **Prep:** Create `pcos/` package with `_shared.py` (shared deps)
2. ✅ **Phase 1:** Extract `governance.py` (~165 lines)
3. ✅ **Phase 2:** Extract `authority.py` (~330 lines)
4. ✅ **Phase 3:** Extract `dashboard.py` (standalone)
5. ✅ **Phase 4:** Extract `gate.py` (standalone)
6. ✅ **Phase 5:** Extract `evidence.py` (document upload, risks, guidance)
7. ✅ **Phase 6:** Extract `budget.py` (financial sub-domain)
8. ✅ **Phase 7:** Extract `compliance.py` (forms, classification, paperwork, snapshots, audit)
9. ✅ **Phase 8:** Extract `entities.py` (CRUD — companies, projects, people, locations, engagements, tasks)
10. ✅ **Phase 9:** Replace original `pcos_routes.py` with shim; update `main.py` to single import
11. **Phase 10:** Run all 5 test files, fix import paths (pending)

---

## Bug Fixed During Analysis

Duplicate error check removed from `extract_fact_from_authority()` (lines 2944-2951).
The same `if not result.get("success")` block was repeated twice.
