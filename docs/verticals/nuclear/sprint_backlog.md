# Nuclear Compliance Sprint Backlog

**Total Sprints**: 5  
**Total Duration**: 16 weeks  
**Total Tickets**: 20

---

## Sprint 0: NRC Record Integrity Floor (2 weeks)

**Gate**: Cannot proceed to Sprint 1 until immutability is provably enforced.

**Regulatory Claim Unlocked**: "Records are immutable, ordered, and tamper-evident"

### NUC-0001 — Database-Enforced Snapshot Immutability

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 50 Appendix B, Criterion XVII  
**Why This Exists**: Records must be protected against unauthorized alteration or loss.

**Task**:
- Add DB triggers to prevent UPDATE and DELETE on `compliance_snapshots`
- Allow ONLY `signature_hash` write during creation transaction
- Implement database-level enforcement (not application-level)

**Acceptance Criteria**:
- [ ] Raw SQL UPDATE on `compliance_snapshots` fails with explicit error
- [ ] Raw SQL DELETE on `compliance_snapshots` fails with explicit error
- [ ] Attempted bypass (direct DB access) raises DB error
- [ ] `signature_hash` can be written exactly once during INSERT transaction
- [ ] All other fields are immutable after INSERT commits

**Dependencies**: None (foundation)

---

### NUC-0002 — Enforce Snapshot Chain Linearity

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 73.54 (superseded records preserved)  
**Why This Exists**: Prevents forked compliance histories that could obscure evidence.

**Task**:
- Add unique constraint on `(facility_id, previous_snapshot_id)`
- Ensure only one successor snapshot per snapshot
- Block attempts to create divergent chains

**Acceptance Criteria**:
- [ ] Second successor insert fails with constraint violation
- [ ] Chain reconstruction always returns linear path
- [ ] Fork attempts logged for audit trail
- [ ] Constraint cannot be disabled without DB admin privileges

**Dependencies**: NUC-0001

---

### NUC-0003 — Clock Regression Detection

**Priority**: P1 (Strongly Recommended)  
**CFR**: 10 CFR 50 App B (anomaly detection)  
**Why This Exists**: Detect potential tampering via backward time movement.

**Task**:
- Compare `snapshot_time` against previous snapshot in chain
- Detect backward time movement
- Log warning without blocking snapshot creation
- Flag snapshot for review

