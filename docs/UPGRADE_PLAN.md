# RegEngine — Best-in-Class Upgrade Plan

**Created:** March 2026  
**Source:** Full codebase review — 8 issue categories identified  
**Strategy:** Fix bugs first → security hardening → structural improvements → quality ceiling

---

## Priority Framework

| Priority | Label | Criteria |
|----------|-------|----------|
| P0 | **Blocker** | Runtime crash or data corruption if triggered |
| P1 | **Critical** | Security vulnerability or silent data loss |
| P2 | **High** | Correctness gap or persistent technical debt |
| P3 | **Medium** | Quality / maintainability improvement |

---

## Phase 1 — Bug Fixes (P0/P1) `[x]`

These issues will cause runtime errors or data loss the moment the affected code path is exercised in production. Fix first.

---

### BUG-001 — Broken graph persistence in `RegulatoryEngine._persist_evaluation` · P0

**File:** `kernel/obligation/engine.py:114–181`

**Problem:**  
`_persist_evaluation` accepts an `ObligationEvaluationResult` (a collection-level result) but accesses fields that only exist on `ObligationMatch` (the single-match model):

```python
# These attributes do NOT exist on ObligationEvaluationResult:
result.obligation_id   # ← AttributeError
result.met             # ← AttributeError
result.confidence      # ← AttributeError
result.matched_evidence  # ← AttributeError
result.evaluated_at    # ← AttributeError (field is `timestamp`)
```

**Fix:**  
Rewrite `_persist_evaluation` to iterate over `result.obligation_matches` and create one `ObligationEvaluation` node per match:

```python
def _persist_evaluation(self, result: ObligationEvaluationResult):
    if self.graph is None:
        return
    try:
        with self.graph.session() as session:
            for match in result.obligation_matches:
                session.run("""
                    CREATE (oe:ObligationEvaluation {
                        evaluation_id: $eval_id,
                        obligation_id: $obligation_id,
                        vertical: $vertical,
                        decision_id: $decision_id,
                        met: $met,
                        risk_score: $risk_score,
                        missing_evidence: $missing_evidence,
                        evaluated_at: datetime($evaluated_at)
                    })
                """,
                    eval_id=result.evaluation_id,
                    obligation_id=match.obligation_id,
                    vertical=result.vertical,
                    decision_id=result.decision_id,
                    met=match.met,
                    risk_score=match.risk_score,
                    missing_evidence=match.missing_evidence,
                    evaluated_at=result.timestamp.isoformat()
                )
                # ... relationship creation using match.obligation_id
    except Exception as e:
        logger.error("persist_evaluation_failed", error=str(e))
```

**Test:** Add `kernel/obligation/tests/test_engine_persistence.py` — mock a `MagicMock` graph client and assert `.run()` is called once per `obligation_match`.

---

### BUG-002 — Broken import in `kernel/monitoring/scoring.py` · P0

**File:** `kernel/monitoring/scoring.py:8`

**Problem:**  
```python
from .models import ComplianceScore, RiskWeight, ObligationMatch, RiskLevel
```
`kernel/monitoring/models.py` **does not exist**. `ComplianceScore` and `RiskWeight` live in `kernel/models.py`; `ObligationMatch` and `RiskLevel` live in `kernel/obligation/models.py`. Any call to `calculate_compliance_score()` will raise `ModuleNotFoundError`.

**Fix:**
```python
# kernel/monitoring/scoring.py
from kernel.models import ComplianceScore, RiskWeight
from kernel.obligation.models import ObligationMatch, RiskLevel
```

**Test:** Add `kernel/monitoring/tests/test_scoring.py` — call `calculate_compliance_score()` with a list of synthetic `ObligationMatch` objects and assert the returned `ComplianceScore.score` is in `[0.0, 100.0]`.

---

### BUG-003 — Hardcoded secret in `docker-compose.yml` · P1

**File:** `docker-compose.yml:57`

**Problem:**  
```yaml
SCHEDULER_API_KEY: regengine-universal-test-key-2026
```
A plaintext API key is committed to source control. The rest of the compose file correctly uses `${VAR:?error}` mandatory-substitution syntax. This key is inconsistent with the security posture of the rest of the file.

