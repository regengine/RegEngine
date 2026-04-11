# RegEngine FSMA 204 Phase 1: Critical Fixes Implementation Roadmap

**Priority:** CRITICAL - Must complete before FDA production use
**Target Timeline:** 2-3 weeks (with focused team of 2)
**Last Updated:** 2026-03-27

---

## Overview

This document breaks down the 8 critical compliance gaps identified in the audit into executable implementation tasks organized by module and priority.

**Estimated Effort:** 120-180 person-hours across 3 phases
- Phase 1 (this document): 40-60 hours (weeks 1-2)
- Phase 2: 40-60 hours (weeks 2-3)
- Phase 3: 40-60 hours (weeks 3+)

---

## Phase 1: Critical Fixes (Next 2 Weeks)

### Task 1.1: Implement FLBR (First Land-Based Receiving) CTE

**Location:** Multiple files
**Complexity:** HIGH
**Effort:** 16-20 hours
**Owner:** Backend engineer

**Current State:**
- FLBR defined in regulatory spec (21 CFR 1.1325) but not in codebase
- csv_templates.py lacks FLBR template
- No FLBR column in FDA export schema
- FLBR is mandatory for all imported foods (> 50% of US food supply)

**Steps:**
1. Add FLBR to `CTE_TYPES` enum in `/sessions/gracious-cool-bell/mnt/RegEngine/services/ingestion/models/cte_model.py` (find current location with grep)
2. Create FLBR CSV template in `/sessions/gracious-cool-bell/mnt/RegEngine/services/ingestion/app/csv_templates.py`:
   - Required columns: TLC, product, quantity, receiving_date, receiving_time, receiving_location, receiving_GLN, immediate_previous_supplier, immediate_previous_location, temperature_celsius
   - Add example row showing proper format
3. Add FLBR to FDA export columns mapping in `fda_export_router.py` (lines 725-735)
4. Add FLBR bizStep URI to EPCIS export in `epcis_export.py` (line 206: add `elif cte_type == "flbr"`)
5. Add FLBR to recall_report.py scoring (line 42: `cte_types_coverage` calculation)
6. Update compliance_score.py CTE coverage weighting to include FLBR
7. Create database migration: add `flbr` as valid event_type in fsma.cte_events.event_type enum
8. Add unit test: CSV upload with FLBR event → verify in export

**Acceptance Criteria:**
- [ ] FLBR template downloadable from `/api/v1/templates/flbr`
- [ ] FLBR events exportable in FDA CSV format
- [ ] FLBR events appear in EPCIS 2.0 export with correct bizStep
- [ ] Compliance score includes FLBR in CTE coverage calculation
- [ ] Test: Upload FLBR CSV → verify 7 fields captured → export → confirm in FDA package

**Blockers:** None
**Dependencies:** None

---

### Task 1.2: Implement Event Entry Time Capture

**Location:** `/sessions/gracious-cool-bell/mnt/RegEngine/services/ingestion/models/cte_model.py`, csv_templates.py, fda_export_router.py
**Complexity:** MEDIUM
**Effort:** 12-14 hours
**Owner:** Backend engineer

**Current State:**
- Only event_date captured; entry_time not stored
- FDA regulation requires time-of-event (not just date) for chain verification
- Current exports show only date, losing 24-hour resolution

**Steps:**
1. Expand cte_model.py to split event datetime:
   - Rename `event_timestamp` → keep as full ISO 8601
   - Add `event_date` field (YYYY-MM-DD extracted)
   - Add `event_time` field (HH:MM:SS extracted)
2. Update CSV templates to include separate date/time columns (or ISO 8601 single column)
3. Update FDA export to include both fields in correct FDA format
4. Update EPCIS export eventTime field (already uses full ISO 8601—verify)
5. Update compliance_score.py: add "time_precision" to KDE completeness check
6. Create database migration: add event_time column if not present
7. Test: Upload event with time → verify both date and time exported

