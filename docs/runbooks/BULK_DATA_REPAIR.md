# Bulk Data Repair Runbook

**Severity:** SEV2+ (any data integrity issue is at least High)
**Owner:** On-call engineer + compliance officer sign-off
**Last Updated:** 2026-04-08

> **The cardinal rule: you NEVER delete canonical events or hash chain entries.**
> The hash chain is append-only. Deleting a row breaks every subsequent chain hash.
> All repairs go through the **amendment chain** via `supersedes_event_id`.

---

## Table of Contents

1. [Before You Start: Understand the Two Table Systems](#1-before-you-start)
2. [Phase 1: Identify Affected Events](#2-identify-affected-events)
3. [Phase 2: Assess Blast Radius](#3-assess-blast-radius)
4. [Phase 3: Construct Amendment Records](#4-construct-amendment-records)
5. [Phase 4: Execute the Repair](#5-execute-the-repair)
6. [Phase 5: Verify Hash Chain Integrity After Repair](#6-verify-hash-chain)
7. [Phase 6: Re-run Compliance Evaluation](#7-rerun-compliance)
8. [Phase 7: Communicate to Affected Tenant](#8-communicate)
9. [RLS Implications of Bulk Operations](#9-rls-implications)
10. [Common Repair Scenarios](#10-common-scenarios)
11. [What to NEVER Do](#11-never-do)
12. [Reference](#12-reference)

---

## 1. Before You Start: Understand the Two Table Systems

RegEngine has two event storage systems that coexist during the migration period. Repairs must target the correct table.

### Legacy System (V002)

| Table | Role |
|-------|------|
| `fsma.cte_events` | Flat CTE records — `id`, `sha256_hash`, `chain_hash`, `validation_status` |
| `fsma.cte_kdes` | Key-value KDE storage linked to `cte_events.id` |
| `fsma.hash_chain` | Append-only chain linked to `cte_events.id` |

- **No `supersedes_event_id` column.** Legacy events can't form amendment chains directly.
- **No `status` column** (only `validation_status`: valid/rejected/warning).
- This is what `CTEPersistence` in `services/shared/cte_persistence.py` writes to.
- The FDA export endpoints read from this table.

### Canonical System (V043)

| Table | Role |
|-------|------|
| `fsma.traceability_events` | Full canonical model with dual payload, provenance, amendment chain |
| KDEs stored inline | `kdes JSONB` column (not a separate table) |
| `fsma.hash_chain` | Same chain, shared between both systems |

- **Has `supersedes_event_id`** — points to the event this record corrects.
- **Has `status`** — `active`, `superseded`, `rejected`, `draft`.
- **Has `amended_at`** — timestamp of when the amendment was made.
- Schema defined in `services/shared/canonical_event.py` (`TraceabilityEvent` model).

### Which Table Am I Repairing?

```sql
-- Check if the affected event exists in the legacy table
SELECT id, event_type, traceability_lot_code, sha256_hash
FROM fsma.cte_events WHERE id = '<event_id>';

-- Check if it exists in the canonical table
SELECT event_id, event_type, traceability_lot_code, status, supersedes_event_id
FROM fsma.traceability_events WHERE event_id = '<event_id>';
```

Most production data is currently in `fsma.cte_events` (legacy). The repair patterns in this runbook cover both systems.

---

## 2. Phase 1: Identify Affected Events

### 2.1 By Symptom: Wrong Data in an Event

```sql
-- Find events with a specific incorrect value
SELECT id, tenant_id, event_type, traceability_lot_code,
       product_description, quantity, unit_of_measure,
       location_gln, location_name, event_timestamp,
       sha256_hash, validation_status, ingested_at
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
  AND traceability_lot_code = '<affected_tlc>'
ORDER BY event_timestamp;
```

### 2.2 By Symptom: Missing KDEs

```sql
-- Events missing a required KDE (legacy system)
SELECT e.id, e.event_type, e.traceability_lot_code, e.event_timestamp
FROM fsma.cte_events e
WHERE e.tenant_id = '<tenant_id>'
  AND e.event_type = 'shipping'
  AND NOT EXISTS (
      SELECT 1 FROM fsma.cte_kdes k
      WHERE k.cte_event_id = e.id
        AND k.kde_key = 'ship_date'
  )
ORDER BY e.event_timestamp;

-- Events missing required KDEs (canonical system — KDEs are inline JSONB)
SELECT event_id, event_type, traceability_lot_code, event_timestamp
FROM fsma.traceability_events
WHERE tenant_id = '<tenant_id>'
  AND event_type = 'shipping'
  AND status = 'active'
  AND (kdes->>'ship_date' IS NULL OR kdes->>'ship_date' = '')
ORDER BY event_timestamp;
```

### 2.3 By Symptom: Duplicate Events

```sql
-- Find duplicates that slipped past idempotency (same TLC + type + timestamp)
SELECT traceability_lot_code, event_type, event_timestamp,
       count(*) AS duplicate_count,
       array_agg(id ORDER BY ingested_at) AS event_ids
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
GROUP BY traceability_lot_code, event_type, event_timestamp
HAVING count(*) > 1
ORDER BY duplicate_count DESC;
```

### 2.4 By Symptom: Wrong Event Type

```sql
-- Events classified as the wrong CTE type
-- (e.g., a receiving event incorrectly labeled as shipping)
SELECT id, event_type, traceability_lot_code, event_timestamp,
       location_name, source
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
  AND traceability_lot_code = '<tlc>'
  AND event_type = '<wrong_type>'
ORDER BY event_timestamp;
```

### 2.5 By Symptom: Ingestion Bug Corrupted a Batch

```sql
-- Find all events from a specific ingestion batch (by source and time window)
SELECT id, event_type, traceability_lot_code, source,
       event_timestamp, ingested_at, validation_status
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
  AND source = '<source_system>'
  AND ingested_at BETWEEN '<batch_start>' AND '<batch_end>'
ORDER BY ingested_at;

-- Canonical system: find by ingestion run ID
SELECT event_id, event_type, traceability_lot_code, status
FROM fsma.traceability_events
WHERE tenant_id = '<tenant_id>'
  AND ingestion_run_id = '<run_id>'
ORDER BY created_at;
```

---

## 3. Phase 2: Assess Blast Radius

Before repairing anything, understand how far the damage reaches.

### 3.1 Count Affected Events

```sql
-- How many events need repair?
SELECT count(*) AS affected_count,
       count(DISTINCT traceability_lot_code) AS affected_tlcs,
       array_agg(DISTINCT event_type) AS affected_cte_types
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
  AND <your_filter_condition>;
```

### 3.2 Check Downstream Dependencies

Each corrupted event may have downstream records that reference it:

```sql
-- Hash chain entries for affected events
SELECT h.sequence_num, h.cte_event_id, h.event_hash, h.chain_hash
FROM fsma.hash_chain h
WHERE h.tenant_id = '<tenant_id>'
  AND h.cte_event_id IN (<affected_event_ids>)
ORDER BY h.sequence_num;

-- Rule evaluations referencing affected events
SELECT re.event_id, re.rule_id, re.result, re.evaluated_at
FROM fsma.rule_evaluations re
WHERE re.tenant_id = '<tenant_id>'
  AND re.event_id = ANY(ARRAY[<affected_event_ids>]::text[]);

-- Exception cases linked to affected events
SELECT ec.id, ec.severity, ec.status, ec.linked_event_ids
FROM fsma.exception_cases ec
WHERE ec.tenant_id = '<tenant_id>'
  AND ec.linked_event_ids && ARRAY[<affected_event_ids>]::text[];

-- FDA exports that included affected events
SELECT el.id, el.query_tlc, el.record_count, el.export_hash, el.generated_at
FROM fsma.fda_export_log el
WHERE el.tenant_id = '<tenant_id>'
  AND el.query_tlc IN (
      SELECT DISTINCT traceability_lot_code
      FROM fsma.cte_events
      WHERE id IN (<affected_event_ids>)
  );
```

### 3.3 Determine Repair Strategy

| Affected Events | Downstream Impact | Strategy |
|----------------|-------------------|----------|
| 1-10 events | No FDA exports sent | Single-event amendment (Section 4.1) |
| 10-100 events | No FDA exports sent | Batch amendment (Section 4.2) |
| 100+ events | No FDA exports sent | Scripted batch amendment (Section 4.3) |
| Any count | FDA exports already sent | Amendment + re-export + tenant notification (Section 8) |
| Any count | Hash chain broken | STOP -- see [FDA_RECALL_RESPONSE.md Section 8](FDA_RECALL_RESPONSE.md#8-emergency-data-integrity-failure) first |

---

## 4. Phase 3: Construct Amendment Records

### The Amendment Pattern

Amendments don't modify or delete the original. They create a **new** corrected event and mark the old one as superseded:

```
Original event (id: AAA, status: active)
  |
  | [repair operation]
  |
  v
Original event (id: AAA, status: superseded, amended_at: NOW())
New event      (id: BBB, status: active, supersedes_event_id: AAA)
```

The new event gets its own hash chain entry. The original's chain entry remains untouched.

### 4.1 Single Event Amendment (Canonical System)

For events in `fsma.traceability_events`:

```sql
BEGIN;

-- Step 1: Mark the original as superseded
UPDATE fsma.traceability_events
SET status = 'superseded',
    amended_at = NOW()
WHERE event_id = '<original_event_id>'
  AND tenant_id = '<tenant_id>'
  AND status = 'active';
-- VERIFY: exactly 1 row updated

-- Step 2: Insert the corrected event
INSERT INTO fsma.traceability_events (
    event_id,
    tenant_id,
    source_system,
    source_record_id,
    ingestion_run_id,
    event_type,
    event_timestamp,
    event_timezone,
    product_reference,
    lot_reference,
    traceability_lot_code,
    quantity,
    unit_of_measure,
    from_entity_reference,
    to_entity_reference,
    from_facility_reference,
    to_facility_reference,
    transport_reference,
    kdes,
    raw_payload,
    normalized_payload,
    provenance_metadata,
    confidence_score,
    status,
    supersedes_event_id,
    schema_version,
    created_at,
    ingested_at
) SELECT
    gen_random_uuid(),               -- new event_id
    tenant_id,
    source_system,
    source_record_id,
    ingestion_run_id,
    event_type,                      -- keep same (or change if that's the fix)
    event_timestamp,
    event_timezone,
    product_reference,
    lot_reference,
    traceability_lot_code,
    quantity,                         -- keep same (or change if that's the fix)
    unit_of_measure,
    from_entity_reference,
    to_entity_reference,
    from_facility_reference,
    to_facility_reference,
    transport_reference,
    kdes || '{"ship_date": "2026-03-15"}'::jsonb,  -- <-- THE FIX: merge corrected KDEs
    raw_payload,
    normalized_payload,
    provenance_metadata || jsonb_build_object(
        'amendment_reason', 'Missing ship_date KDE — bulk data repair',
        'amendment_timestamp', NOW()::text,
        'amendment_operator', 'christopher@regengine.com'
    ),
    confidence_score,
    'active',                        -- new event is active
    '<original_event_id>'::uuid,     -- points back to the original
    schema_version,
    NOW(),                           -- new created_at
    ingested_at                      -- preserve original ingestion time
FROM fsma.traceability_events
WHERE event_id = '<original_event_id>'
  AND tenant_id = '<tenant_id>';
-- VERIFY: exactly 1 row inserted

COMMIT;
```

### 4.2 Single Event Amendment (Legacy System)

The legacy `fsma.cte_events` table has no `supersedes_event_id` or `status` column. The repair strategy is different:

```sql
BEGIN;

-- Step 1: Mark the original as "warning" (closest to superseded in legacy)
UPDATE fsma.cte_events
SET validation_status = 'warning',
    updated_at = NOW()
WHERE id = '<original_event_id>'
  AND tenant_id = '<tenant_id>';

-- Step 2: Insert corrected event as a new row
INSERT INTO fsma.cte_events (
    id, tenant_id, event_type, traceability_lot_code,
    product_description, quantity, unit_of_measure,
    location_gln, location_name, event_timestamp,
    source, source_event_id, idempotency_key,
    sha256_hash, chain_hash, validation_status
)
SELECT
    gen_random_uuid(),
    tenant_id,
    event_type,
    traceability_lot_code,
    product_description,
    quantity,
    unit_of_measure,
    location_gln,
    location_name,
    event_timestamp,
    'data_repair',                         -- source = data_repair for audit trail
    'amends:' || id::text,                 -- source_event_id links back to original
    NULL,                                  -- new idempotency_key (computed below)
    '<recomputed_sha256_hash>',            -- MUST recompute (see Step 3)
    '<new_chain_hash>',                    -- MUST compute by extending chain (see Step 4)
    'valid'
FROM fsma.cte_events
WHERE id = '<original_event_id>'
  AND tenant_id = '<tenant_id>'
RETURNING id AS new_event_id;

-- Step 3: Insert corrected KDEs for the new event
INSERT INTO fsma.cte_kdes (tenant_id, cte_event_id, kde_key, kde_value, is_required)
SELECT tenant_id, '<new_event_id>', kde_key, kde_value, is_required
FROM fsma.cte_kdes
WHERE cte_event_id = '<original_event_id>'
  AND tenant_id = '<tenant_id>';

-- Step 3b: Add/update the KDE that needed fixing
INSERT INTO fsma.cte_kdes (tenant_id, cte_event_id, kde_key, kde_value, is_required)
VALUES ('<tenant_id>', '<new_event_id>', 'ship_date', '2026-03-15', true)
ON CONFLICT (cte_event_id, kde_key) DO UPDATE SET kde_value = EXCLUDED.kde_value;

-- Step 4: Extend the hash chain (the new event gets a NEW chain entry)
-- This MUST be done via the application to compute hashes correctly.
-- See Section 5 for the Python-based approach.

COMMIT;
```

> **Important:** Steps 3-4 involve hash computation. For legacy events, always use the application code (`CTEPersistence.store_event()`) rather than raw SQL for the hash chain extension. Raw SQL can get the hash formula wrong.

### 4.3 Batch Amendment via Python Script

For repairing more than 10 events, use the application layer to handle hashing correctly:

```python
"""
Bulk data repair script.

Usage:
    python -m scripts.bulk_repair \
        --tenant-id <uuid> \
        --filter "event_type = 'shipping' AND ingested_at > '2026-03-01'" \
        --fix-type add_kde \
        --kde-key ship_date \
        --kde-value 2026-03-15 \
        --reason "Missing ship_date from CSV batch import on 2026-03-01" \
        --dry-run
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from shared.cte_persistence import CTEPersistence, compute_event_hash, compute_chain_hash
from shared.database import SessionLocal

logger = logging.getLogger("bulk_repair")


def repair_batch(
    tenant_id: str,
    affected_event_ids: list[str],
    build_corrected_event: callable,  # (original_event_dict) -> corrected_event_dict
    reason: str,
    operator: str,
    dry_run: bool = True,
) -> dict:
    """
    Amend a batch of events using the amendment chain pattern.

    For each affected event:
    1. Mark original as validation_status='warning' (legacy) or status='superseded' (canonical)
    2. Insert a corrected copy with new hashes
    3. Extend the hash chain for the corrected event
    4. Copy and fix KDEs

    Returns summary of actions taken.
    """
    session = SessionLocal()
    persistence = CTEPersistence(session)
    results = {"amended": 0, "skipped": 0, "errors": [], "dry_run": dry_run}

    try:
        for event_id in affected_event_ids:
            try:
                # Fetch original event with KDEs
                original = _fetch_event_with_kdes(session, tenant_id, event_id)
                if not original:
                    results["skipped"] += 1
                    logger.warning("event_not_found", event_id=event_id)
                    continue

                # Build the corrected version
                corrected = build_corrected_event(original)

                if dry_run:
                    logger.info("dry_run_would_amend", event_id=event_id,
                                tlc=original["traceability_lot_code"])
                    results["amended"] += 1
                    continue

                # Store the corrected event (CTEPersistence handles hashing + chain)
                store_result = persistence.store_event(
                    tenant_id=tenant_id,
                    event_type=corrected["event_type"],
                    traceability_lot_code=corrected["traceability_lot_code"],
                    product_description=corrected["product_description"],
                    quantity=corrected["quantity"],
                    unit_of_measure=corrected["unit_of_measure"],
                    location_gln=corrected.get("location_gln"),
                    location_name=corrected.get("location_name"),
                    event_timestamp=corrected["event_timestamp"],
                    source="data_repair",
                    source_event_id=f"amends:{event_id}",
                    kdes=corrected.get("kdes", {}),
                )

                if store_result.success and not store_result.idempotent:
                    # Mark original as warning/superseded
                    _mark_superseded(session, tenant_id, event_id)
                    results["amended"] += 1
                    logger.info("event_amended",
                                original_id=event_id,
                                new_id=store_result.event_id,
                                tlc=corrected["traceability_lot_code"])
                elif store_result.idempotent:
                    results["skipped"] += 1
                    logger.info("event_idempotent_skip", event_id=event_id)
                else:
                    results["errors"].append({
                        "event_id": event_id,
                        "errors": store_result.errors,
                    })

            except Exception as e:
                results["errors"].append({"event_id": event_id, "error": str(e)})
                logger.error("repair_failed", event_id=event_id, error=str(e))

        if not dry_run:
            session.commit()
            logger.info("bulk_repair_committed", **results)
        else:
            session.rollback()
            logger.info("bulk_repair_dry_run_complete", **results)

    except Exception as e:
        session.rollback()
        logger.error("bulk_repair_aborted", error=str(e))
        raise
    finally:
        session.close()

    return results


def _fetch_event_with_kdes(session, tenant_id: str, event_id: str) -> dict | None:
    """Fetch a legacy event with its KDEs merged into a dict."""
    from sqlalchemy import text

    row = session.execute(
        text("""
            SELECT id, tenant_id, event_type, traceability_lot_code,
                   product_description, quantity, unit_of_measure,
                   location_gln, location_name, event_timestamp,
                   source, sha256_hash, chain_hash, validation_status
            FROM fsma.cte_events
            WHERE id = :id AND tenant_id = :tid
        """),
        {"id": event_id, "tid": tenant_id},
    ).fetchone()

    if not row:
        return None

    event = dict(zip([
        "id", "tenant_id", "event_type", "traceability_lot_code",
        "product_description", "quantity", "unit_of_measure",
        "location_gln", "location_name", "event_timestamp",
        "source", "sha256_hash", "chain_hash", "validation_status",
    ], row))

    # Fetch KDEs
    kde_rows = session.execute(
        text("""
            SELECT kde_key, kde_value
            FROM fsma.cte_kdes
            WHERE cte_event_id = :eid AND tenant_id = :tid
        """),
        {"eid": event_id, "tid": tenant_id},
    ).fetchall()

    event["kdes"] = {r[0]: r[1] for r in kde_rows}
    return event


def _mark_superseded(session, tenant_id: str, event_id: str):
    """Mark a legacy event as superseded (validation_status = 'warning')."""
    from sqlalchemy import text

    session.execute(
        text("""
            UPDATE fsma.cte_events
            SET validation_status = 'warning', updated_at = NOW()
            WHERE id = :id AND tenant_id = :tid
        """),
        {"id": event_id, "tid": tenant_id},
    )
```

### 4.4 Constructing the Corrected Event: Common Fix Patterns

**Add a missing KDE:**
```python
def fix_missing_ship_date(original: dict) -> dict:
    corrected = {**original}
    corrected["kdes"] = {**original.get("kdes", {}), "ship_date": "2026-03-15"}
    return corrected
```

**Fix a wrong quantity:**
```python
def fix_quantity(original: dict) -> dict:
    corrected = {**original}
    corrected["quantity"] = 500.0  # was incorrectly 50.0
    corrected["unit_of_measure"] = "LB"
    return corrected
```

**Fix a wrong event type:**
```python
def fix_event_type(original: dict) -> dict:
    corrected = {**original}
    corrected["event_type"] = "receiving"  # was incorrectly "shipping"
    return corrected
```

**Fix a wrong location:**
```python
def fix_location(original: dict) -> dict:
    corrected = {**original}
    corrected["location_gln"] = "0012345000015"
    corrected["location_name"] = "Warehouse B"
    return corrected
```

---

## 5. Phase 4: Execute the Repair

### 5.1 Pre-Repair Checklist

- [ ] Blast radius assessed (Section 3)
- [ ] Repair strategy chosen (single, batch, or scripted)
- [ ] Amendment records constructed and reviewed
- [ ] Dry run completed successfully (for batch repairs)
- [ ] Database backup taken or Supabase point-in-time recovery window confirmed
- [ ] RLS context verified (Section 9)
- [ ] If during an active recall: compliance officer notified

### 5.2 Execution Order

**Always execute in this order:**

1. **Take a snapshot** of the affected events (for rollback evidence):
```sql
CREATE TEMP TABLE repair_snapshot AS
SELECT * FROM fsma.cte_events
WHERE id IN (<affected_event_ids>)
  AND tenant_id = '<tenant_id>';
-- Also snapshot KDEs
CREATE TEMP TABLE repair_snapshot_kdes AS
SELECT * FROM fsma.cte_kdes
WHERE cte_event_id IN (<affected_event_ids>)
  AND tenant_id = '<tenant_id>';
```

2. **Insert corrected events** (new rows with `source = 'data_repair'`)

3. **Extend the hash chain** for each new event (via `CTEPersistence.store_event()`)

4. **Mark originals as superseded** (after new events are committed)

5. **Invalidate stale rule evaluations** on the original events:
```sql
-- Mark evaluations on superseded events so check_blocking_defects() flags them
UPDATE fsma.rule_evaluations
SET evaluated_at = '1970-01-01'::timestamptz
WHERE tenant_id = '<tenant_id>'
  AND event_id = ANY(ARRAY[<original_event_ids>]::text[]);
```

6. **Verify** (Section 6)

### 5.3 Transaction Safety

For small repairs (< 50 events), wrap everything in a single transaction:

```sql
BEGIN;
-- all amendments here
-- VERIFY counts before committing
SELECT count(*) FROM fsma.cte_events
WHERE source = 'data_repair' AND tenant_id = '<tenant_id>'
  AND ingested_at > NOW() - interval '5 minutes';
-- Should match expected amendment count
COMMIT;
```

For large repairs (50+ events), use the Python script with batch commits:

```python
# Commit every 100 events to avoid holding long transactions
BATCH_SIZE = 100
for i in range(0, len(affected_ids), BATCH_SIZE):
    batch = affected_ids[i:i + BATCH_SIZE]
    result = repair_batch(
        tenant_id=tenant_id,
        affected_event_ids=batch,
        build_corrected_event=fix_function,
        reason=reason,
        operator=operator,
        dry_run=False,
    )
    logger.info(f"Batch {i // BATCH_SIZE + 1} complete: {result}")
```

---

## 6. Phase 5: Verify Hash Chain Integrity After Repair

After every repair, verify the chain is intact. New amendment events extend the chain — they don't modify it.

### 6.1 Full Chain Verification (Application)

```python
from shared.cte_persistence import CTEPersistence
from shared.database import SessionLocal

session = SessionLocal()
persistence = CTEPersistence(session)
result = persistence.verify_chain(tenant_id="<tenant_id>")

assert result.valid, f"Chain broken after repair: {result.errors}"
print(f"Chain valid. Length: {result.chain_length}. Checked at: {result.checked_at}")
session.close()
```

### 6.2 Full Chain Verification (SQL)

```sql
-- Check 1: No sequence gaps
WITH ordered AS (
    SELECT sequence_num,
           LAG(sequence_num) OVER (ORDER BY sequence_num) AS prev_seq
    FROM fsma.hash_chain
    WHERE tenant_id = '<tenant_id>'
)
SELECT sequence_num, prev_seq
FROM ordered
WHERE prev_seq IS NOT NULL AND sequence_num != prev_seq + 1;
-- MUST return 0 rows

-- Check 2: Previous chain hash linkage is consistent
WITH ordered AS (
    SELECT sequence_num, chain_hash, previous_chain_hash,
           LAG(chain_hash) OVER (ORDER BY sequence_num) AS expected_prev
    FROM fsma.hash_chain
    WHERE tenant_id = '<tenant_id>'
)
SELECT sequence_num,
       left(previous_chain_hash, 16) AS stored_prev,
       left(expected_prev, 16) AS expected_prev
FROM ordered
WHERE expected_prev IS NOT NULL AND previous_chain_hash != expected_prev;
-- MUST return 0 rows

-- Check 3: Genesis entry has NULL previous hash
SELECT sequence_num, previous_chain_hash
FROM fsma.hash_chain
WHERE tenant_id = '<tenant_id>'
ORDER BY sequence_num ASC
LIMIT 1;
-- previous_chain_hash MUST be NULL

-- Check 4: New amendment events have chain entries
SELECT e.id AS event_id, e.traceability_lot_code,
       h.sequence_num, h.chain_hash
FROM fsma.cte_events e
LEFT JOIN fsma.hash_chain h ON h.cte_event_id = e.id AND h.tenant_id = e.tenant_id
WHERE e.tenant_id = '<tenant_id>'
  AND e.source = 'data_repair'
  AND e.ingested_at > NOW() - interval '1 hour';
-- Every repair event MUST have a chain entry (h.sequence_num IS NOT NULL)

-- Check 5: Chain grew by exactly the number of amendments
SELECT max(sequence_num) AS chain_head
FROM fsma.hash_chain
WHERE tenant_id = '<tenant_id>';
-- Should be previous_chain_head + number_of_amendments
```

### 6.3 Verify Amendment Linkage

```sql
-- For canonical system: verify supersedes chain is intact
SELECT e.event_id, e.status, e.supersedes_event_id,
       orig.event_id AS original_id, orig.status AS original_status
FROM fsma.traceability_events e
JOIN fsma.traceability_events orig ON e.supersedes_event_id = orig.event_id
WHERE e.tenant_id = '<tenant_id>'
  AND e.created_at > NOW() - interval '1 hour';
-- Every amendment should point to a 'superseded' original

-- For legacy system: verify source_event_id linkage
SELECT e.id, e.source_event_id, e.validation_status,
       orig.id AS original_id, orig.validation_status AS original_status
FROM fsma.cte_events e
JOIN fsma.cte_events orig ON e.source_event_id = 'amends:' || orig.id::text
WHERE e.tenant_id = '<tenant_id>'
  AND e.source = 'data_repair'
  AND e.ingested_at > NOW() - interval '1 hour';
-- Every amendment should link to a 'warning' original
```

### 6.4 Verify FDA Export Still Works

```bash
# Re-run export for affected TLCs and check headers
curl -G "https://<railway-url>/api/v1/fda/export" \
  --data-urlencode "tlc=<affected_tlc>" \
  --data-urlencode "tenant_id=<tenant_id>" \
  --data-urlencode "format=csv" \
  -H "Authorization: Bearer <token>" \
  -o post_repair_export.csv -D headers.txt

# Check chain integrity header
grep "X-Chain-Integrity" headers.txt
# MUST say: X-Chain-Integrity: VERIFIED
```

---

## 7. Phase 6: Re-run Compliance Evaluation

Amendments invalidate previous rule evaluations. The stale evaluation check in `check_blocking_defects()` (`assembly.py:634-656`) compares `COALESCE(e.amended_at, e.created_at)` against `re.evaluated_at`. New amendment events will have `created_at > evaluated_at` for any existing evaluations.

### 7.1 Check for Stale Evaluations

```sql
-- Events that need re-evaluation after repair
SELECT re.event_id, re.rule_id, re.evaluated_at,
       e.ingested_at AS event_created
FROM fsma.rule_evaluations re
JOIN fsma.cte_events e ON re.event_id = e.id::text AND re.tenant_id = e.tenant_id
WHERE re.tenant_id = '<tenant_id>'
  AND e.source = 'data_repair'
  AND e.ingested_at > re.evaluated_at;
```

### 7.2 Trigger Re-evaluation

The compliance service re-evaluates events on the next scoring run. To force immediate re-evaluation:

```bash
# Re-run compliance scoring for the tenant
curl -X POST "https://<railway-url>/api/v1/compliance/evaluate" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "<tenant_id>"}'
```

### 7.3 Verify Blocking Defects Resolved

If the repair was triggered by a blocking defect on an active request case:

```bash
curl "https://<railway-url>/api/v1/requests/<request_case_id>/blockers" \
  -H "Authorization: Bearer <token>" \
  -H "X-Tenant-Id: <tenant_id>"
```

The `stale_evaluations` blocker type should clear once re-evaluation completes.

---

## 8. Phase 7: Communicate to Affected Tenant

### 8.1 When to Notify

| Situation | Notify? | How |
|-----------|---------|-----|
| Internal data quality fix, no user-visible impact | No | Log in repair audit trail only |
| Fix changes compliance score | Yes | In-app notification + email |
| Fix changes FDA export content | Yes | Email with before/after summary |
| Fix corrects data during an active recall | Yes | Immediate phone/email to compliance contact |
| Fix was triggered by customer-reported issue | Yes | Direct response to the original report |

### 8.2 Notification Template

```
Subject: Data Correction Applied — [TLC(s)] Traceability Records Updated

[Tenant Name],

We identified and corrected an issue affecting [N] traceability records 
for lot code(s) [TLC list].

What happened:
  [Description of the data issue — e.g., "Ship date KDE was missing 
  from 15 Shipping events imported via CSV on March 1, 2026."]

What we did:
  - Created corrected records for all [N] affected events
  - Original records preserved in amendment chain (not deleted)
  - Hash chain integrity verified after correction
  - Compliance scoring re-evaluated

Impact:
  - Your compliance score for [dimension] changed from [X]% to [Y]%
  - [If applicable: FDA export packages generated before this date 
    should be regenerated]

No action is required on your part. The corrected records are already 
reflected in your dashboard and any future FDA exports.

If you have questions, contact [support contact].

— RegEngine Compliance Team
```

### 8.3 Log the Repair for Audit

```sql
-- Record the bulk repair operation in the audit trail
INSERT INTO fsma.fda_export_log (
    tenant_id, export_type, record_count,
    export_hash, generated_by, generated_at
) VALUES (
    '<tenant_id>',
    'data_repair',
    <number_of_amended_events>,
    '<sha256 of the repair summary>',
    'bulk_repair:<operator_email>',
    NOW()
);
```

---

## 9. RLS Implications of Bulk Operations

### 9.1 The Core Problem

Row-Level Security policies filter all queries by `tenant_id`. Bulk repairs that touch a single tenant work fine. But there are traps:

**Trap 1: Superuser bypass.** If you connect as the Supabase `postgres` superuser, RLS is bypassed. Your repair SQL will succeed but won't be subject to the same access controls as the application. This means:
- You could accidentally read/write another tenant's data
- You won't catch RLS-related bugs in your repair SQL

**Trap 2: Cross-tenant repairs.** If the same bug affected multiple tenants (e.g., a bad ingestion mapper), you must repair each tenant separately. Do NOT write a single SQL statement that touches multiple `tenant_id` values.

**Trap 3: `get_tenant_context()` not set.** The RLS policies on `fsma.traceability_events` (V043) use `get_tenant_context()`. If this function isn't set in your session, RLS will block all access.

### 9.2 Safe Repair Session Setup

```sql
-- Option A: Use the application role with tenant context (RECOMMENDED)
SET ROLE regengine;
SELECT set_config('regengine.tenant_id', '<tenant_id>', true);  -- session-local

-- Verify RLS is active
SELECT current_user, current_setting('regengine.tenant_id', true);

-- Now all queries are automatically scoped to this tenant
-- You CANNOT accidentally touch another tenant's data

-- Option B: For V043 tables that use get_tenant_context()
SET ROLE regengine;
-- Set whatever session variable get_tenant_context() reads
-- (check the function definition for your installation)
```

### 9.3 Verify Isolation After Repair

```sql
-- After completing the repair, verify no cross-tenant contamination
SELECT count(*), count(DISTINCT tenant_id) AS tenant_count
FROM fsma.cte_events
WHERE source = 'data_repair'
  AND ingested_at > NOW() - interval '1 hour';
-- tenant_count MUST be 1

-- Check the hash chain wasn't extended for the wrong tenant
SELECT DISTINCT tenant_id
FROM fsma.hash_chain
WHERE created_at > NOW() - interval '1 hour';
-- Should contain only the target tenant_id
```

### 9.4 Multi-Tenant Repair (Same Bug, Multiple Tenants)

```python
# ALWAYS repair one tenant at a time, never in a shared transaction
affected_tenants = ["tenant-uuid-1", "tenant-uuid-2", "tenant-uuid-3"]

for tenant_id in affected_tenants:
    logger.info(f"Starting repair for tenant {tenant_id}")

    # Each tenant gets its own session with correct RLS context
    result = repair_batch(
        tenant_id=tenant_id,
        affected_event_ids=get_affected_ids(tenant_id),
        build_corrected_event=fix_function,
        reason=reason,
        operator=operator,
        dry_run=False,
    )

    # Verify chain for THIS tenant before moving to next
    session = SessionLocal()
    persistence = CTEPersistence(session)
    chain_result = persistence.verify_chain(tenant_id=tenant_id)
    assert chain_result.valid, f"Chain broken for tenant {tenant_id}: {chain_result.errors}"
    session.close()

    logger.info(f"Tenant {tenant_id} repair complete: {result}")
```

---

## 10. Common Repair Scenarios

### Scenario A: CSV Import Had Wrong Column Mapping

**Symptom:** 200 events have `product_description` and `location_name` swapped.

```python
def fix_swapped_columns(original: dict) -> dict:
    corrected = {**original}
    corrected["product_description"] = original["location_name"]
    corrected["location_name"] = original["product_description"]
    return corrected
```

**Identify:**
```sql
SELECT id, product_description, location_name
FROM fsma.cte_events
WHERE tenant_id = '<tenant_id>'
  AND source = 'csv_upload'
  AND ingested_at BETWEEN '2026-03-01' AND '2026-03-02';
```

### Scenario B: Duplicate Events From Retry Storm

**Symptom:** The same physical event has 3 rows because the webhook retried.

**Repair:** Keep the earliest (most accurate `ingested_at`), supersede the duplicates.

```sql
-- Find duplicates
WITH ranked AS (
    SELECT id, traceability_lot_code, event_type, event_timestamp,
           ROW_NUMBER() OVER (
               PARTITION BY traceability_lot_code, event_type, event_timestamp
               ORDER BY ingested_at ASC
           ) AS rn
    FROM fsma.cte_events
    WHERE tenant_id = '<tenant_id>'
)
SELECT id, traceability_lot_code, event_type, rn
FROM ranked
WHERE rn > 1;  -- these are the duplicates to supersede
```

Then mark duplicates (rn > 1) as `validation_status = 'warning'` and record in the repair log. Do NOT delete them.

### Scenario C: Wrong Tenant ID on Events

**Symptom:** Events were ingested with the wrong `tenant_id` due to a misconfigured API key.

**This is the hardest repair.** You cannot UPDATE `tenant_id` because:
- The hash chain is per-tenant — moving an event breaks both chains
- RLS policies would hide the events from the correct tenant

**Repair approach:**
1. In the WRONG tenant's context: mark the events as `validation_status = 'warning'`
2. In the CORRECT tenant's context: re-ingest the events from the raw source
3. The wrong-tenant events remain in the chain (they can't be removed) but are marked as invalid
4. Document the orphaned chain entries in the repair log

### Scenario D: Compliance Rule Change Requires KDE Backfill

**Symptom:** A new FSMA rule requires `growing_area_name` on all Harvesting events. Existing events don't have it.

```sql
-- Find events needing the backfill
SELECT e.id, e.traceability_lot_code, e.event_timestamp
FROM fsma.cte_events e
WHERE e.tenant_id = '<tenant_id>'
  AND e.event_type = 'harvesting'
  AND NOT EXISTS (
      SELECT 1 FROM fsma.cte_kdes k
      WHERE k.cte_event_id = e.id AND k.kde_key = 'growing_area_name'
  );
```

```python
def add_growing_area(original: dict) -> dict:
    corrected = {**original}
    # Look up the growing area from facility reference data
    growing_area = lookup_growing_area(original["location_gln"])
    corrected["kdes"] = {**original.get("kdes", {}), "growing_area_name": growing_area}
    return corrected
```

---

## 11. What to NEVER Do

| Action | Why It's Forbidden | What to Do Instead |
|--------|-------------------|-------------------|
| `DELETE FROM fsma.cte_events` | Breaks every hash chain entry that references the deleted event | Supersede via amendment chain |
| `DELETE FROM fsma.hash_chain` | Breaks chain continuity; all subsequent chain_hashes become invalid | Chain is append-only; leave it |
| `UPDATE fsma.cte_events SET sha256_hash = ...` | The hash is computed from the event content; changing it without changing content creates a mismatch | Insert a new corrected event |
| `UPDATE fsma.cte_events SET chain_hash = ...` | The chain_hash depends on the previous entry; modifying it breaks the chain forward | Extend the chain with a new entry |
| `UPDATE fsma.hash_chain SET chain_hash = ...` | Invalidates every subsequent chain entry | Never modify chain entries |
| `UPDATE fsma.cte_events SET tenant_id = ...` | Hash chain is per-tenant; RLS policies depend on tenant_id | Re-ingest in correct tenant, mark originals as invalid |
| Repair multiple tenants in one transaction | If the transaction fails partway, one tenant is repaired and another isn't | One transaction per tenant |
| Skip the dry run for batch repairs | You can't undo a committed repair without another repair | Always `--dry-run` first |
| Repair during active FDA export | Export may read a mix of original and amended events | Pause exports, repair, verify, resume |

---

## 12. Reference

### Key Files

| File | Role in Repair |
|------|---------------|
| `services/shared/cte_persistence.py` | `store_event()` for hash-safe event insertion, `verify_chain()` for post-repair validation |
| `services/shared/canonical_event.py` | `TraceabilityEvent` model with `supersedes_event_id`, `EventStatus.SUPERSEDED` |
| `services/shared/request_workflow/assembly.py` | `check_blocking_defects()` — stale evaluation detection at line 634 |
| `migrations/V002__fsma_cte_persistence.sql` | Legacy table schema (`cte_events`, `cte_kdes`, `hash_chain`) |
| `migrations/V043__canonical_traceability_events.sql` | Canonical table schema (`traceability_events` with amendment chain) |
| `migrations/V052__cte_events_composite_idempotency_key.sql` | Composite idempotency constraint `(tenant_id, idempotency_key)` |

### Hash Formulas

```
event_hash = SHA-256(event_id | event_type | tlc | product | qty | uom | gln | location | timestamp | json(kdes))
             Implemented: compute_event_hash() in cte_persistence.py

chain_hash = SHA-256(previous_chain_hash | event_hash)
             Genesis: SHA-256('GENESIS' | event_hash)
             Implemented: compute_chain_hash() in cte_persistence.py:142-149

idempotency_key = SHA-256(json({event_type, tlc, timestamp, source, from_facility, to_facility, kdes}))
                  Implemented: compute_idempotency_key() in cte_persistence.py
```

### Tables Involved in Repairs

| Table | Append-Only? | Can UPDATE? | Can DELETE? |
|-------|-------------|-------------|-------------|
| `fsma.cte_events` | No (but treat as such) | Only `validation_status`, `updated_at` | **NEVER** |
| `fsma.cte_kdes` | No | Only `kde_value` on corrected events | **NEVER** on originals |
| `fsma.hash_chain` | **YES** | **NEVER** | **NEVER** |
| `fsma.traceability_events` | No (but treat as such) | Only `status`, `amended_at` | **NEVER** |
| `fsma.rule_evaluations` | No | `evaluated_at` to invalidate | OK (re-evaluation creates new) |
| `fsma.fda_export_log` | Yes (audit trail) | **NEVER** | **NEVER** |

### Related Runbooks

- [FDA_RECALL_RESPONSE.md](FDA_RECALL_RESPONSE.md) — Section 8 covers data integrity failures during recalls
- [incident-response.md](incident-response.md) — Escalation paths for SEV1/SEV2
- [disaster-recovery.md](disaster-recovery.md) — Database backup and point-in-time recovery
