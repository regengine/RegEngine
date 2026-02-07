# RegEngine Customer Verification SDK

## Purpose

This SDK enables customers to **independently verify** the cryptographic integrity of their RegEngine compliance snapshot chains **without trusting RegEngine's database or infrastructure**.

## What This Proves

When a customer runs this verification script, they mathematically validate:

1. ✅ **Content Integrity** — Snapshot data has not been modified since creation
2. ✅ **Binding Integrity** — Database records authentically link to content (cannot swap data between snapshots)
3. ✅ **Chronological Integrity** — Snapshots form an unbroken chain (cannot insert/delete snapshots retroactively)
4. ✅ **Time Integrity** — Timestamps flow forward (cannot backdate snapshots)

## Usage

### 1. Export Snapshot Chain from RegEngine

```bash
# Via RegEngine API (customer runs this)
curl -H "X-RegEngine-API-Key: $API_KEY" \
  https://api.regengine.io/energy/substations/ALPHA-001/snapshots/export \
  > my_snapshot_export.json
```

### 2. Run Verification Script

```bash
python verify_snapshot_chain.py my_snapshot_export.json
```

### 3. Review Results

**Success Output:**
```
======================================================================
RegEngine Snapshot Chain Verification Report
======================================================================

Export Metadata:
  Substation ID: ALPHA-001
  Export Time: 2026-01-30T07:53:00Z
  Total Snapshots: 47

Verification Results:
  Snapshots Verified: 47/47
  Chain Integrity: ✓ INTACT

======================================================================
✓ VERIFICATION PASSED - All cryptographic checks succeeded
======================================================================
```

**Failure Output:**
```
⚠️  Snapshot 23/47 (uuid-here): Content hash mismatch: expected abc123..., got def456...

======================================================================
RegEngine Snapshot Chain Verification Report
======================================================================

Verification Results:
  Snapshots Verified: 46/47
  Chain Integrity: ✗ BROKEN

❌ Content Hash Failures (1):
     - uuid-here

======================================================================
✗ VERIFICATION FAILED - Integrity violations detected
======================================================================
```

## How It Works

### Cryptographic Algorithm (Mirrors RegEngine Backend)

The verification script implements **the exact same** hash calculation logic as `services/energy/app/crypto.py`:

**Content Hash:**
```python
# 1. Extract content fields (not ID, not metadata)
canonical = {
    "snapshot_time": snapshot["snapshot_time"],
    "substation_id": snapshot["substation_id"],
    "system_status": snapshot["system_status"],
    "asset_states": canonicalize_dict(snapshot["asset_states"]),
    "esp_config": canonicalize_dict(snapshot["esp_config"]),
    "patch_metrics": canonicalize_dict(snapshot["patch_metrics"]),
    "active_mismatches": sorted(snapshot["active_mismatches"])
}

# 2. Serialize to canonical JSON (sorted keys, no whitespace)
canonical_json = json.dumps(canonical, sort_keys=True, separators=(',', ':'))

# 3. SHA-256 hash
content_hash = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
```

**Signature Hash:**
```python
# Binds snapshot ID to content
signature_input = f"{snapshot_id}:{content_hash}"
signature_hash = hashlib.sha256(signature_input.encode('utf-8')).hexdigest()
```

### Why This Matters

**Traditional Compliance Tools:**
> "Here's our audit report. Trust us, the data is accurate."

**RegEngine with Verification SDK:**
> "Here's our audit report. Here's the cryptographic proof. Here's the verification script. **Don't trust us — verify the math yourself.**"

## Requirements

- Python 3.7+
- No external dependencies (uses stdlib only: `hashlib`, `json`, `datetime`)

## Security

### Can RegEngine Fake Verification?

**No.** The verification script runs on the customer's machine and recalculates all hashes independently. If RegEngine modifies data in their database:
- Content hash will not match → Immediate detection
- Chain will break → Immediate detection

### What if RegEngine Modifies the Verification Script?

Customers should:
1. Hash the verification script itself on first download
2. Re-verify hash before each use
3. Store verification script on air-gapped system (not RegEngine infrastructure)

**Recommended:**
```bash
# After first download
sha256sum verify_snapshot_chain.py > verify_script.sha256

# Before each use
sha256sum -c verify_script.sha256
```

## Audit Use Case

### Scenario: SOX 404 / NERC CIP External Audit

**Auditor**: "How do I know your compliance snapshots are authentic?"

**Customer** (running SDK):
```bash
python verify_snapshot_chain.py audit_export_q4_2025.json

✓ VERIFICATION PASSED - All cryptographic checks succeeded
```

**Customer** (to auditor): 
> "I independently verified the cryptographic integrity using this open algorithm. The math proves the data is unmodified since creation. Here's the verification report for your files."

**Auditor**: 
> "Accepted. This is mathematically provable — much stronger than trust-based evidence."

## Limitations

### What This SDK Does NOT Verify

1. ❌ **Upstream data accuracy** — If incorrect data was fed into RegEngine, snapshots will correctly preserve that incorrect data
2. ❌ **Timestamp authenticity** — Server clocks can be manipulated (unless RFC 3161 timestamps added)
3. ❌ **Initial data source** — Verification starts from the first snapshot in the export, cannot verify data before RegEngine ingestion

### Trust Assumptions

You still must trust:
- RegEngine provides complete export (not hiding snapshots)
- RegEngine operators don't have conflicting snapshots in a shadow database
- Original data sources (SCADA, EHR, AD) were accurate

**Mitigation**: Request regular exports (weekly/monthly), store on customer-controlled systems.

## Integration with Audit Workflow

### Recommended Practice

**Weekly Verification:**
```bash
#!/bin/bash
# weekly_verification.sh

# 1. Export latest snapshot chain
curl -H "X-RegEngine-API-Key: $API_KEY" \
  https://api.regengine.io/energy/substations/ALPHA-001/snapshots/export \
  > backups/snapshots_$(date +%Y%m%d).json

# 2. Run verification
python verify_snapshot_chain.py backups/snapshots_$(date +%Y%m%d).json

# 3. Store verification result
if [ $? -eq 0 ]; then
  echo "$(date): PASSED" >> verification_log.txt
else
  echo "$(date): FAILED - ALERT COMPLIANCE TEAM" >> verification_log.txt
  # Send alert email/Slack notification
fi
```

**Benefits:**
- Detect tampering within 7 days (vs. annual audit cycles)
- Build historical verification log for auditors
- Air-gapped backups protect against RegEngine infrastructure compromise

## Support

**For RegEngine Customers:**
- Technical support: support@regengine.io
- SDK issues: Open ticket with export file + error output
- Custom verification needs: Contact your account manager

**For Auditors:**
- Verification methodology review: auditor-support@regengine.io
- Algorithm source code: Available in customer portal
- Independent code review: Contact Big 4 accounting firm partners

## License

Proprietary - Licensed to RegEngine customers only.  
Redistribution requires written permission.

---

**Version:** 1.0.0  
**Last Updated:** January 30, 2026  
**Compatibility:** RegEngine Energy Service v2.0+