**Acceptance Criteria:**
- [ ] All CSV templates show event_date and event_time columns
- [ ] FDA CSV export includes EVENT_TIME column with HH:MM:SS format
- [ ] EPCIS export includes eventTime with timezone offset
- [ ] Compliance score flags events with missing time
- [ ] Test: Upload event 2026-03-27 14:30 → export shows both components

**Blockers:** None
**Dependencies:** None

---

### Task 1.3: Implement KDE Completeness Validation at Upload

**Location:** `/sessions/gracious-cool-bell/mnt/RegEngine/services/ingestion/validators/` (create if missing)
**Complexity:** MEDIUM
**Effort:** 14-18 hours
**Owner:** Backend engineer

**Current State:**
- No validation that KDEs are filled before export
- Missing fields exported as empty strings without error
- No audit trail of validation failures
- Compliance score only shows current state, not entry-time validation

**Steps:**
1. Create KDE validator module: `/sessions/gracious-cool-bell/mnt/RegEngine/services/ingestion/validators/kde_validator.py`
   - Function: `validate_kde_completeness(cte_event: dict) -> (bool, list[str])` returns (is_valid, errors)
   - Check all 5 required KDEs present and non-empty:
     - Traceability_Lot_Code (TLC) - must match regex `^[A-Z0-9\-_]{6,}$`
     - Location identifier (GLN or facility name) - GLN must be 13-digit numeric
     - Date/time (now includes both date and time per Task 1.2)
     - Product description + quantity
     - Reference document (shipping doc, receiving doc, transformation doc)
2. Add validation to CSV upload endpoint in `csv_ingest_router.py`:
   - Validate each row during parse (reject invalid rows early)
   - Log validation errors to audit log
   - Return count of valid/invalid rows to user
3. Add validation to `/api/v1/compliance-score` endpoint:
   - Add "kde_validation_errors" field showing events with missing KDEs
4. Add validation to export endpoints:
   - Warn if exporting events with missing KDEs
   - Option to exclude incomplete events from export
5. Create database table: `fsma.kde_validation_log` to track all validation checks
6. Test: Upload CSV with missing TLC in row 5 → verify row rejected, others accepted

**Acceptance Criteria:**
- [ ] CSV upload rejects rows with missing required KDEs
- [ ] Validation error messages show which KDE is missing in which row
- [ ] Audit log captures all validation failures with timestamp
- [ ] Compliance score shows "KDE completeness: X% (Y events missing KDEs)"
- [ ] Test: Upload CSV with 5 complete + 2 incomplete rows → verify rejection + audit trail

**Blockers:** Task 1.2 (need both date and time fields)
**Dependencies:** Task 1.2

---

### Task 1.4: Implement Chain Verification in Export Flow

**Location:** `fda_export_router.py`, `epcis_export.py`, new module: `chain_verifier.py`
**Complexity:** HIGH
**Effort:** 18-22 hours
**Owner:** Backend engineer (cryptography experience helpful)

**Current State:**
- `verify_export()` endpoint exists (lines 934-1040) but only called on-demand
- Chain verification not integrated into regular export flow
- No automatic detection of sequence gaps or tampering
- Hash values computed but not validated during export

**Steps:**
1. Create chain verification module: `/sessions/gracious-cool-bell/mnt/RegEngine/services/ingestion/crypto/chain_verifier.py`
   - Function: `verify_chain_integrity(events: list[dict]) -> (bool, list[dict])` returns (is_valid, gaps)
   - Check all events have sequential hashes (each event hash includes previous hash)
   - Detect gaps in TLC sequence (events out of order)
   - Detect missing intermediate events
   - Return detailed gap report with affected LOT_CODE and time range
2. Implement Merkle tree for batch verification (optional; consider for Phase 2):
   - Current sequential hash approach is valid but inefficient for large batches
   - Merkle tree allows O(log n) verification of subset integrity
3. Integrate into `_build_fda_package()` (lines 815-825):
   - Call chain_verifier before creating ZIP
   - Include chain verification results in manifest.json
   - Flag any gaps in chain_verification_*.json
