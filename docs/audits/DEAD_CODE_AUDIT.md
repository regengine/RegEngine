# RegEngine Dead Code Sweep Report
**Date: March 9, 2026**

---

## SUMMARY
This comprehensive dead code audit identified **10 categories of issues**:
- **1 completely orphaned service** (opportunity-api)
- **1 duplicate test directory** (test_shared/ vs shared_models/)
- **1 large commented code block** (~30 lines of test code)
- **3 undocumented but actively used environment variables**
- **3 documented but never used environment variables**
- **Multiple environment variables used in tests but not documented**

---

## 1. ORPHANED SERVICES

### Issue: opportunity-api service referenced but never built

**Status:** HIGH PRIORITY - Breaks production deployments

**Locations:**
- `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/docker-compose.prod.yml` - lines 137-155
  - References: `services.opportunity-api`
  - Image: `ghcr.io/regengine/opportunity-api:${IMAGE_TAG:-latest}`
  - Dockerfile: `./services/opportunity/Dockerfile` (does not exist)

**Finding:**
- The `opportunity-api` service is defined in `docker-compose.prod.yml`
- No corresponding service directory exists in `/services/`
- No Dockerfile exists for building this service
- **Impact:** Production deployments using `docker-compose.prod.yml` will fail when trying to start this service

**Recommendation:** SAFE TO REMOVE
- Delete lines 137-155 from `docker-compose.prod.yml`
- This service appears to be from an old feature branch that was never completed

---

## 2. STALE COMMENTED-OUT CODE BLOCKS

### Issue: ~30 lines of commented test code (Phase 2b golden corpus)

**Location:** 
- `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/tests/data_integrity/test_fsma_204_phase_2b_structure.py` - lines 36-63 and 69-96

**Details:**
- **Lines 36-63 (28 lines):** Entire ingest/polling/verification workflow commented out
  ```python
  # payload = {"url": "https://www.fda.gov/media/163126/download", "source_type": "regulation"}
  # response = requests.post(f"{INGEST_SERVICE_URL}/ingest", json=payload)
  # assert response.status_code == 202
  # ... (25+ more lines of commented code)
  ```
- **Lines 69-96 (28 lines):** Helper functions and validation assertions commented out
  ```python
  # def get_fact(key):
  #     return next((f for f in facts if f["fact_key"] == key), None)
  # ... (20+ more lines)
  ```

**Context:** 
- The test file itself is a skeleton (methods end with `pass`)
- Comments note: "This test will require the full Docker stack"
- This appears to be draft/WIP code from Phase 2b testing

**Recommendation:** SAFE TO REMOVE
- Delete lines 36-98 (entire commented section)
- The active test code is only the method signatures and pass statements
- No production logic depends on this commented code

---

## 3. DUPLICATE TEST DIRECTORIES

### Issue: Two nearly-identical test directories for same modules

**Location:**
- `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/tests/test_shared/` (ACTIVE)
- `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/tests/shared_models/` (STALE)

**Files Affected:**
```
test_shared/test_audit.py          (7,769 bytes) - ACTIVE
shared_models/test_audit.py        (7,874 bytes) - DUPLICATE
test_shared/test_schemas.py        (10,493 bytes) - ACTIVE
shared_models/test_schemas.py      (12,029 bytes) - DUPLICATE
```

**Key Differences:**
- `shared_models/test_audit.py` has extra imports: `sys`, `Path`, and custom sys.path manipulation
- `shared_models/` versions are slightly outdated (longer file sizes, different structure)
- `test_shared/` is the modern version being used

**Evidence:**
- No CI workflow references `shared_models/`
- No recent commits to `shared_models/` (vs active changes to `test_shared/`)
- The `test_shared/` directory has cleaner imports (direct `from shared.audit import`)

**Recommendation:** SAFE TO REMOVE
- Delete the entire `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/tests/shared_models/` directory
- Keep `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/tests/test_shared/`

---

## 4. UNDOCUMENTED ENVIRONMENT VARIABLES (IN .env.example)

### Issue: Variables used in code but not documented in .env.example

**Critical (production-impact):**
```
ENTERTAINMENT_DATABASE_URL    - Used in services/admin (line 105 of docker-compose.yml)
ADMIN_DATABASE_URL            - Used in services (async driver version)
INTERNAL_SERVICE_SECRET       - Referenced in tests/security/conftest.py (line 10)
SCHEDULER_API_KEY             - Used in docker-compose.yml (line 57)
REGENGINE_INTERNAL_SECRET     - Mentioned in docker-compose.yml but not used in .env.example
```

**Test-specific (low-impact but confusing):**
```
DOCKER_RUNNING                - Used in tests/data_integrity/test_fsma_204_phase_2b_structure.py:25
TEST_DB_URL                   - Used in tests/security/test_strict_ciam_compliance.py
ADMIN_FALLBACK_SQLITE         - Used in tests/admin/test_database.py
AUTH_TEST_BYPASS_TENANT_ID    - Defined in .env.example as comment, not documented
REGENGINE_TEST_API_KEY        - Used in FSMA 204 test phases
```

**Recommendation:** ADD TO .env.example
- Add documented entries for all the above variables
- Most are intentionally test-only (prefix with `#` or note as optional)

---

## 5. DOCUMENTED BUT UNUSED ENVIRONMENT VARIABLES

### Issue: Variables in .env.example that are never referenced in code

**Variables Never Used:**
```
REGULATORY_DISCOVERY_INTERVAL   (line 55) - Intended for future regulatory scraper
REGULATORY_POLITE_DELAY         (line 56) - Intended for future regulatory scraper
SCHEDULER_API_KEY               (documented, but only used in docker-compose references)
```

