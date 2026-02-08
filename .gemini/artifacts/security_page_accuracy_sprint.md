# Security Page Accuracy Sprint
**Date**: 2026-02-08
**Goal**: Make every claim on the security page verifiably accurate against codebase evidence.

## Fixes Required

### FIX-1: Wrong trigger name in Immutable Audit Trail evidence
- **File**: `frontend/src/app/security/page.tsx` (line 79)
- **Current**: `"Enforced via prevent_content_mutation trigger..."`
- **Actual**: The trigger is named `prevent_mutation()` (V20__schema_governance.sql, line 35)
- **Fix**: Change to `prevent_mutation`

### FIX-2: Stale evidence numbers for Independent Verification
- **File**: `frontend/src/app/security/page.tsx` (line 87)
- **Current**: `"5 hashes verified, 0 failed. 4 lineage links verified, 0 broken. 0 consistency errors."`
- **Finding**: V3 verification run verified 430 records. The "4 lineage links" claim is from `tests/audit/verify_chain.py` (which does have lineage checking), but the *public SDK* version doesn't include lineage.
- **Fix**: Update to reflect V3 evidence: "430 hashes verified, 0 failed. Lineage links verified via audit export (tests/audit/verify_chain.py)."

### FIX-3: Promote 5 "Tonight/Implementing" items to "✓ Implemented"
- **File**: `frontend/src/app/security/page.tsx` (lines 98-102)
- **Items that are DONE**:
  1. CI security scanning → `.github/workflows/security.yml` (262 lines, 8 jobs)
  2. VDP + security.txt → `docs/security/VDP.md` + `frontend/public/.well-known/security.txt`
  3. Audit log export (tamper-evident) → `V30__audit_logs_tamper_evident.sql` (118 lines, hash chain, immutability triggers)
  4. Hardening gates → `security.yml` tenant-isolation job
  5. Incident response plan → `docs/security/INCIDENT_RESPONSE.md` + `docs/runbooks/incident-response.md`
- **Fix**: Change status from `"implementing"` to `"implemented"` and timeline from `"Tonight"` to `"Current"`

### FIX-4: Update security roadmap doc to match
- **File**: `docs/security/ROADMAP.md`
- **Fix**: Update statuses to reflect implemented items

### FIX-5: Update Immutable Audit Trail description for accuracy
- **File**: `frontend/src/app/security/page.tsx` (line 78)
- **Current description** mentions "Updates create new versioned records" — but `prevent_mutation()` blocks ALL updates/deletes (not selective content-vs-metadata)
- **Fix**: Clarify the description to match V20 behavior

## Execution Order
1. FIX-1 + FIX-2 + FIX-3 + FIX-5 → Single edit to `security/page.tsx`
2. FIX-4 → Update `docs/security/ROADMAP.md`
3. Verify in browser