4. Integrate into EPCIS export:
   - Add chain verification status to response metadata
5. Add chain verification to compliance_score.py:
   - Chain integrity dimension (25% weight) should verify actual chain not just assume success
   - Current code (line 625) calls `CTEPersistence.verify_chain()` - ensure it's working
6. Create background job: periodic chain verification (nightly)
   - Log any chains with gaps
   - Alert on tampering detection
7. Test: Create batch of 5 events → export → verify chain → modify one hash → re-verify shows tampering

**Acceptance Criteria:**
- [ ] Export includes chain verification report in JSON
- [ ] Gaps in event sequence detected and reported
- [ ] Manual hash tampering detected on re-verification
- [ ] Compliance score "Chain Integrity" dimension reflects actual verification (not assumed)
- [ ] Test: Modify event #3 hash in database → export fails verification check

**Blockers:** None
**Dependencies:** None (but works better with Task 1.2)

---

### Task 1.5: Consolidate Demo Mode Disclaimers

**Location:** `recall_report.py`, `epcis_export.py`, `recall_simulations.py`, `fda_export_router.py`
**Complexity:** LOW
**Effort:** 6-8 hours
**Owner:** Any engineer

**Current State:**
- Hardcoded demo data in 3 modules with inconsistent disclaimer handling
- recall_report.py shows disclaimer when demo_mode=true
- epcis_export.py has sample data but no disclaimer in response
- recall_simulations.py always illustrative but disclaimer buried in response
- fda_export_router.py shows warning in README but not in JSON

**Steps:**
1. Create standardized disclaimer constant: `/sessions/gracious-cool-bell/mnt/RegEngine/services/ingestion/config/disclaimers.py`
   ```python
   DEMO_DATA_DISCLAIMER = (
       "⚠ DEMO/SAMPLE DATA: This export contains illustrative or sample data "
       "that is NOT derived from your tenant's actual traceability records. "
       "Scores, findings, and recommendations are representative examples only. "
       "Complete your onboarding to see production data."
   )
   SYNTHETIC_METRICS_DISCLAIMER = (
       "⚠ SYNTHETIC METRICS: Simulation metrics are based on illustrative scenarios, "
       "not your tenant's actual supply chain. Use for training/demonstration only."
   )
   ```
2. Update recall_report.py to use standardized disclaimer (already compliant, just refactor)
3. Update epcis_export.py:
   - Add `is_sample_data` flag to response when using SAMPLE_EPCIS_EVENTS (line 273)
   - Include disclaimer in response when flagged
4. Update recall_simulations.py:
   - Rename `is_illustrative` → `uses_synthetic_metrics`
   - Always include SYNTHETIC_METRICS_DISCLAIMER in response
5. Update fda_export_router.py:
   - Add disclaimer to JSON response metadata (not just README.txt)
   - Only include if exporting fewer than 10 events (threshold for demo)
6. Create UI component (frontend integration task):
   - Any response with disclaimer flag should show warning banner
   - Make banner dismissible but persistent per session
7. Test: Export from tenant with 0 events → verify disclaimer present; with 1000 events → no disclaimer

**Acceptance Criteria:**
- [ ] All demo/sample data exports include standardized disclaimer
- [ ] Disclaimer appears in JSON response (not just files)
- [ ] Frontend shows warning banner for demo data
- [ ] Test: Demo export response includes `demo_mode: true, disclaimer: "⚠ DEMO/SAMPLE DATA..."`

**Blockers:** None
**Dependencies:** None

---

### Task 1.6: Update CSV Templates with All 7 CTE Types

**Location:** `csv_templates.py`
**Complexity:** LOW
**Effort:** 4-6 hours
**Owner:** Any engineer

**Current State:**
- 6 CTE types defined: harvesting, cooling, initial_packing, shipping, receiving, transformation
- FLBR missing (to be added in Task 1.1)
- Growing CTE not implemented (required for certain products)
- Templates lack field descriptions and validation rules

