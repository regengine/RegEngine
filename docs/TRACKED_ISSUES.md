# RegEngine — Tracked Issues (from TODO comments)

**Generated:** February 8, 2026  
**Source:** Full codebase scan of `services/` and `frontend/src/`

---

## Open Items

### ISSUE-001: PCOS Component Stubs
**File:** `frontend/src/components/pcos/index.ts`  
**Priority:** P3 (Low)  
**Type:** Feature Gap  

4 PCOS components are commented out with TODO:
- `ComplianceTimeline` (line 10)
- `DocumentTracker` (line 17)
- `RiskHeatMap` (line 21)
- `HowToGuide` (line 27)

**Action:** Either implement these components or remove the commented exports. These are part of the Entertainment (PCOS) vertical which currently uses "Demo Preview" badges for mock data. These components can be implemented when the Entertainment vertical gets a production backend.

---

### ISSUE-002: PCOS Backend API Integration
**File:** `frontend/src/app/pcos/page.tsx:347`  
**Priority:** P3 (Low)  
**Type:** Integration Work  

```
// TODO: Integrate with backend API when available
```

The PCOS page currently uses hardcoded mock data. Needs backend API integration when the Entertainment service is production-ready.

**Action:** Implement API routes in the Entertainment service and connect the frontend when ready.

---

### ISSUE-003: Energy Snapshot Test Database
**File:** `services/energy/tests/test_snapshot_integrity.py:299`  
**Priority:** P2 (Medium)  
**Type:** Test Coverage  

```python
# TODO: Implement with actual test database
```

An integration test that needs a real database connection to verify snapshot integrity end-to-end.

**Action:** Create a `conftest.py` fixture that provisions a test Postgres database (or uses `testcontainers`) for this test.

---

### ISSUE-004: Energy Model User ID Enforcement
**File:** `services/energy/app/models.py:69`  
**Priority:** P2 (Medium)  
**Type:** Security — Business Logic  

```python
# TODO: In production, enforce user_id requirement based on generated_by type
```

Currently `user_id` is not required when `generated_by` indicates an automated process. In production, this should enforce user identity for audit trail completeness.

**Action:** Add a Pydantic validator that requires `user_id` when `generated_by != 'SYSTEM'`.

---

## Summary

| Priority | Count | Status |
|----------|-------|--------|
| P2       | 2     | Open   |
| P3       | 2     | Open   |
| **Total**| **4** |        |

> Previous TODOs (PPAP vault storage, placeholder tests) have been resolved in Sprint 5.
