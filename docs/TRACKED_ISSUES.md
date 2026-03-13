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

## Summary

| Priority | Count | Status |
|----------|-------|--------|
| P3       | 2     | Open   |
| **Total**| **2** |        |

> Previous TODOs (PPAP vault storage, placeholder tests) have been resolved in Sprint 5.