**Steps:**
1. Add FLBR template (per Task 1.1)
2. Add Growing CTE template (optional—check if required for your product lines):
   - Columns: TLC, product, quantity, grow_start_date, grow_end_date, location, GLN, harvester_name
3. Update all existing templates to include:
   - Comment rows explaining each column
   - Example values showing proper format (GLN must be 13-digit, dates ISO 8601)
   - Validation rules inline (e.g., "GLN: 13-digit numeric with check digit")
4. Add CTE_TYPE_ALIASES mapping for user convenience:
   - "receiving" → maps to "receiving" or "flbr" depending on source
5. Update `download_template()` endpoint to include comment descriptions
6. Test: Download each template → verify all fields present with examples

**Acceptance Criteria:**
- [ ] All 7 CTE type templates available
- [ ] Each template shows required fields + examples
- [ ] Download returns CSV with inline field descriptions
- [ ] Test: Download FLBR template → verify 9+ columns with examples

**Blockers:** Task 1.1 (need FLBR defined first)
**Dependencies:** Task 1.1

---

## Phase 1 Implementation Schedule

| Week | Task | Owner | Hours | Status |
|------|------|-------|-------|--------|
| 1 | 1.1: FLBR CTE | Backend | 18 | PENDING |
| 1 | 1.2: Event Time Capture | Backend | 13 | PENDING |
| 1 | 1.5: Demo Disclaimers | Any | 7 | PENDING |
| 2 | 1.3: KDE Validation | Backend | 16 | PENDING |
| 2 | 1.4: Chain Verification | Backend | 20 | PENDING |
| 2 | 1.6: CSV Templates Update | Any | 5 | PENDING |
| **Total Phase 1** | | | **79 hours** | |

**Weekly Cadence:**
- Daily standup (15 min): blockers, progress, next tasks
- Code review: all PRs require 2 approvals
- Testing: unit + integration tests for each task before merge

---

## Phase 1 Success Criteria (Overall)

Phase 1 is complete when ALL of the following are true:

- [ ] FLBR CTE supported in CSV upload, export, scoring
- [ ] KDE completeness validated at upload time with audit trail
- [ ] Event time captured and exported (both date + time)
- [ ] Chain verification integrated into export flow
- [ ] Demo mode disclaimers standardized and visible in all responses
- [ ] CSV templates complete (all CTE types + examples)
- [ ] All Phase 1 unit tests passing
- [ ] Compliance audit passes with <5 medium-priority findings

**Go/No-Go Decision:** After Phase 1 completion, determine readiness for pilot with select tenants or proceed to Phase 2.

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Merkle tree complexity delays chain verification | Medium | High | Defer Merkle tree to Phase 2; use sequential hash for now |
| GLN validation too strict, breaks existing imports | Medium | High | Implement with warning-only mode first; gather feedback before blocking |
| FLBR mapping unclear (receiving vs FLBR) | Low | High | Review FDA FTL guidance document; create decision matrix in code comments |
| Database migration conflicts with live data | Low | Critical | Test migration on staging copy; have rollback plan; coordinate with ops |
| KDE validator blocks valid international formats | Low | Medium | Make validation configurable by region; add exemption list |

---

## Next Steps After Phase 1

1. **Testing & Validation** (1 week)
   - Run full compliance test suite
   - Pilot export with 3 test tenants
   - Validate FDA compatibility with sample package

2. **Phase 2: Data Integrity Hardening** (2-3 weeks)
   - Implement Merkle tree chain verification
   - Add Merkle root to manifest
   - Background chain verification job
   - Audit log retention and archival

3. **Phase 3: Operational Hardening** (2-3 weeks)
   - 24-hour response time SLA tracking
   - Export monitoring and alerting
   - Disaster recovery for chain data
   - Supplier onboarding validation workflow

---

**Document Owner:** Christopher (Founder)
**Last Updated:** 2026-03-27
**Next Review:** After Phase 1 completion