**Fix:**
```yaml
SCHEDULER_API_KEY: ${SCHEDULER_API_KEY:?SCHEDULER_API_KEY must be set}
```

Add `SCHEDULER_API_KEY` to `.env.example` with a generation instruction:
```
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
SCHEDULER_API_KEY=
```

**Test:** Run `grep -r "regengine-universal-test-key" .` — should return no matches after the fix.

---

### BUG-004 — PostgreSQL password defaults to `"regengine"` in compose · P1

**File:** `docker-compose.yml:450`

**Problem:**  
```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-regengine}
```
Uses `:-` (silent default) instead of `:?` (fail if unset). Unlike `NEO4J_PASSWORD` and `ADMIN_MASTER_KEY`, a weak default can silently reach a staging or production environment. The `DATABASE_URL` on line 22 also embeds the same default credential.

**Fix — compose:**
```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}
```

**Fix — DATABASE_URL default:**  
Remove the embedded credential from the default `DATABASE_URL` string. Instead, require it from the environment:
```yaml
DATABASE_URL: ${DATABASE_URL:?DATABASE_URL must be set}
```

Add to `.env.example`:
```
POSTGRES_PASSWORD=
DATABASE_URL=postgresql://regengine:<password>@postgres:5432/regengine
```

---

### BUG-005 — Invalid Groq model identifier in `MappingEngine` · P1

**File:** `kernel/graph.py:32`

**Problem:**  
```python
self.llm = ChatGroq(model="grok-beta", temperature=0)
```
`"grok-beta"` is not a valid Groq SDK model identifier (Groq hosts Llama, Mixtral, Gemma). This is a confusion with xAI's Grok. The `__init__` silently swallows the error at line 34 (`except Exception: self.llm = None`), meaning the mapping engine will always be disabled in production with no visible failure signal.

**Fix — use a real Groq model, make it configurable:**
```python
_groq_model = os.getenv("GROQ_MODEL", "llama3-70b-8192")
self.llm = ChatGroq(model=_groq_model, temperature=0)
```

Add `GROQ_MODEL` to `.env.example` with valid options documented.

**Secondary fix:** Replace the bare `except Exception: self.llm = None` with:
```python
except Exception as e:
    logger.warning("groq_init_failed", model=_groq_model, error=str(e))
    self.llm = None
```

---

### BUG-006 — Pydantic v2 incompatible `min_items` on `required_evidence` field · P0

**Files:** `kernel/obligation/models.py:51`, `kernel/models.py:53`

**Problem:**  
```python
required_evidence: List[str] = Field(..., min_items=1, description="Required evidence fields")
```
`min_items` was a Pydantic v1 argument removed in v2. The project targets `pydantic>=2.6.0`. This silently has **no effect** — an empty `required_evidence: []` list will pass validation without error, meaning obligations with no required evidence will evaluate as always-met, corrupting compliance scoring. The LSP confirms the error on both files.

**Fix — use Pydantic v2 `Annotated` syntax:**
```python
from typing import Annotated
from pydantic import Field
from annotated_types import Len

required_evidence: Annotated[List[str], Field(min_length=1, description="Required evidence fields")]
```

Or the simpler v2 approach:
```python
required_evidence: List[str] = Field(..., min_length=1, description="Required evidence fields")
```

Apply to both `kernel/obligation/models.py:51` and `kernel/models.py:53`.

**Test:** Add a test that attempts to construct an `ObligationDefinition` with `required_evidence=[]` and asserts a `ValidationError` is raised.

---

## Phase 2 — Security Hardening (P1) `[ ]`

---

### SEC-001 — Refresh token flow does not verify tenant status · P1

**File:** `services/admin/app/auth_routes.py:218–220`

**Problem:**  
On token refresh, the active tenant is taken as the first membership row without checking `TenantModel.status`. A tenant that has been suspended or archived will continue issuing valid access tokens to all its users through the refresh flow indefinitely.

```python
# Current — no status check
memberships = db.execute(stmt_mem).scalars().all()
active_tenant_id = memberships[0].tenant_id if memberships else None
```

