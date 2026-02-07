# Nuclear Vertical

**Regulatory Framework**: 10 CFR (Nuclear Regulatory Commission)  
**Status**: Active Development  
**Compliance Standard**: NRC Recordkeeping & Cybersecurity Documentation

---

## Overview

The Nuclear vertical provides a **Regulatory Evidence Layer** for nuclear facilities to meet NRC recordkeeping and cybersecurity documentation obligations under Title 10 Code of Federal Regulations.

**Critical Understanding**: This is **infrastructure**, not a compliance dashboard. It operates out-of-band and does not control reactor operations, ensure nuclear safety, or replace Quality Assurance programs.

---

## What This System Does

✅ **Produces immutable, cryptographically verifiable compliance records**  
✅ **Preserves evidence under legal hold for enforcement actions**  
✅ **Blocks compliance actions when integrity cannot be verified (fail-safe)**  
✅ **Attributes all records to authenticated principals**  
✅ **Retains records per NRC requirements (license life + 3 years)**  

---

## What This System Does NOT Do

❌ **Does not ensure nuclear safety** (that's your QA program under 10 CFR 50 Appendix B)  
❌ **Does not make you NRC-compliant automatically** (compliance requires complete programs)  
❌ **Does not replace licensing or QA processes** (this is evidence infrastructure)  
❌ **Does not control reactor operations** (out-of-band evidence layer only)  

---

## Regulatory Foundations

| CFR Citation | Requirement | Implementation |
|--------------|-------------|----------------|
| **10 CFR 50 Appendix B, Criterion XVII** | Records shall be identifiable and retrievable. Controls shall prevent damage, deterioration, or loss. | Database immutability, chain linearity, retention policies |
| **10 CFR 73.54** | Protect digital systems from cyber attacks. Retain records of cyber security events. | Snapshot engine, integrity verification, safety mode |
| **10 CFR 72.174** | Maintain decommissioning records. | Discovery export, lifecycle logging |

---

## Architecture

### Core Components

1. **Immutability Layer** (Sprint 0)
   - Database triggers prevent UPDATE/DELETE
   - Chain linearity enforcement
   - Clock regression detection

2. **Cryptographic Engine** (Sprint 1)
   - Canonical snapshot representation
   - SHA-256 content hashing
   - Signature sealing

3. **Verification & Safety** (Sprint 2)
   - Independent hash verification
   - Backend safety mode (blocks actions during corruption)
   - Integrity incident ledger

4. **Attribution** (Sprint 3)
   - Server-side principal enforcement
   - Authentication integration
   - Immutable attribution persistence

5. **Retention & Legal Hold** (Sprint 4)
   - Retention policy engine
   - Legal hold registry
   - Discovery export

6. **Lifecycle Proof** (Sprint 5)
   - Immutable lifecycle logging
   - Cryptographic sealing
   - Compliance reporting

---

## Documentation

- **[CFR Traceability Matrix](./cfr_traceability_matrix.md)** - Maps every feature to specific CFR requirements
- **[Sprint Backlog](./sprint_backlog.md)** - Execution roadmap (Sprint 0-5)
- **[Inspection Walkthrough](./inspection_walkthrough.md)** - How NRC inspectors will verify the system
- **[Regulatory Boundaries](./regulatory_boundaries.md)** - Clear scope and limitations
- **[Approved Claims](./approved_claims.md)** - What sales/executives can legally say

---

## Integration Points

### Backend
```python
# regengine/verticals/nuclear/
from regengine.verticals.nuclear import NuclearComplianceEngine

engine = NuclearComplianceEngine()
record = engine.create_record(
    facility_id="NPP-UNIT-1",
    docket_number="50-12345",
    record_type="CYBER_SECURITY_PLAN",
    ...
)
```

### Frontend
```typescript
// See: frontend/src/app/verticals/nuclear/page.tsx
<Link href="/verticals/nuclear">Nuclear Compliance</Link>
```

### API
```bash
POST /api/nuclear/records
GET /api/nuclear/records/{id}/verify
POST /api/nuclear/legal-holds
GET /api/nuclear/discovery/export
```

---

## Compliance Claims (Approved for External Use)

> "RegEngine provides a compliance evidence layer that helps nuclear operators meet NRC recordkeeping and cybersecurity documentation obligations under 10 CFR. It operates out-of-band, preserves evidence immutably, and supports inspection and discovery."

**Why This Is Safe**:
- Claims are bounded and provable
- Does not overstate system capabilities
- Acknowledges system boundaries
- Aligns with regulatory expectations

---

## Development Roadmap

| Sprint | Duration | Gate | Regulatory Claim Unlocked |
|--------|----------|------|---------------------------|
| **Sprint 0** | 2 weeks | Immutability proven | "Records are immutable, ordered, and tamper-evident" |
| **Sprint 1** | 2 weeks | Hash verification working | "Cryptographically verifiable compliance snapshots" |
| **Sprint 2** | 2 weeks | Safety mode enforced | "System fails safe during integrity failure" |
| **Sprint 3** | 2 weeks | Attribution verified | "All compliance records are attributable" |
| **Sprint 4** | 4 weeks | Legal hold tested | "Evidence preserved and discoverable per NRC" |
| **Sprint 5** | 4 weeks | Reports generated | "Non-deletion provable" |

**Total**: 16 weeks to full compliance framework

---

## Getting Started

### For Developers
1. Read [Sprint Backlog](./sprint_backlog.md) for current priorities
2. Review [CFR Traceability Matrix](./cfr_traceability_matrix.md) to understand regulatory context
3. Start with Sprint 0 (immutability is the foundation)

### For Compliance/QA
1. Read [Regulatory Boundaries](./regulatory_boundaries.md) to understand scope
2. Review [Inspection Walkthrough](./inspection_walkthrough.md) for NRC scenarios
3. Use [Approved Claims](./approved_claims.md) for commercial positioning

### For Executives
1. Read [Approved Claims](./approved_claims.md) (what you can say)
2. Understand: This is infrastructure, not a magic compliance button
3. Commercial positioning requires regulatory counsel review

---

## Next Steps

1. ✅ Complete Sprint 0 (database immutability)
2. ⏳ Implement Sprint 1 (cryptographic engine)
3. ⏳ Build Sprint 2 (safety mode)
4. ⏳ After Sprint 2: Create board briefing and mock NRC inspection

---

## Contact & Governance

**Vertical Owner**: TBD  
**Regulatory Counsel**: TBD  
**Technical Lead**: TBD  

**Change Control**: Any changes to Sprint 0-2 components require:
1. CFR justification
2. Regulatory counsel review
3. documented in this README

---

**Last Updated**: 2026-01-25  
**Version**: 1.0  
**Status**: Active Development
