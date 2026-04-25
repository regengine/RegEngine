# FDA Recall Response Runbook

**Severity:** SEV1 by default -- any recall-related failure is critical
**Owner:** On-call engineer
**Last Updated:** 2026-04-08
**FSMA 204 deadline to respond:** 24 hours from FDA records request

> **The clock starts when the FDA calls or sends a records request.
> Everything in this runbook is optimized for speed under that constraint.**

---

## Table of Contents

1. [Overview: What Happens During a Recall](#1-overview)
2. [Phase 1: Intake -- FDA Request Received (T+0)](#2-phase-1-intake)
3. [Phase 2: Records Assembly -- Generate the FDA Package](#3-phase-2-records-assembly)
4. [Phase 3: Verify Data Integrity Before Submission](#4-phase-3-verify-data-integrity)
5. [Phase 4: Tenant Isolation Check](#5-phase-4-tenant-isolation-check)
6. [Phase 5: Submit to FDA](#6-phase-5-submit)
7. [When Export Hangs or Fails](#7-when-export-hangs)
8. [Emergency: Data Integrity Failure](#8-emergency-data-integrity-failure)
9. [Emergency: Manual Export (Bypass Application)](#9-emergency-manual-export)
10. [Post-Submission Checklist](#10-post-submission)
11. [Reference: Key Files and Endpoints](#11-reference)

---

## 1. Overview

RegEngine's core promise: **"When the FDA calls, produce compliant traceability records within 24 hours."**

The recall response flows through these stages:

```
FDA Records Request
  |
  v
[1] Intake: Create request case, define scope (affected TLCs, products, date range)
  |
  v
[2] Records Assembly: Query canonical events, generate FDA package (CSV + PDF + ZIP)
  |                    Services: ingestion-service (port 8000) on Railway
  |                    Database: fsma.cte_events + fsma.hash_chain on Supabase PostgreSQL
  |
  v
[3] Verify Integrity: Hash chain verification, KDE completeness check, blocking defect scan
  |                    Code: CTEPersistence.verify_chain() in services/shared/cte_persistence.py
  |
  v
[4] Tenant Isolation: Confirm RLS is enforcing -- no cross-tenant data in the export
  |                    Database: Row-Level Security policies on all fsma.* tables
  |
  v
[5] Submit: Check blocking defects, obtain signoffs, submit FDA package
            API: POST /api/v1/requests/{id}/submit via request_workflow_router.py
```

### Services Involved

| Service | Host | Role in Recall |
|---------|------|----------------|
| **Frontend** | Vercel (Next.js 15) | Recall dashboard UI, drill simulator |
| **Ingestion** | Railway (port 8000) | FDA export endpoints, package generation |
| **Admin** | Railway (port 8400) | Tenant auth, user management |
| **Compliance** | Railway (port 8500) | Scoring, rule evaluation, blocking defects |
| **Scheduler** | Railway (port 8600) | 5-minute deadline monitor cron |
| **PostgreSQL** | Supabase | Canonical events, hash chain, audit log |

---

## 2. Phase 1: Intake -- FDA Request Received (T+0)

**Goal:** Create the request case and start the 24-hour clock.

### 2.1 Create the Request Case

Via the dashboard recall page or API:

```bash
# API: Create a new request case
curl -X POST https://<railway-url>/api/v1/requests \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "<tenant_id>",
    "requesting_party": "FDA",
    "scope_description": "Records request for <product> traced by TLC <lot_code>",
    "response_due_at": "<ISO8601 timestamp, 24h from now>"
  }'
```

### 2.2 Verify the Deadline Monitor Picks It Up

The scheduler runs `check_request_deadlines()` every 5 minutes (`services/scheduler/main.py`). It classifies urgency as:

| Hours Remaining | Urgency | Log Level |
|-----------------|---------|-----------|
| < 0 | `overdue` | `logger.error` |
| < 2 | `critical` | `logger.warning` |
| < 6 | `urgent` | Normal |
| >= 6 | `normal` | Normal |

**Check it's working:**
```bash
# Via API
curl https://<railway-url>/api/v1/requests/deadlines \
  -H "Authorization: Bearer <token>" \
  -H "X-Tenant-Id: <tenant_id>"
```

Expected response includes `hours_remaining`, `urgency`, and `countdown_display`.

### 2.3 Define Scope

Identify the affected Traceability Lot Codes (TLCs), products, date ranges, and facilities. The scope determines what the export will contain.

```sql
-- Quick assessment: how many events exist for the affected TLCs?
SELECT traceability_lot_code, event_type, count(*) as event_count,
       min(event_timestamp) as earliest, max(event_timestamp) as latest
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
  AND traceability_lot_code IN ('<tlc1>', '<tlc2>')
GROUP BY traceability_lot_code, event_type
ORDER BY traceability_lot_code, event_type;
```

> **Checkpoint:** If the total event count exceeds 5,000, see [Section 7: When Export Hangs](#7-when-export-hangs) before proceeding.

---

## 3. Phase 2: Records Assembly -- Generate the FDA Package

**Goal:** Produce the FDA-compliant export package (CSV + PDF + ZIP).

### 3.1 Generate via API

The primary export endpoint is `GET /api/v1/fda/export` on the ingestion service (`services/ingestion/app/fda_export/router.py`):

```bash
# Single TLC export (most common in a recall)
curl -G "https://<railway-url>/api/v1/fda/export" \
  --data-urlencode "tlc=<lot_code>" \
  --data-urlencode "tenant_id=<tenant_id>" \
  --data-urlencode "format=package" \
  --data-urlencode "start_date=2026-01-01" \
  --data-urlencode "end_date=2026-04-08" \
  -H "Authorization: Bearer <token>" \
  -o fda_package.zip
```

**Format options:**
| Format | Output | Use When |
|--------|--------|----------|
| `package` | ZIP bundle (CSV + PDF + chain verification JSON + completeness report) | **Default for FDA submission** |
| `csv` | Raw FDA-format CSV only | Quick inspection |
| `pdf` | Human-readable PDF summary (landscape A4, subset of columns) | Reviewer walkthrough |

### 3.2 What's in the Package

The ZIP bundle (`_build_fda_package()` in `services/ingestion/app/fda_export_service.py`) contains:

| File | Contents |
|------|----------|
| `fda_traceability_<tlc>_<timestamp>.csv` | All 34 FDA columns per FSMA 204 spec |
| `fda_export_<tlc>_<timestamp>.pdf` | Human-readable summary (8 key columns) |
| `chain_verification.json` | Hash chain integrity proof |
| `completeness_summary.json` | KDE coverage analysis per CTE type |
| `manifest.json` | Package metadata, hashes, generation timestamp |

### 3.3 FDA CSV Column Specification

The export uses 34 columns defined in `FDA_COLUMNS` (`fda_export_service.py:29-65`):

**Core fields:** TLC, Product Description, Quantity, UOM, Event Type (CTE), Event Date/Time, Location GLN/Name, Ship From/To, Immediate Previous Source, TLC Source, Source Document

**Integrity fields:** Record Hash (SHA-256), Chain Hash

**KDE fields:** Reference Document Number, Receive/Ship/Harvest/Cooling/Packing/Transformation/Landing Date, Receiving Location, Temperature, Carrier, Growing Area, Additional KDEs (JSON)

**FSMA 204 required:** System Entry Timestamp (when the record was entered into the system, maps to `ingested_at` column)

### 3.4 Check Response Headers

The export endpoint returns compliance metadata in response headers:

```
X-Export-Hash:          SHA-256 of the CSV content
X-Package-Hash:         SHA-256 of the ZIP bundle (package format only)
X-Record-Count:         Number of events in the export
X-Chain-Integrity:      VERIFIED or UNVERIFIED
X-KDE-Coverage:         0.0 to 1.0 (fraction of required KDEs present)
X-KDE-Warnings:         Count of events with missing required KDEs
X-Compliance-Warning:   Present only if KDE coverage < 80%
```

**Stop and investigate if:**
- `X-Chain-Integrity: UNVERIFIED` -- do NOT submit. See [Section 8](#8-emergency-data-integrity-failure).
- `X-KDE-Coverage` < 0.80 -- the FDA may reject incomplete records. Assess whether missing KDEs can be backfilled before submission.

### 3.5 Export All Events (Full Tenant Export)

For broad recalls affecting multiple TLCs:

```bash
curl -G "https://<railway-url>/api/v1/fda/export/all" \
  --data-urlencode "tenant_id=<tenant_id>" \
  --data-urlencode "format=package" \
  --data-urlencode "event_type=SHIPPING" \
  -H "Authorization: Bearer <token>" \
  -o fda_full_export.zip
```

> **Warning:** The `/export/all` endpoint has a hard limit of 10,000 events per query (`query_all_events(..., limit=10000)` in `services/ingestion/app/fda_export/router.py`). For tenants with more events, filter by date range or event type to stay under the limit.

---

## 4. Phase 3: Verify Data Integrity Before Submission

**Goal:** Prove the export is tamper-free and complete before sending to the FDA.

### 4.1 Hash Chain Verification via API

```bash
# Verify a previous export's integrity
curl -X POST "https://<railway-url>/api/v1/fda/export/verify" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"export_hash": "<hash_from_X-Export-Hash_header>", "tenant_id": "<tenant_id>"}'
```

### 4.2 Hash Chain Verification via SQL

The hash chain lives in `fsma.hash_chain`. Each entry links to the previous via SHA-256:

```
chain_hash = SHA-256( previous_chain_hash | event_hash )
```

The genesis entry uses `'GENESIS'` as the seed (see `compute_chain_hash()` in `cte_persistence.py:142-149`).

**Full chain verification query:**

```sql
-- Step 1: Check for sequence gaps (should return 0 rows)
WITH chain AS (
    SELECT sequence_num,
           event_hash,
           previous_chain_hash,
           chain_hash,
           LAG(chain_hash) OVER (ORDER BY sequence_num) AS expected_prev,
           LAG(sequence_num) OVER (ORDER BY sequence_num) AS prev_seq
    FROM fsma.hash_chain
    WHERE tenant_id = '<tenant_id>'
    ORDER BY sequence_num
)
SELECT sequence_num, 'SEQUENCE_GAP' AS error_type,
       format('Expected sequence %s, got %s', prev_seq + 1, sequence_num) AS detail
FROM chain
WHERE prev_seq IS NOT NULL AND sequence_num != prev_seq + 1

UNION ALL

-- Step 2: Check previous_chain_hash linkage (should return 0 rows)
SELECT sequence_num, 'CHAIN_BREAK' AS error_type,
       format('stored prev %s != expected %s',
              left(previous_chain_hash, 16), left(expected_prev, 16)) AS detail
FROM chain
WHERE prev_seq IS NOT NULL AND previous_chain_hash != expected_prev

UNION ALL

-- Step 3: Check genesis entry has null previous (should return 0 rows)
SELECT sequence_num, 'GENESIS_ERROR' AS error_type,
       'Genesis entry has non-null previous_chain_hash' AS detail
FROM chain
WHERE prev_seq IS NULL AND previous_chain_hash IS NOT NULL

ORDER BY sequence_num;
```

> **If any rows are returned, STOP. See [Section 8](#8-emergency-data-integrity-failure).**

**Recompute and verify chain hashes** (requires application code because the hash formula is `SHA-256(prev_hash|event_hash)`):

```python
# Run from project root with database access
from shared.cte_persistence import CTEPersistence
from shared.database import SessionLocal

session = SessionLocal()
persistence = CTEPersistence(session)
result = persistence.verify_chain(tenant_id="<tenant_id>")

print(f"Valid: {result.valid}")
print(f"Chain length: {result.chain_length}")
print(f"Checked at: {result.checked_at}")
if result.errors:
    for error in result.errors:
        print(f"  ERROR: {error}")
session.close()
```

The `verify_chain()` method (`cte_persistence.py:966-1030`) walks the entire chain from genesis to head, recomputing each `chain_hash` as `SHA-256(previous_chain_hash|event_hash)` and comparing to the stored value. Any mismatch means tampering or corruption.

### 4.3 Merkle Tree Verification (Supplemental)

For O(log n) inclusion proofs (useful for proving a specific event is in the chain without walking the whole thing):

```python
merkle_result = persistence.verify_chain_merkle(tenant_id="<tenant_id>")
print(f"Merkle root: {merkle_result.merkle_root}")
print(f"Tree depth: {merkle_result.tree_depth}")
print(f"Valid: {merkle_result.valid}")
```

### 4.4 KDE Completeness Check

The export includes a completeness summary computed by `_build_completeness_summary()` (`fda_export_service.py:251-294`). It checks each event's KDEs against `REQUIRED_KDES_BY_CTE` for its CTE type.

```sql
-- Quick check: events missing critical KDEs
SELECT e.id, e.event_type, e.traceability_lot_code,
       e.event_timestamp, e.validation_status
FROM fsma.cte_events e
WHERE e.tenant_id = '<tenant_id>'
  AND e.validation_status = 'warning'
ORDER BY e.event_timestamp DESC;
```

### 4.5 Check Blocking Defects

Before submission, the request workflow checks 7 blocking conditions via `check_blocking_defects()` (`services/shared/request_workflow/assembly.py:458-722`):

```bash
curl "https://<railway-url>/api/v1/requests/<request_case_id>/blockers" \
  -H "Authorization: Bearer <token>" \
  -H "X-Tenant-Id: <tenant_id>"
```

**Blocking conditions:**

| # | Blocker Type | What It Means | Resolution |
|---|-------------|---------------|------------|
| 1 | `critical_rule_failure` | A severity=critical FSMA rule failed for an event | Fix the data or waive the exception with documented justification |
| 2 | `unresolved_critical_exception` | A critical exception case is still open | Resolve or waive via exception queue |
| 3 | `unevaluated_event` | An in-scope event has zero rule evaluations | Run compliance evaluation on the event |
| 4 | `missing_signoff` | Required signoffs not obtained | Obtain `scope_approval` and `final_approval` |
| 5 | `identity_ambiguity` | Entity matches >= 85% confidence are unresolved | Resolve in identity review queue |
| 6 | `stale_evaluations` | Event was modified or rule version changed after evaluation | Re-run compliance evaluation |
| 7 | _(warnings only)_ | Non-critical rule failures | Document but don't block |

**Required signoffs** (enforced by `REQUIRED_SIGNOFF_TYPES` constant):
- `scope_approval` -- confirms the scope of the recall response
- `final_approval` -- authorizes FDA submission

```bash
# Add a required signoff
curl -X POST "https://<railway-url>/api/v1/requests/<request_case_id>/signoffs" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "signoff_type": "scope_approval",
    "signed_by": "user@company.com",
    "notes": "Scope confirmed: all Shipping and Receiving events for TLC ABC-123"
  }'
```

---

## 5. Phase 4: Tenant Isolation Check

**Goal:** Confirm the export contains ONLY the target tenant's data.

### 5.1 Verify RLS Is Active

```sql
-- Check that RLS is enabled on the critical tables
SELECT schemaname, tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'fsma'
  AND tablename IN ('cte_events', 'hash_chain', 'cte_event_kdes',
                     'request_cases', 'request_signoffs', 'fda_export_log')
ORDER BY tablename;
-- All rows should show rowsecurity = true
```

### 5.2 Test Tenant Isolation

```sql
-- Connect as a non-superuser role, set tenant context
SET app.current_tenant = '<tenant_id>';

-- Verify: query for events from a DIFFERENT tenant (should return 0)
SELECT count(*) FROM fsma.cte_events
WHERE tenant_id != current_setting('app.current_tenant');
-- MUST return 0. If it returns > 0, STOP. RLS is broken.

-- Verify: the export query returns only our tenant's data
SELECT count(*), count(DISTINCT tenant_id)
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>';
-- count(DISTINCT tenant_id) MUST be exactly 1
```

### 5.3 Cross-Check Export Content

After generating the package, spot-check that the CSV contains only the target tenant's events:

```bash
# Extract and check the CSV
unzip -p fda_package.zip '*.csv' | head -5
# Verify TLCs match the expected scope
unzip -p fda_package.zip '*.csv' | cut -d',' -f1 | sort -u | head -20
```

---

## 6. Phase 5: Submit to FDA

**Goal:** Submit the verified package through the request workflow.

### 6.1 Submit via API

```bash
curl -X POST "https://<railway-url>/api/v1/requests/<request_case_id>/submit" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"force": false}'
```

If `force: false` (default), submission is blocked if any of the 7 blocking defect types are present. The endpoint returns HTTP 422 with the blocker details.

### 6.2 Force Submit (Emergency Override)

If the 24-hour deadline is imminent and blocking defects cannot be resolved in time:

```bash
curl -X POST "https://<railway-url>/api/v1/requests/<request_case_id>/submit" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"force": true}'
```

> **Warning:** `force: true` bypasses blocking defects but logs the override in the audit trail. Use only when the cost of missing the FDA deadline exceeds the cost of submitting with known defects. Document the justification.

### 6.3 Verify Submission

```bash
# Check the export audit log
curl "https://<railway-url>/api/v1/fda/export/history" \
  -H "Authorization: Bearer <token>" \
  -G --data-urlencode "tenant_id=<tenant_id>"
```

---

## 7. When Export Hangs or Fails

### 7.1 The 5,000+ Event Threshold

The FDA export loads all matching events into memory, generates CSV via `csv.DictWriter`, and (for package format) also generates a PDF and ZIP. The bottlenecks at scale:

| Event Count | Expected Behavior | Likely Issue |
|------------|-------------------|--------------|
| < 1,000 | Completes in < 5s | No issues |
| 1,000 - 5,000 | Completes in 5-30s | May hit Railway request timeout |
| 5,000 - 10,000 | May timeout | Memory pressure, PDF generation slow |
| > 10,000 | Hard limit reached | `/export/all` caps at 10,000 (`limit=10000`) |

### 7.2 Diagnosis

```bash
# Check Railway logs for the ingestion service
# Look for: fda_export_generated (success) or fda_export_failed (failure)

# Check active database queries
psql $DATABASE_URL -c "
  SELECT pid, now() - query_start AS duration, state, left(query, 100) AS query
  FROM pg_stat_activity
  WHERE state != 'idle' AND query ILIKE '%cte_events%'
  ORDER BY duration DESC;
"

# Check for lock contention (bulk import running during recall?)
psql $DATABASE_URL -c "
  SELECT blocked_locks.pid AS blocked_pid,
         blocking_locks.pid AS blocking_pid,
         blocked_activity.query AS blocked_query
  FROM pg_catalog.pg_locks blocked_locks
  JOIN pg_catalog.pg_locks blocking_locks
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
  JOIN pg_catalog.pg_stat_activity blocked_activity
    ON blocked_activity.pid = blocked_locks.pid
  WHERE NOT blocked_locks.granted;
"
```

### 7.3 Mitigations for Large Exports

**Option A: Filter the scope.** Reduce the date range or filter by event type:
```bash
curl -G "https://<railway-url>/api/v1/fda/export" \
  --data-urlencode "tlc=<lot_code>" \
  --data-urlencode "tenant_id=<tenant_id>" \
  --data-urlencode "format=csv" \
  --data-urlencode "start_date=2026-03-01" \
  --data-urlencode "end_date=2026-04-08" \
  -H "Authorization: Bearer <token>" \
  -o partial_export.csv
```

**Option B: Export CSV only (skip PDF).** PDF generation (`fpdf`) is the slowest part -- it renders each row into positioned cells. Use `format=csv` instead of `format=package`:
```bash
# CSV-only export skips PDF generation entirely
curl -G "https://<railway-url>/api/v1/fda/export" \
  --data-urlencode "tlc=<lot_code>" \
  --data-urlencode "tenant_id=<tenant_id>" \
  --data-urlencode "format=csv" \
  -H "Authorization: Bearer <token>" \
  -o fda_export.csv
```

**Option C: Export in batches by TLC.** The `/export/all` endpoint deduplicates by fetching per-TLC batches of 50 (`services/ingestion/app/fda_export/router.py`). If this is too slow, export one TLC at a time using `/export?tlc=<each_tlc>`.

**Option D: Direct SQL export (emergency).** See [Section 9](#9-emergency-manual-export).

### 7.4 If Railway Request Timeout Hits

Railway's default request timeout may be shorter than a large export needs.

1. Check Railway dashboard for the ingestion service's request timeout setting
2. If the export takes > 60s, it's likely timing out at the reverse proxy layer
3. Mitigation: use `format=csv` (faster), narrow the date range, or fall back to direct SQL export

---

## 8. Emergency: Data Integrity Failure

**This is a P0 incident.** If hash chain verification fails, the export cannot be trusted.

### 8.1 Triage

```python
# Run full verification to identify the exact break point
from shared.cte_persistence import CTEPersistence
from shared.database import SessionLocal

session = SessionLocal()
persistence = CTEPersistence(session)
result = persistence.verify_chain(tenant_id="<tenant_id>")

if not result.valid:
    print(f"CHAIN BROKEN - {len(result.errors)} errors found:")
    for error in result.errors:
        print(f"  {error}")
        # Errors have three patterns:
        #   "Sequence gap: expected N, got M"
        #   "Chain break at seq=N: stored prev X != expected Y"
        #   "Tamper detected at seq=N: recomputed chain_hash X != stored Y"
session.close()
```

### 8.2 Classify the Break

| Error Pattern | Likely Cause | Severity |
|---------------|-------------|----------|
| `Sequence gap` | Event deleted or migration error | Critical -- data loss |
| `Chain break` | Concurrent write race condition or manual DB edit | Critical -- chain corrupted |
| `Tamper detected` | Event hash changed after insertion or malicious tampering | Critical -- integrity violated |
| `Genesis entry has non-null previous_chain_hash` | Migration or seed data error | High -- chain root invalid |

### 8.3 Determine Blast Radius

```sql
-- How many events are affected?
-- Find the first broken sequence number from the verify_chain output
-- All events AT or AFTER that sequence are suspect
SELECT count(*) AS affected_events
FROM fsma.hash_chain
WHERE tenant_id = '<tenant_id>'
  AND sequence_num >= <first_broken_sequence>;

-- What TLCs are affected?
SELECT DISTINCT e.traceability_lot_code
FROM fsma.cte_events e
JOIN fsma.hash_chain h ON h.cte_event_id = e.id::text AND h.tenant_id = e.tenant_id
WHERE h.tenant_id = '<tenant_id>'
  AND h.sequence_num >= <first_broken_sequence>;
```

### 8.4 Do NOT Attempt

- **Do NOT delete hash chain entries.** The chain is append-only.
- **Do NOT update event hashes directly.** This makes the tampering permanent.
- **Do NOT submit the export to the FDA with `UNVERIFIED` chain integrity.**

### 8.5 Escalation

1. Notify the compliance officer immediately
2. Document the exact error output from `verify_chain()`
3. Determine if the break affects events in the FDA request scope
4. If the break is OUTSIDE the request scope, the export for unaffected TLCs may still be valid -- verify by checking per-TLC event hashes individually
5. If the break is INSIDE the scope, fall back to [Section 9: Manual Export](#9-emergency-manual-export) and note the integrity gap in the FDA submission

---

## 9. Emergency: Manual Export (Bypass Application)

**Use only when:** The application export endpoint is down/hanging AND the 24-hour FDA deadline is imminent.

### 9.1 Direct SQL to FDA-Format CSV

```sql
-- Connect to Supabase PostgreSQL directly
-- This query produces output matching the FDA_COLUMNS specification

\copy (
  SELECT
    e.traceability_lot_code AS "Traceability Lot Code (TLC)",
    e.product_description AS "Product Description",
    e.quantity AS "Quantity",
    e.unit_of_measure AS "Unit of Measure",
    e.event_type AS "Event Type (CTE)",
    to_char(e.event_timestamp, 'YYYY-MM-DD') AS "Event Date",
    to_char(e.event_timestamp, 'HH24:MI:SS') AS "Event Time",
    e.location_gln AS "Location GLN",
    e.location_name AS "Location Name",
    -- KDEs are in a separate table, join them
    MAX(CASE WHEN k.kde_key = 'ship_from_gln' THEN k.kde_value END) AS "Ship From GLN",
    MAX(CASE WHEN k.kde_key = 'ship_from_location' THEN k.kde_value END) AS "Ship From Name",
    MAX(CASE WHEN k.kde_key = 'ship_to_gln' THEN k.kde_value END) AS "Ship To GLN",
    MAX(CASE WHEN k.kde_key = 'ship_to_location' THEN k.kde_value
             WHEN k.kde_key = 'receiving_location' THEN k.kde_value END) AS "Ship To Name",
    MAX(CASE WHEN k.kde_key = 'immediate_previous_source' THEN k.kde_value END) AS "Immediate Previous Source",
    MAX(CASE WHEN k.kde_key = 'tlc_source_gln' THEN k.kde_value END) AS "TLC Source GLN",
    MAX(CASE WHEN k.kde_key = 'tlc_source_fda_reg' THEN k.kde_value END) AS "TLC Source FDA Registration",
    e.source AS "Source Document",
    e.sha256_hash AS "Record Hash (SHA-256)",
    e.chain_hash AS "Chain Hash",
    MAX(CASE WHEN k.kde_key = 'reference_document_number' THEN k.kde_value END) AS "Reference Document Number",
    MAX(CASE WHEN k.kde_key = 'receive_date' THEN k.kde_value END) AS "Receive Date",
    MAX(CASE WHEN k.kde_key = 'ship_date' THEN k.kde_value END) AS "Ship Date",
    MAX(CASE WHEN k.kde_key = 'harvest_date' THEN k.kde_value END) AS "Harvest Date",
    MAX(CASE WHEN k.kde_key = 'cooling_date' THEN k.kde_value END) AS "Cooling Date",
    MAX(CASE WHEN k.kde_key = 'packing_date' THEN k.kde_value END) AS "Packing Date",
    MAX(CASE WHEN k.kde_key = 'transformation_date' THEN k.kde_value END) AS "Transformation Date",
    MAX(CASE WHEN k.kde_key = 'landing_date' THEN k.kde_value END) AS "Landing Date",
    MAX(CASE WHEN k.kde_key = 'receiving_location' THEN k.kde_value END) AS "Receiving Location",
    MAX(CASE WHEN k.kde_key = 'temperature' THEN k.kde_value END) AS "Temperature (F)",
    MAX(CASE WHEN k.kde_key = 'carrier' THEN k.kde_value END) AS "Carrier",
    MAX(CASE WHEN k.kde_key = 'growing_area_name' THEN k.kde_value END) AS "Growing Area",
    e.ingested_at AS "System Entry Timestamp"
  FROM fsma.cte_events e
  LEFT JOIN fsma.cte_event_kdes k ON k.cte_event_id = e.id AND k.tenant_id = e.tenant_id
  WHERE e.tenant_id = '<tenant_id>'
    AND e.traceability_lot_code = '<lot_code>'
  GROUP BY e.id, e.traceability_lot_code, e.product_description,
           e.quantity, e.unit_of_measure, e.event_type,
           e.event_timestamp, e.location_gln, e.location_name,
           e.source, e.sha256_hash, e.chain_hash, e.ingested_at
  ORDER BY e.event_timestamp
) TO '/tmp/fda_emergency_export.csv' WITH CSV HEADER;
```

### 9.2 Verify the Emergency Export

```sql
-- Count events in export vs database
SELECT count(*) FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
  AND traceability_lot_code = '<lot_code>';

-- Spot-check: first and last event hashes
SELECT traceability_lot_code, sha256_hash, event_timestamp
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
  AND traceability_lot_code = '<lot_code>'
ORDER BY event_timestamp ASC
LIMIT 1;

SELECT traceability_lot_code, sha256_hash, event_timestamp
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
  AND traceability_lot_code = '<lot_code>'
ORDER BY event_timestamp DESC
LIMIT 1;
```

### 9.3 Document the Manual Export

If you used the emergency bypass, log it:

```sql
-- Record the manual export in the audit log
INSERT INTO fsma.fda_export_log (
    tenant_id, export_hash, record_count,
    query_tlc, generated_by, created_at
) VALUES (
    '<tenant_id>',
    '<sha256 of the exported CSV file>',
    <record_count>,
    '<lot_code>',
    'manual_emergency_export',
    NOW()
);
```

---

## 10. Post-Submission Checklist

- [ ] Export audit log entry exists (`GET /api/v1/fda/export/history`)
- [ ] Hash chain verification passed (`verify_chain()` returned `valid: true`)
- [ ] Tenant isolation confirmed (RLS check passed)
- [ ] All blocking defects resolved (or force-submitted with documented justification)
- [ ] Both required signoffs obtained (`scope_approval` + `final_approval`)
- [ ] Package hash recorded for tamper detection of the submitted artifact
- [ ] If manual export was used, emergency export logged in `fda_export_log`
- [ ] Deadline monitor shows the case status as `submitted`
- [ ] Postmortem scheduled if any failures occurred during the process

---

## 11. Reference: Key Files and Endpoints

### Endpoints

| Endpoint | Method | Service | Purpose |
|----------|--------|---------|---------|
| `/api/v1/fda/export` | GET | Ingestion (8000) | Generate FDA export for a TLC |
| `/api/v1/fda/export/all` | GET | Ingestion (8000) | Export all events (limit 10K) |
| `/api/v1/fda/export/history` | GET | Ingestion (8000) | Export audit log |
| `/api/v1/fda/export/verify` | POST | Ingestion (8000) | Verify export integrity |
| `/api/v1/requests` | POST | Ingestion (8000) | Create request case |
| `/api/v1/requests/{id}/blockers` | GET | Ingestion (8000) | Check blocking defects |
| `/api/v1/requests/{id}/submit` | POST | Ingestion (8000) | Submit FDA package |
| `/api/v1/requests/{id}/signoffs` | POST | Ingestion (8000) | Add required signoff |
| `/api/v1/requests/deadlines` | GET | Ingestion (8000) | Check all deadline statuses |

### Source Files

| File | What It Does |
|------|-------------|
| `services/ingestion/app/fda_export/router.py` | HTTP endpoints for FDA export |
| `services/ingestion/app/fda_export_service.py` | CSV/PDF/ZIP generation, FDA column spec, completeness analysis |
| `services/ingestion/app/request_workflow_router.py` | Request lifecycle endpoints (blockers, submit, signoffs) |
| `services/shared/request_workflow/assembly.py` | `check_blocking_defects()` (7 checks), `add_signoff()`, `check_deadline_status()` |
| `services/shared/request_workflow/submission.py` | `submit_package()` with force override |
| `services/shared/cte_persistence.py` | `verify_chain()`, `verify_chain_merkle()`, `query_events_by_tlc()`, `log_export()` |
| `services/shared/audit_logging.py` | `AuditIntegrity.verify_chain()` (HMAC-SHA256), `AuditLogger` |
| `services/shared/canonical_event.py` | `TraceabilityEvent` model, normalization functions |
| `services/shared/exception_queue.py` | `ExceptionQueueService` for blocking exception management |
| `services/shared/identity_resolution.py` | `IdentityResolutionService` for entity disambiguation |
| `services/scheduler/main.py` | 5-minute `check_request_deadlines()` cron |
| `services/scheduler/app/compliance_integration.py` | FDA recall alert matching (3-tier: lot code, supplier, FTL keyword) |

### Database Tables

| Table | Role in Recall |
|-------|----------------|
| `fsma.cte_events` | Canonical traceability events (source of truth) |
| `fsma.cte_event_kdes` | Key Data Elements per event |
| `fsma.hash_chain` | SHA-256 chain (sequence_num, event_hash, previous_chain_hash, chain_hash) |
| `fsma.request_cases` | FDA request lifecycle (10-stage state machine) |
| `fsma.request_signoffs` | Required approvals (scope_approval, final_approval) |
| `fsma.rule_evaluations` | Compliance rule results per event |
| `fsma.exception_cases` | Blocking exceptions requiring resolution |
| `fsma.identity_review_queue` | Ambiguous entity matches (>= 85% confidence) |
| `fsma.fda_export_log` | Audit trail of all exports |
| `fsma.compliance_alerts` | FDA recall/warning alerts matched to tenants |

### Hash Chain Formula

```
event_hash   = SHA-256(event_id | event_type | tlc | product | qty | uom | gln | location | timestamp | json(kdes))
chain_hash   = SHA-256(previous_chain_hash | event_hash)     -- or SHA-256('GENESIS' | event_hash) for first entry
```

Implementation: `compute_event_hash()` and `compute_chain_hash()` in `services/shared/cte_persistence.py:115-149`.