**Fix — join to TenantModel and filter on status:**
```python
stmt_mem = (
    select(MembershipModel, TenantModel)
    .join(TenantModel, MembershipModel.tenant_id == TenantModel.id)
    .where(
        MembershipModel.user_id == user.id,
        MembershipModel.is_active == True,
        TenantModel.status == "active"
    )
)
results = db.execute(stmt_mem).all()
active_tenant_id = results[0][1].id if results else None
```

If `active_tenant_id` is `None` after filtering (all tenants suspended), return a 403 with `"No active tenant available"`.

**Test:** `services/admin/tests/test_auth_refresh_tenant_status.py` — create a user whose only tenant is `status="suspended"`, call `/auth/refresh`, assert 403.

---

### SEC-002 — Audit `services/shared/` for dead security modules · P2

**File:** `services/shared/` (87 files)

**Problem:**  
The shared module contains security files that may not be imported anywhere in active code paths:
- `ldap_security.py` — no LDAP infrastructure in compose
- `xml_security.py` — no XML ingestion paths evident
- `deserialization_security.py` — Python pickle not used
- `template_security.py` — no server-side templating
- `concurrency_security.py`, `memory_security.py` — unclear consumers

Dead security code is not neutral: it increases review burden, can give false assurance, and may contain incorrect implementations that are never tested.

**Fix process:**
1. Run `grep -rn "from shared\.<module>" services/ kernel/` for each suspect file
2. For files with zero imports: move to `services/shared/archive/` with a dated comment
3. For files with one import: evaluate if the import should be removed or the module kept
4. Update `services/shared/__init__.py` to only export actively used symbols

**Deliverable:** A comment header in each remaining file listing its known consumers.

---

## Phase 3 — Structural Improvements (P2) `[ ]`

---

### STR-001 — Consolidate duplicate model definitions · P2

**Files:**
- `kernel/models.py` — defines `Regulator`, `RegulatoryDomain`, `RiskLevel`, `ObligationDefinition`, `ObligationMatch`, `ObligationEvaluationResult`, `RiskWeight`, `ComplianceScore`
- `kernel/obligation/models.py` — defines same set (minus `RiskWeight`, `ComplianceScore`, plus divergences)

**Divergences that must be resolved before merge:**

| Symbol | `kernel/models.py` | `kernel/obligation/models.py` |
|--------|--------------------|-------------------------------|
| `Regulator` | Includes `FDA` | Does not include `FDA` |
| `RegulatoryDomain` | Includes `FSMA` | Does not include `FSMA` |
| `ComplianceScore.vertical` | `default="fsma"` | Not defined here |

**Migration plan:**

1. **Extend `kernel/obligation/models.py`** to be the single source of truth:
   - Add `FDA` to `Regulator`
   - Add `FSMA` to `RegulatoryDomain`
   - Move `RiskWeight` and `ComplianceScore` from `kernel/models.py` into `kernel/obligation/models.py`
   - Set `ComplianceScore.vertical` default to `"fsma"` (documents intent)

2. **Rewrite `kernel/models.py`** to be a pure re-export shim for backward compatibility:
   ```python
   # kernel/models.py — compatibility shim, do not add new definitions here
   from kernel.obligation.models import (
       Regulator, RegulatoryDomain, RiskLevel,
       ObligationDefinition, ObligationMatch, ObligationEvaluationResult,
       RiskWeight, ComplianceScore, ObligationCoverageReport
   )
   __all__ = [...]
   ```

3. **Fix `kernel/monitoring/scoring.py`** to import from `kernel.obligation.models` (also fixes BUG-002).

4. **Run full test suite** after migration to catch any import regressions.

---

### STR-002 — Fix duplicate log calls in `compliance_routes.py` · P2

**File:** `services/admin/app/compliance_routes.py` — repeated pattern across ~12 exception handlers

**Problem:**  
Each handler calls `logger.error(...)` then immediately `logger.exception(...)` then raises an `HTTPException`. This produces two log entries per error, the second of which has the wrong exception in its traceback (it captures the `HTTPException` being constructed, not the original cause).

```python
# Current — duplicated, second traceback is wrong
except Exception as e:
    logger.error("get_status_failed", tenant_id=tenant_id, error=str(e))
    logger.exception("endpoint_error", error=str(e)); raise HTTPException(status_code=500, ...)
```

