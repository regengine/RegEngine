# CFR Traceability Matrix
## Nuclear Regulatory Compliance Mapping

**Purpose**: This document maps every RegEngine nuclear compliance feature to specific Code of Federal Regulations (CFR) requirements.

**Audience**: NRC inspectors, QA personnel, licensing engineers

**Last Updated**: 2026-01-25

---

## Overview

RegEngine's nuclear vertical implements a **Regulatory Evidence Layer** that meets NRC recordkeeping and cybersecurity documentation requirements under Title 10 CFR.

**Key Principle**: This system operates **out-of-band**. It does not control reactor operations, does not ensure nuclear safety, and does not replace your Quality Assurance program.

---

## Primary Regulatory Drivers

| CFR Citation | Requirement | RegEngine Implementation |
|--------------|-------------|--------------------------|
| **10 CFR 50 Appendix B, Criterion XVII** | Records shall be identifiable and retrievable. Adequate controls shall be established to prevent damage, deterioration, or loss. | Database immutability (NUC-0001), Chain linearity (NUC-0002), Retention policies (NUC-0401) |
| **10 CFR 73.54** | Licensees shall protect digital computer and communication systems from cyber attacks. Records of cyber security events shall be retained. | Snapshot creation engine (NUC-0104), Integrity verification (NUC-0201), Safety mode (NUC-0202) |
| **10 CFR 72.174** | Records important to decommissioning shall be maintained in an identified location until they are transferred to the licensee. | Discovery export (NUC-0404), Lifecycle logging (NUC-0501) |

---

## Sprint 0: NRC Record Integrity Floor

### NUC-0001 - Database-Enforced Snapshot Immutability

**CFR**: 10 CFR 50 Appendix B, Criterion XVII

> "Sufficient records shall be maintained to furnish evidence of activities affecting quality. [...] Records shall be identifiable and retrievable."

**Requirement Analysis**:
- "Shall be maintained" → Records must not be destroyed
- "Adequate controls" → Technical enforcement, not procedural

**Implementation**:
- PostgreSQL triggers prevent UPDATE/DELETE
- Only `signature_hash` writable post-creation
- Bypass impossible without DB admin access

**Verification**:
- Attempted UPDATE returns error
- Attempted DELETE returns error
- Audit log captures bypass attempts

---

### NUC-0002 - Enforce Snapshot Chain Linearity

**CFR**: 10 CFR 73.54(b)(1)

> "The cyber security program must be designed to protect digital computer and communication systems."

**Requirement Analysis**:
- Chain forks could obscure superseded records
- Evidence trail must be complete and linear

**Implementation**:
- Unique constraint on `(facility_id, previous_snapshot_id)`
- Prevents divergent compliance histories

**Verification**:
- Second successor fails with constraint violation
- Chain reconstruction always linear

---

### NUC-0003 - Clock Regression Detection

**CFR**: 10 CFR 50 Appendix B (Quality Assurance anomalies)

**Requirement Analysis**:
- Backward time movement indicates potential tampering
- Must be detected but not block operations

**Implementation**:
- Compare timestamps against previous snapshot
- Log anomaly without blocking creation
- Flag for QA review

**Verification**:
- Anomaly detected and logged
- Chain remains valid
- Inspector can query anomalies

---

## Sprint 1: Compliance Snapshot Engine

### NUC-0101 - Canonical Snapshot Representation

**CFR**: 10 CFR 73.54(b)(1) - accurate documentation

**Requirement Analysis**:
- Records must be authentic and verifiable
- Independent verification requires determinism

**Implementation**:
- Deterministic JSON serialization
- Stable field ordering
- No whitespace variations

**Verification**:
- Hash reproducible across environments
- Python/Node.js/Go produce same hash

---

### NUC-0102 - Content Hashing (SHA-256)

**CFR**: 10 CFR 50 Appendix B, Criterion XVII - authentic records

**Requirement Analysis**:
- Cryptographic proof of non-alteration
- Industry-standard algorithm required

**Implementation**:
- SHA-256 hash of canonical content
- Stored in immutable field
- Uses system crypto library (not custom)

**Verification**:
- Independent recomputation matches stored hash
- Alteration detected immediately

---

### NUC-0103 - Signature Seal

**CFR**: 10 CFR 50 Appendix B - document control

**Requirement Analysis**:
- Prevent ID reuse attacks
- Bind identity to content

**Implementation**:
- `signature_hash = SHA256(snapshot_id + content_hash)`
- Written atomically with snapshot

**Verification**:
- Signature mismatch detectable
- Cannot be modified post-creation

---

### NUC-0104 - Snapshot Creation Service

**CFR**: 10 CFR 73.54 - administrative controls

**Requirement Analysis**:
- Consistent procedures required
- Prevent bypass of controls

**Implementation**:
- Single service entry point
- Automatic chain linking
- Atomic transactions