**Acceptance Criteria**:
- [ ] Backward time movement detected and logged
- [ ] Warning does NOT block snapshot creation
- [ ] Anomaly flag persisted in database
- [ ] Chain remains authoritative (time anomaly doesn't break chain)
- [ ] Inspector can query anomalies

**Dependencies**: NUC-0002

---

## Sprint 1: Compliance Snapshot Engine (2 weeks)

**Gate**: Hash must be reproducible across environments.

**Regulatory Claim Unlocked**: "Cryptographically verifiable compliance snapshots are produced"

### NUC-0101 — Canonical Snapshot Representation

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 73.54 (accurate documentation)

**Task**:
- Implement deterministic canonical JSON serialization
- Stable field ordering (alphabetical)
- Consistent formatting (no whitespace variations)
- Remove non-deterministic fields before hashing

**Acceptance Criteria**:
- [ ] Same input → same canonical output
- [ ] Hash reproducible in Python, Node.js, Go
- [ ] Independent recomputation matches stored hash
- [ ] Unit tests verify determinism

---

### NUC-0102 — Content Hashing (SHA-256)

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 50 App B (authentic records)

**Task**:
- Compute SHA-256 hash of canonical snapshot
- Store hash in `content_hash` field
- Use industry-standard library (DO NOT implement crypto)

**Acceptance Criteria**:
- [ ] SHA-256 hash computed correctly
- [ ] Independent recomputation matches stored value
- [ ] Hash includes all immutable fields
- [ ] Hash excludes mutable metadata

**Dependencies**: NUC-0101

---

### NUC-0103 — Signature Seal

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 50 App B (instance authenticity)

**Task**:
- Compute `signature_hash = SHA256(snapshot_id + content_hash)`
- Write signature post-flush, pre-commit
- Make signature immutable after commit

**Acceptance Criteria**:
- [ ] Signature incorporates both ID and content hash
- [ ] Signature written in same transaction as snapshot
- [ ] Signature mismatch detectable via verification
- [ ] Signature cannot be modified after commit

**Dependencies**: NUC-0102

---

### NUC-0104 — Snapshot Creation Service

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 73.54

**Task**:
- Create `SnapshotService.create()` method
- Chain to previous snapshot automatically
- Compute hashes and signature
- Emit `snapshot-created` event
- Atomic transaction (all or nothing)

**Acceptance Criteria**:
- [ ] Service is only way to create snapshots
- [ ] Direct INSERT to DB bypassed by triggers
- [ ] Chain linking automatic
- [ ] Event emitted on success
- [ ] Rollback on any failure

**Dependencies**: NUC-0101, NUC-0102, NUC-0103

---

## Sprint 2: Integrity Verification & Safety Mode (2 weeks)

**Gate**: Safety mode must block ALL mutations during corruption.

**Regulatory Claim Unlocked**: "The system fails safe and can prove non-action during integrity failure"

### NUC-0201 — Snapshot Verification Engine

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 73.54 (integrity protection)

**Task**:
- Implement `VerificationService.verify(snapshot_id)`
- Recompute content hash, compare to stored
- Verify signature seal
- Check chain integrity
- Return status: `valid | corrupted | no_snapshots`

**Acceptance Criteria**:
- [ ] Hash verification detects altered content
- [ ] Signature verification detects ID mismatch
- [ ] Chain verification detects broken links
- [ ] Returns detailed verification report
- [ ] Verification is idempotent (no side effects)

---

### NUC-0202 — Backend Safety Mode Enforcement

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 50 App B (prevent misleading records)

**Task**:
- Block ALL compliance-affecting mutations when `integrity_status ≠ valid`
- Enforce server-side (not client-side)
- Allow read-only operations
- Log all denied attempts

**Acceptance Criteria**:
- [ ] Direct API calls blocked when integrity fails
- [ ] Client cannot bypass safety mode
- [ ] Read operations still allowed
- [ ] Clear error message returned
- [ ] Denied attempts logged with reason

**Dependencies**: NUC-0201

---

### NUC-0203 — Integrity Incident Ledger

**Priority**: P1 (Strongly Recommended)  
**CFR**: 10 CFR 50 App B (anomaly tracking)

**Task**:
- Create `integrity_incidents` table
- Record: detection time, clearance time, affected snapshots
- Immutable incident records
- Query interface for inspectors

**Acceptance Criteria**:
- [ ] Corruption detection creates incident record
- [ ] Incident includes precise time window
- [ ] Clearance event updates incident
- [ ] Incidents cannot be deleted
- [ ] Inspector can query incident history

**Dependencies**: NUC-0201

---

### NUC-0204 — Action Attempt Logging

**Priority**: P1 (Strongly Recommended)  
**CFR**: Inspection & enforcement practice

**Task**:
- Log all compliance mutation attempts
- Include: timestamp, principal, action, allowed/denied, reason
- Immutable log
- Query interface

**Acceptance Criteria**:
- [ ] Allowed actions logged
- [ ] Denied actions logged with reason
- [ ] Principal attribution included
- [ ] Logs cannot be altered
- [ ] Inspector can prove non-action during corruption

**Dependencies**: NUC-0202

---

## Sprint 3: Attribution & Authentication (2 weeks)

**Gate**: Client cannot forge attribution.

**Regulatory Claim Unlocked**: "All compliance records are attributable"

### NUC-0301 — Authentication Integration

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 50 App B (signed records)

**Task**:
- Integrate OAuth/SAML for human principals
- Service account authentication for systems
- Session management
- Token validation

**Acceptance Criteria**:
- [ ] OAuth/SAML login functional
- [ ] Service accounts authenticatable
- [ ] Sessions properly managed
- [ ] Unauthenticated requests rejected

---

### NUC-0302 — Server-Side Attribution Enforcement

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 73.54

**Task**:
- Remove all client-supplied attribution fields
- Server assigns principal identity from auth context
- Make attribution immutable

**Acceptance Criteria**:
- [ ] Client cannot specify `principal_id`
- [ ] Server extracts identity from auth token
- [ ] Attribution persisted atomically with record
- [ ] Attribution cannot be modified

**Dependencies**: NUC-0301

---

### NUC-0303 — Attribution Persistence

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 50 App B

**Task**:
- Add attribution fields: `principal_id`, `principal_type`, `source_ip`, `request_id`
- Make fields non-nullable
- Include in hash computation

**Acceptance Criteria**:
- [ ] All fields populated on creation
- [ ] Fields immutable
- [ ] Included in verification
- [ ] Queryable for audit

**Dependencies**: NUC-0302

---

## Sprint 4: Retention & Legal Hold (4 weeks)

**Gate**: Legal hold must prevent deletion.

**Regulatory Claim Unlocked**: "Evidence is preserved and discoverable per NRC requirements"

### NUC-0401 — Retention Policy Engine

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 73.54 (license life + 3 years)

**Task**:
- Implement retention policy engine
- Default: license life + 3 years
- Override for specific record types
- Prevent premature deletion

**Acceptance Criteria**:
- [ ] Retention period calculated correctly
- [ ] Deletion blocked before retention expires
- [ ] Policy configurable per facility
- [ ] Deletion attempts logged

---

### NUC-0402 — Legal Hold Registry

**Priority**: P0 (Mandatory)  
**Legal Basis**: Federal spoliation law

**Task**:
- Create `legal_holds` table
- Associate holds with snapshots
- Prevent deletion while hold active
- Audit trail of hold lifecycle

**Acceptance Criteria**:
- [ ] Legal hold can be placed on snapshots
- [ ] Deletion blocked while hold active
- [ ] Hold lifecycle auditable
- [ ] Multiple holds supported

**Dependencies**: NUC-0401

---

### NUC-0403 — Deletion Prevention Under Hold

**Priority**: P0 (Mandatory)  
**CFR**: 10 CFR 50 App B

**Task**:
- Add DB constraint preventing deletion when hold exists
- Override retention policies when hold active
- Log deletion attempts

**Acceptance Criteria**:
- [ ] Deletion fails when hold exists
- [ ] Clear error message
- [ ] Attempt logged
- [ ] Cannot bypass via API or DB

**Dependencies**: NUC-0402

---

### NUC-0404 — Discovery Export

**Priority**: P1 (Strongly Recommended)  
**CFR**: 10 CFR 72.174 (retrievability)

**Task**:
- Implement discovery export API
- Export format: JSON with verification metadata
- Include chain proof
- Cryptographic attestation

**Acceptance Criteria**:
- [ ] Export includes all requested snapshots
- [ ] Verification metadata included
- [ ] Chain proof verifiable offline
- [ ] Export signed/attested

**Dependencies**: NUC-0402

---

## Sprint 5: Lifecycle Proof (4 weeks)

**Gate**: Lifecycle logs must be tamper-evident.

**Regulatory Claim Unlocked**: "Non-deletion and evidence existence are provable"

### NUC-0501 — Immutable Lifecycle Log

**Priority**: P1 (Strongly Recommended)  
**CFR**: 10 CFR 50 App B (implied)

**Task**:
- Create `record_lifecycle` table
- Log: creation, access, hold placement, deletion attempts
- Immutable log entries
- Queryable audit trail

**Acceptance Criteria**:
- [ ] All lifecycle events logged
- [ ] Logs immutable
- [ ] Deletion attempts logged (even if blocked)
- [ ] Inspector can query lifecycle

---

### NUC-0502 — Lifecycle Cryptographic Sealing

**Priority**: P2 (Recommended)  
**Legal Basis**: Discovery defense

**Task**:
- Hash lifecycle log entries
- Chain lifecycle entries
- Periodic sealing (daily/hourly)
- Independent verification

**Acceptance Criteria**:
- [ ] Lifecycle entries hashed
- [ ] Tampering detectable
- [ ] Verification independent
- [ ] Seals timestamped

**Dependencies**: NUC-0501

---

### NUC-0503 — Retention Compliance Reports

**Priority**: P1 (Strongly Recommended)  
**CFR**: 10 CFR 72.174

**Task**:
- Generate retention compliance report
- Show: oldest records, retention status, upcoming expirations
- Export format for inspectors
- Scheduled reporting

**Acceptance Criteria**:
- [ ] Report shows all retention statuses
- [ ] Upcoming expirations highlighted
- [ ] Export to PDF/JSON
- [ ] Automated scheduling

**Dependencies**: NUC-0501

---

## Progress Tracking

**Sprint 0**: ⏳ Not Started  
**Sprint 1**: ⏳ Not Started  
**Sprint 2**: ⏳ Not Started  
**Sprint 3**: ⏳ Not Started  
**Sprint 4**: ⏳ Not Started  
**Sprint 5**: ⏳ Not Started

**Overall Progress**: 0/20 tickets complete (0%)

---

**Last Updated**: 2026-01-25  
**Version**: 1.0