**Fix — single structured log with exception context:**
```python
except Exception as e:
    logger.exception("get_status_failed", tenant_id=tenant_id, error=str(e))
    raise HTTPException(status_code=500, detail="Internal server error")
```

`structlog`'s `logger.exception()` automatically captures `exc_info=True`. One call, correct traceback, no duplication. Apply consistently across all 12+ handlers in the file.

**Automation:** Write a `scripts/fix_duplicate_log_handlers.py` script that uses `ast` to detect and report the pattern across all route files, to catch future regressions.

---

### STR-003 — Make `RegulatoryEngine` initialization fail-fast on bad verticals dir · P2

**File:** `kernel/obligation/engine.py:28–43`, `kernel/obligation/routes.py:24–25`

**Problem:**  
The engine is initialized at module import time in `routes.py` with a path that may not exist:
```python
VERTICALS_DIR = Path(os.getenv("REGENGINE_VERTICALS_DIR", "./verticals"))
engine = RegulatoryEngine(verticals_dir=VERTICALS_DIR)
```
If `./verticals` doesn't exist, the service starts silently. The failure only surfaces when `/evaluate` is called and raises `FileNotFoundError`. This masks misconfiguration.

**Fix — validate on startup:**
```python
# In RegulatoryEngine.__init__:
if not self.verticals_dir.exists():
    raise FileNotFoundError(
        f"Verticals directory not found: {self.verticals_dir}. "
        "Set REGENGINE_VERTICALS_DIR to the correct path."
    )
```

Move engine initialization into the FastAPI `lifespan` context so a missing verticals dir fails startup cleanly rather than at the first request.

---

## Phase 4 — Quality Ceiling (P3) `[ ]`

These items elevate the codebase from "working" to "best in class" — production observability, test coverage, and developer experience.

---

### QUAL-001 — Add structured logging to `kernel/obligation/evaluator.py` · P3

**File:** `kernel/obligation/evaluator.py`

**Problem:**  
Uses `logging.getLogger(__name__)` (stdlib) while the rest of the service uses `structlog`. Log lines are unstructured strings with f-string interpolation, making them unsearchable in log aggregators.

**Fix — migrate to structlog with bound context:**
```python
import structlog
logger = structlog.get_logger("obligation.evaluator")

# In evaluate_decision:
log = logger.bind(decision_id=decision_id, decision_type=decision_type, vertical=vertical)
log.info("evaluation_started")
...
log.info("evaluation_complete",
    met=met_count,
    total=len(obligation_matches),
    coverage_pct=round(coverage_percent, 1),
    risk_level=risk_level.value
)
```

Apply the same pattern to `engine.py` and `regulation_loader.py`.

---

### QUAL-002 — Add `obligation_id` to `ObligationMatch.risk_score` comment contract · P3

**File:** `kernel/obligation/evaluator.py:182–188`

**Problem:**  
The risk score formula comment says `"Range: 0.5-1.0 for violations"` but doesn't document why violations start at 0.5 rather than 0.0 (the business rationale: any violation carries at least medium risk regardless of evidence completeness). This is non-obvious and has caused confusion in the model mismatch above.

**Fix — add explicit docstring:**
```python
# Risk floor for any violation is 0.5 (medium risk):
# Even a single missing field is a compliance gap, not a minor issue.
# Full missing evidence maps to 1.0 (critical).
risk_score = 0.5 + (missing_ratio * 0.5)  # [0.5, 1.0]
```

---

### QUAL-003 — `MappingEngine` LLM confidence score is hardcoded · P3

**File:** `kernel/graph.py:101`

**Problem:**  
```python
"confidence": 0.9,
"justification": "Semantic harmonization via Grok-beta"
```
Confidence is hardcoded at `0.9` for every LLM match, and the justification references `"Grok-beta"` (already broken — see BUG-005). There is no mechanism for the LLM to express uncertainty.

**Fix:**
1. Update the prompt to ask the LLM to return `index:confidence` pairs (e.g., `"0:0.85,2:0.60"`)
2. Parse confidence per match
3. Set a minimum confidence threshold (e.g., `0.7`) — skip mappings below threshold
4. Update justification to reference the actual model used:
   ```python
   "justification": f"Semantic harmonization via {_groq_model}"
   ```