**Verification**:
- Direct DB INSERT blocked
- All snapshots follow procedure

---

## Sprint 2: Integrity Verification & Safety Mode

### NUC-0201 - Snapshot Verification Engine

**CFR**: 10 CFR 73.54(b)(3) - detection and response

> "Procedures shall include methods to detect, respond to, and recover from cyber attacks."

**Requirement Analysis**:
- Must detect tampering
- Independent verification required

**Implementation**:
- Recompute hash, compare to stored
- Verify signature seal
- Check chain integrity

**Verification**:
- Altered content detected
- Broken chain detected
- ID mismatch detected

---

### NUC-0202 - Backend Safety Mode Enforcement

**CFR**: 10 CFR 50 Appendix B - prevent non-conforming materials/products

**Requirement Analysis**:
- Cannot use corrupted records for compliance
- System must fail safe

**Implementation**:
- Block mutations when integrity ≠ valid
- Server-side enforcement (cannot bypass)
- Read operations still allowed

**Verification**:
- API calls blocked during corruption
- Denied attempts logged
- Read access maintained

---

### NUC-0203 - Integrity Incident Ledger

**CFR**: 10 CFR 50 Appendix B - corrective action

**Requirement Analysis**:
- Anomalies must be documented
- Corrective action timeline preserved

**Implementation**:
- Immutable incident records
- Detection and clearance timestamps
- Affected snapshot window

**Verification**:
- Incident creation on corruption detection  
- Clearance event recorded
- Inspector can query history

---

### NUC-0204 - Action Attempt Logging

**CFR**: Enforcement practice (CFR Part 2, Appendix C - Enforcement Policy)

**Requirement Analysis**:
- Prove system blocked actions during failure
- Defense against enforcement actions

**Implementation**:
- Log all mutation attempts
- Include: timestamp, principal, action, allowed/denied, reason
- Immutable log

**Verification**:
- Denied actions logged with reason
- Can prove non-action during corruption

---

## Sprint 3: Attribution & Authentication

### NUC-0301 - Authentication Integration

**CFR**: 10 CFR 50 Appendix B, Criterion XVII - signed records

> "If a signature is required, the records shall be signed [...] by an authorized individual."

**Requirement Analysis**:
- Records must be attributable
- Authentication required

**Implementation**:
- OAuth/SAML for humans
- Service account auth for systems
- Session management

**Verification**:
- Unauthenticated requests rejected
- Principal identity captured

---

### NUC-0302 - Server-Side Attribution Enforcement

**CFR**: 10 CFR 73.54 - cyber security controls

**Requirement Analysis**:
- Client cannot forge identity
- Server must assign attribution

**Implementation**:
- Remove client-supplied attribution
- Server extracts from auth token
- Atomic with record creation

**Verification**:
- Client cannot specify principal_id
- Attribution immutable

---

### NUC-0303 - Attribution Persistence

**CFR**: 10 CFR 50 Appendix B - traceability

**Requirement Analysis**:
- Complete audit trail required
- Who created each record

**Implementation**:
- Fields: principal_id, principal_type, source_ip, request_id
- Non-nullable
- Included in hash

**Verification**:
- All fields populated
- Queryable for audit
- Immutable

---

## Sprint 4: Retention & Legal Hold

### NUC-0401 - Retention Policy Engine

**CFR**: 10 CFR 73.54(e)(3)

> "Records shall be retained for 3 years after the last entry or for the life of the facility, whichever is longer."

**Requirement Analysis**:
- Minimum retention: license life + 3 years
- Premature deletion prohibited

**Implementation**:
- Retention calculator
- Deletion blocked before expiration
- Configurable per record type

**Verification**:
- Deletion fails before retention expires
- Attempts logged

---

### NUC-0402 - Legal Hold Registry

**Legal Basis**: Federal Rules of Civil Procedure, Rule 37(e) - Spoliation

**Requirement Analysis**:
- Evidence must be preserved during litigation
- Hold must override retention policies

**Implementation**:
- `legal_holds` table
- Associate with snapshots
- Block deletion while hold active

**Verification**:
- Deletion fails when hold exists
- Multiple holds supported

---

### NUC-0403 - Deletion Prevention Under Hold

**CFR**: 10 CFR 50 Appendix B + Federal spoliation law

**Requirement Analysis**:
- Must not destroy evidence
- Override normal retention

**Implementation**:
- DB constraint prevents deletion
- Overrides retention expiration
- Audit trail of attempts

**Verification**:
- Deletion fails when hold active
- Cannot bypass via API or DB

---

### NUC-0404 - Discovery Export

**CFR**: 10 CFR 72.174(a)

> "Records shall be maintained and transferred including decommissioning records."

**Requirement Analysis**:
- Inspectors must retrieve evidence
- Export must be verifiable

**Implementation**:
- JSON export with metadata
- Chain proof included
- Cryptographic attestation