**Impact:** LOW - These are mostly future-proofing placeholders

**Recommendation:** Keep (for now)
- These are intentionally reserved for upcoming features
- Mark with comments: `# Reserved for future use`
- Consider moving to a separate `FUTURE_FEATURES` section if .env.example grows

---

## 6. STALE DOCKER-COMPOSE FILES

### docker-compose.test.yml (Explicit stub)

**Location:** `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/docker-compose.test.yml`

**Status:**
- File explicitly notes: `STUB: Not yet wired to real test infrastructure`
- Contains minimal setup (postgres + redis only)
- Not referenced in any CI workflow

**Recommendation:** Document or remove
- Either complete the implementation (wire up all services)
- Or delete and document that integration tests use `docker-compose.yml`

### docker-compose.fsma.yml (Minimal override)

**Location:** `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/docker-compose.fsma.yml`

**Status:**
- Very small file (29 lines)
- Extends base compose to disable OTEL for FSMA testing
- Low value; functionality can be achieved with env var override

**Recommendation:** Document purpose or consolidate
- Add clear comment about when/how to use this file
- Consider if ENABLE_OTEL=false in base .env is simpler

---

## 7. CONFTEST ENV VAR SETUP (SCATTERED DEFINITIONS)

### Issue: Test environment variables defined in multiple conftest.py files

**Locations:**
- `tests/conftest.py` - Sets: ADMIN_DATABASE_URL, DATABASE_URL, ENTERTAINMENT_DATABASE_URL, AUTH_SECRET_KEY, ADMIN_MASTER_KEY, AUTH_TEST_BYPASS_TOKEN, ENVIRONMENT
- `tests/security/conftest.py` - Sets: ENVIRONMENT, LOG_LEVEL, INTERNAL_SERVICE_SECRET
- `tests/integration/conftest.py` - References: TEST_ADMIN_URL, TEST_ENERGY_URL, etc. (with hardcoded defaults)

**Issue:** 
- Duplicated env var initialization (e.g., ENVIRONMENT set in two places)
- No single source of truth for test environment configuration
- Maintenance burden if test infrastructure changes

**Recommendation:** Consolidate
- Create a `tests/env_config.py` module with all test-specific defaults
- Import and use in all conftest.py files
- Reduces duplication and makes dependencies clear

---

## 8. MISSING MODULES IN OPPORTUNITY/ARBITRAGE TESTS

### Issue: Test for non-existent module structure

**Location:** `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/tests/opportunity/test_arbitrage_gaps.py`

**Status:**
- Test file exists but tests "opportunity" module
- No corresponding `services/opportunity/` directory
- Cannot verify what this test is actually testing

**Note:** This may be intentional (future feature) or orphaned

**Recommendation:** Verify intent
- If opportunity service is planned: add to backlog/roadmap
- If abandoned: move test to `tests/archived/` or delete

---

## 9. STALE REFERENCES IN DOCKER-COMPOSE

### References to non-existent services in comments

**Location:** `/sessions/cool-fervent-davinci/mnt/GitHub/RegEngine/docker-compose.yml` - line 120

**Content:**
```yaml
# finance-api: REMOVED — services/finance_api/ directory does not exist.
# Re-add when the Finance service is implemented.
```

**Status:** 
- Correctly documented as removed
- Clean note for future developers
- No broken references

**Recommendation:** Keep as-is
- This is good documentation of past cleanup

---

## 10. WORKFLOW/CI REFERENCES

### No major issues found

**Status:**
- `.github/workflows/backend-ci.yml` correctly tests only existing services (admin, compliance, graph, ingestion, nlp, scheduler)
- No references to opportunity-api or finance-api in CI
- Does NOT test `tests/test_shared/` or `tests/shared_models/` directly (runs entire test suite)

**Note:** Backend-CI may run both test_shared and shared_models if they're both in the test discovery path. This is why removing shared_models/ is safe.

---

## REMEDIATION CHECKLIST

### IMMEDIATE (Safe, high-value cleanup)
- [ ] Remove `opportunity-api` service from `docker-compose.prod.yml` (lines 137-155)
- [ ] Remove commented code block from `test_fsma_204_phase_2b_structure.py` (lines 36-98)
- [ ] Delete `/tests/shared_models/` directory entirely

### SHORT-TERM (Documentation/cleanup)
- [ ] Add missing env vars to `.env.example`:
  - ENTERTAINMENT_DATABASE_URL
  - ADMIN_DATABASE_URL
  - INTERNAL_SERVICE_SECRET
  - SCHEDULER_API_KEY
  - TEST_* variables (mark as test-only)
  
- [ ] Consolidate test env configuration into `tests/env_config.py`
- [ ] Add purpose comments to `docker-compose.test.yml` and `docker-compose.fsma.yml`

### VERIFICATION NEEDED
- [ ] Verify `tests/opportunity/test_arbitrage_gaps.py` is intentional or archived
- [ ] Run full test suite after deletions to verify no broken imports
- [ ] Check if `REGULATORY_DISCOVERY_INTERVAL` and `REGULATORY_POLITE_DELAY` are truly unused or future-planned

---

## NOTES FOR CHRISTOPHER

**Total findings: 10 major issues**

**Safe to remove immediately:**
1. opportunity-api service definition (~20 lines)
2. Commented Phase 2b test code (~60 lines)
3. shared_models/ test directory (~20 files)

**This cleans up roughly 100-150 lines of dead code and reduces confusion around duplicate test dirs.**

**Estimated impact:** 
- Reduces maintenance burden
- Clarifies which test files are active
- Prevents future prod deployment failures from opportunity-api references

