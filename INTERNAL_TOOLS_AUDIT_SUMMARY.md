# RegEngine Internal Tools Audit Report

> Generated: 2025-12-02

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Internal Tools Identified | 15 |
| Incomplete Internal Tools | 12 |
| High Priority Tools | 5 |

### High Priority Tools Requiring Immediate Attention

1. **State Registry Scrapers** - 5 of 7 scrapers return empty bytes
2. **Chaos Engineering Data Validator** - Data integrity checks are stubbed
3. **Provenance Replay Auditor** - Missing batch capability and audit logging
4. **Tenant CLI Tool (regctl)** - PostgreSQL schema creation is stubbed
5. **Scheduler/Auto-Ingestion** - ENTIRE SERVICE DOES NOT EXIST

## Systemic Patterns Observed

1. **Placeholder Implementations** - Many functions contain `pass` or return empty data
2. **Missing Scheduled Infrastructure** - No cron/scheduler service exists
3. **Import Path Issues** - Hard-coded paths like `/home/user/RegEngine`
4. **Missing Docker Compose Entries** - Compliance service not in stack
5. **Test Coverage Gaps** - Internal tools have no dedicated tests

---

## Tool-by-Tool Summary

### 1. State Registry Scrapers ⚠️ CRITICAL

**Location:** `services/ingestion/app/scrapers/state_adaptors/`

**Status:** 5 of 7 scrapers return `b""` (empty bytes)

| Scraper | Jurisdiction | Status |
|---------|-------------|--------|
| nydfs.py | US-NY | ✅ Implemented |
| cppa.py | US-CA | ❌ Stub |
| fl_rss.py | US-FL | ❌ Stub |
| nj_gaming.py | US-NJ | ❌ Stub |
| nv_gaming.py | US-NV | ❌ Stub |
| tx_rss.py | US-TX | ❌ Stub |

**Fix:** Copy implementation pattern from `nydfs.py` to other scrapers

---

### 2. Chaos Engineering Data Validator ⚠️ HIGH

**Location:** `scripts/chaos_runner.py`

**Status:** `_validate_data_integrity()` returns `True` always (contains TODO comment)

**Risk:** False confidence in system resilience during chaos tests

**Fix:** Implement actual Neo4j/PostgreSQL/Kafka verification queries

---

### 3. Provenance Replay Auditor ⚠️ HIGH

**Location:** `services/internal/provenance_replay.py`, `scripts/audit/verify_provenance.py`

**Status:** Functional but limited to single-provision verification

**Missing:**
- Batch audit capability
- Audit trail logging
- Support for all extractor frameworks

---

### 4. Tenant CLI Tool (regctl) ⚠️ CRITICAL

**Location:** `scripts/regctl/tenant.py`

**Status:** PostgreSQL operations are stubs with `pass`

**Broken Functions:**
- `_create_postgres_schema()` 
- `_delete_postgres_schema()`

**Fix:** Implement SQLAlchemy schema creation

---

### 5. Scheduler Service ⚠️ CRITICAL

**Location:** `services/scheduler/` (DOES NOT EXIST)

**Status:** The README explicitly states this is missing

**Impact:** No automated regulatory document ingestion

**Fix:** Create new FastAPI service with APScheduler

---

### 6. Demo Data Loader ⚠️ HIGH

**Location:** `scripts/demo/load_demo_data.py`

**Status:** Imports non-existent modules

**Broken Imports:**
- `services/graph/app/models/tenant_nodes` (doesn't exist)
- `services/graph/app/overlay_writer` (doesn't exist)

---

### 7. Secrets Rotation Tool

**Location:** `scripts/rotate_secrets_to_aws.py`, `scripts/sync_prod_secrets.py`

**Status:** Initial upload works, but no rotation/renewal

**Missing:**
- Secret versioning
- Service integration to pull from Secrets Manager

---

### 8. Launch Orchestrator

**Location:** `launch_orchestrator/orchestrator.py`

**Status:** Commands don't execute actual deployments (dry-run only behavior)

---

### 9. Compliance Checklist Engine ⚠️ HIGH

**Location:** `services/compliance/`

**Status:** Service NOT included in docker-compose.yml

**Fix:** Add to docker-compose or run via `uvicorn services.compliance.main:app --port 8500`

---

### 10. Document Ingestion CLI

**Location:** `scripts/ingest_document.py`

**Status:** PDF extraction returns placeholder text

**Missing:** Actual PyPDF2/pdfplumber integration

---

### 11. FSMA 204 Compliance Engine ⚠️ CRITICAL

**Location:** `services/compliance/fsma_engine.py`

**Status:** References non-existent `fsma_204.yaml` file

**Fix:** Create `industry_plugins/food_beverage/fsma_204.yaml`

---

### 12. Seed Audit Record Tool

**Location:** `scripts/demo/seed_audit_record.py`

**Status:** Hard-coded paths break in CI

---

## Recommended Priority Order

### Phase 1: Critical Path (Week 1)
1. Fix state scrapers to return actual content
2. Create scheduler service
3. Add compliance service to docker-compose
4. Create missing YAML definition files

### Phase 2: Demo Readiness (Week 2)
1. Fix demo data loader imports
2. Implement PDF extraction
3. Fix tenant CLI PostgreSQL operations

### Phase 3: Production Hardening (Week 3)
1. Implement chaos data integrity checks
2. Add batch provenance auditing
3. Complete secrets rotation workflow

---

## Detailed JSON Report

See `INTERNAL_TOOLS_AUDIT.json` for complete tool-by-tool analysis including:
- Build-out plans with actionable steps
- Innovative upgrade suggestions
- Risk assessments
- Integration point documentation