**Verification**:
- Export includes requested snapshots
- Chain proof verifiable offline

---

## Sprint 5: Lifecycle Proof

### NUC-0501 - Immutable Lifecycle Log

**CFR**: 10 CFR 50 Appendix B (implied) - record lifecycle

**Requirement Analysis**:
- Prove non-deletion through logging
- Complete lifecycle trail

**Implementation**:
- Log all lifecycle events
- Creation, access, holds, deletion attempts
- Immutable entries

**Verification**:
- All events logged
- Deletion attempts recorded
- Inspector queryable

---

### NUC-0502 - Lifecycle Cryptographic Sealing

**Legal Basis**: Discovery defense (spoliation claims)

**Requirement Analysis**:
- Prove lifecycle log authentic
- Prevent retroactive alteration

**Implementation**:
- Hash lifecycle entries
- Chain entries
- Periodic sealing

**Verification**:
- Tampering detectable
- Independent verification possible

---

### NUC-0503 - Retention Compliance Reports

**CFR**: 10 CFR 72.174(d) - inspections

**Requirement Analysis**:
- Inspector must verify retention compliance
- Automated reporting

**Implementation**:
- Generate compliance reports
- Show retention status
- Highlight upcoming expirations

**Verification**:
- All records accounted for
- Export to PDF/JSON

---

## Enforcement Defense Strategy

### How This System Supports NRC Inspections

**Inspection Scenario 1**: "Show me your cybersecurity program records."

- **System Response**: Display snapshot timeline with cryptographic verification
- **Inspector Verification**: Recompute hashes independently
- **CFR Satisfied**: 10 CFR 73.54(b)(1)

---

**Inspection Scenario 2**: "Prove this record wasn't altered."

- **System Response**: Provide hash, signature, chain proof
- **Inspector Verification**: Independent recomputation matches
- **CFR Satisfied**: 10 CFR 50 App B, Criterion XVII

---

**Inspection Scenario 3**: "What happened during the June incident?"

- **System Response**: Integrity incident ledger shows corruption window
- **Inspector Verification**: Action logs prove system blocked mutations
- **CFR Satisfied**: Enforcement policy compliance

---

**Inspection Scenario 4**: "Who approved this change?"

- **System Response**: Attribution fields show authenticated principal
- **Inspector Verification**: Cannot be forged (server-side enforcement)
- **CFR Satisfied**: 10 CFR 50 App B (signed records)

---

**Inspection Scenario 5**: "Are records preserved under legal hold?"

- **System Response**: Legal hold registry + discovery export
- **Inspector Verification**: Chain verification in export
- **CFR Satisfied**: 10 CFR 72.174 + spoliation law

---

## What This System Does NOT Do

**Critical Boundaries** (avoid false claims):

❌ **Does not ensure nuclear safety**  
→ That's your QA program under 10 CFR 50 App B

❌ **Does not make you NRC-compliant automatically**  
→ Compliance requires complete programs, not just record keeping

❌ **Does not replace licensing processes**  
→ This is evidence infrastructure, not regulatory processes

❌ **Does not control reactor operations**  
→ Out-of-band evidence layer only

---

## Compliance Claim (Approved for Sales)

> "RegEngine provides a compliance evidence layer that helps nuclear operators meet NRC recordkeeping and cybersecurity documentation obligations under 10 CFR. It operates out-of-band, preserves evidence immutably, and supports inspection and discovery."

**Why This Is Safe**:
- Claims are bounded and provable
- Does not overstate system capabilities
- Aligns with regulatory expectations
- Acknowledges system boundaries

---

## Summary Table

| Sprint | CFR Citations | Regulatory Claims Unlocked |
|--------|---------------|----------------------------|
| **Sprint 0** | 10 CFR 50 App B (XVII), 10 CFR 73.54 | "Records are immutable, ordered, and tamper-evident" |
| **Sprint 1** | 10 CFR 73.54, 10 CFR 50 App B | "Cryptographically verifiable compliance snapshots are produced" |
| **Sprint 2** | 10 CFR 73.54(b)(3), 10 CFR 50 App B | "The system fails safe and can prove non-action during integrity failure" |
| **Sprint 3** | 10 CFR 50 App B (XVII), 10 CFR 73.54 | "All compliance records are attributable" |
| **Sprint 4** | 10 CFR 73.54(e)(3), 10 CFR 72.174 | "Evidence is preserved and discoverable per NRC requirements" |
| **Sprint 5** | 10 CFR 50 App B, 10 CFR 72.174(d) | "Non-deletion and evidence existence are provable" |

---

## Document Control

**Version**: 1.0  
**Effective Date**: 2026-01-25  
**Next Review**: Sprint 2 completion  
**Maintained By**: RegEngine Compliance Team  
**Approved Claim**: See "Compliance Claim" section above

---

*This document is a living artifact and will be updated as sprints complete and regulatory guidance evolves.*