---

### QUAL-004 — Add test coverage for `kernel/evidence/` chain verification · P3

**File:** `kernel/evidence/` — no tests exist for `verify.py` or the full chain walk

**Tests to add in `kernel/evidence/tests/`:**

| Test | What it verifies |
|------|------------------|
| `test_hash_chain_integrity` | Sequential envelopes link correctly via `previous_hash` |
| `test_tamper_detection` | Modifying `evidence_payload` causes hash mismatch |
| `test_merkle_proof_roundtrip` | `generate_merkle_proof` + `verify_merkle_proof` round-trips cleanly |
| `test_chain_break_detected` | Removing a middle envelope raises a chain break |
| `test_empty_payload_hash` | Edge case: empty dict produces stable hash |

---

### QUAL-005 — Add `pyproject.toml` test path for `kernel/` · P3

**File:** `pyproject.toml:115–122`

**Problem:**  
`kernel/` tests (e.g., `kernel/obligation/tests/`, `kernel/monitoring/tests/`) are not in the `testpaths` list. They will not run with a bare `pytest` invocation.

**Fix:**
```toml
testpaths = [
    "tests",
    "kernel/obligation/tests",
    "kernel/monitoring/tests",
    "kernel/evidence/tests",
    "services/admin/tests",
    "services/graph/tests",
    "services/ingestion/tests",
    "services/nlp/tests",
    "services/scheduler/tests",
]
```

---

## Summary Table

| ID | Phase | Priority | File(s) | Status |
|----|-------|----------|---------|--------|
| BUG-001 | 1 | P0 | `kernel/obligation/engine.py` | `[x]` |
| BUG-002 | 1 | P0 | `kernel/monitoring/scoring.py` | `[x]` |
| BUG-003 | 1 | P1 | `docker-compose.yml` | `[x]` |
| BUG-004 | 1 | P1 | `docker-compose.yml` | `[x]` |
| BUG-005 | 1 | P1 | `kernel/graph.py` | `[x]` |
| BUG-006 | 1 | P0 | `kernel/obligation/models.py`, `kernel/models.py` | `[x]` |
| SEC-001 | 2 | P1 | `services/admin/app/auth_routes.py` | `[x]` |
| SEC-002 | 2 | P2 | `services/shared/` | `[x]` | <!-- No dead modules found - all in use or removed |
| STR-001 | 3 | P2 | `kernel/models.py`, `kernel/obligation/models.py` | `[x]` | <!-- Consolidated models, obligation is source of truth |
| STR-002 | 3 | P2 | `services/admin/app/compliance_routes.py` | `[x]` |
| STR-003 | 3 | P2 | `kernel/obligation/engine.py`, `routes.py` | `[x]` | <!-- Already has fail-fast in __init__ --> |
| QUAL-001 | 4 | P3 | `kernel/obligation/evaluator.py` | `[x]` | <!-- Migrated to structlog |
| QUAL-002 | 4 | P3 | `kernel/obligation/evaluator.py` | `[x]` | <!-- Added risk floor rationale |
| QUAL-003 | 4 | P3 | `kernel/graph.py` | `[x]` | <!-- LLM returns confidence scores, min threshold 0.7 |
| QUAL-004 | 4 | P3 | `kernel/evidence/tests/` | `[x]` | <!-- Added 5 test suites |
| QUAL-005 | 4 | P3 | `pyproject.toml` | `[x]` | <!-- Added kernel test paths |

---

## Execution Notes

- **BUG-006 and BUG-001 are the highest-risk items** — BUG-006 silently accepts invalid obligation definitions; BUG-001 crashes graph persistence. Both can cause silent data integrity issues.
- **Phase 1 items can be fixed independently** — none depend on each other, safe to parallelize across engineers.
- **STR-001 (model consolidation) must come after BUG-002** — fixing the import first will reveal which files need updating in the merge.
- **SEC-002 (shared module audit) should be a dedicated PR** — it is low risk but high surface area; keep it isolated so it's easy to revert.
- **QUAL-004 and QUAL-005 should land together** — adding tests without adding the test path to `pyproject.toml` will silently skip them in CI.
