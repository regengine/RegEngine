# Neo4j Cross-Tenant MERGE Vulnerability — Migration Plan

Epic: #1643 — Neo4j tenant-isolation impl
Target file: `services/graph/app/neo4j_utils.py`
Status: **REVISED 2026-05-12 — migration moot, recommend deletion**
Source audit: `project_session_2026_05_11.md` finding #1

## Inventory result (2026-05-12, prod Neo4j)

- `Document`, `Provision`, `Threshold` labels do not exist in prod
- 0 nodes, 0 cross-tenant collisions across all 5 collision classes
- Only labels present: `BuyerTenant`, `CTE`, `FTLCategory`, `Facility`, `Location`, `Lot`, `Organization`, `PendingSupplierInvite`, `Product`, `SupplierContact`, `SupplierFacility`, `Tenant` — all written by the safe `fsma_nodes.py` composite-key path
- Legacy `consumer.py` (which calls `upsert_from_entities` → vulnerable MERGE) has no callers in `main.py`, no separate Railway process, and no ingest history

**Implication:** the vulnerable MERGE is dead code. No data, no consumer, no exploit surface.

**Revised recommendation:** delete the legacy MERGE path rather than migrate it. Specifically:
- `services/graph/app/neo4j_utils.py` — remove `CYPHER_UPSERT`, `CYPHER_UPSERT_PROVISION`, `upsert_from_entities`, and the legacy `_run_legacy_upsert` call site in `consumer.py:535`
- `services/graph/app/consumer.py` — keep `Neo4jClient` import (still used as the shared driver) but delete the `upsert_from_entities` call path
- Constraint scripts: leave alone if they create constraints for shared labels still in use; remove any that target Document/Provision/Threshold
- ADR-003 (Threshold collapse, PR #2329) becomes informational only — closes naturally with the deletion

If the legacy path may be revived later, fall back to Steps 2-5 below as written (now ~14h since Step 3 is skipped).

---

## Original migration plan (retained for reference if legacy path is revived)


## 1. Decision matrix

| # | Line | Node | Current key | Tenant scope | New MERGE key | Rationale |
|---|------|------|-------------|--------------|---------------|-----------|
| 1 | 184 | Document | `{id}` | tenant-owned | `{id, tenant_id}` | Two tenants may ingest the same `doc_id` (e.g. "21-CFR-117"); each gets its own copy. Matches `fsma_nodes.py:500` precedent. |
| 2 | 194 | Provision | `{pid}` | tenant-owned | `{pid, tenant_id}` | `pid = doc_id:start:end` collides whenever doc_id collides. Drop `ON MATCH SET p.tenant_id` (the clobber). |
| 3 | 203 | Threshold | `{pid}` | tenant-owned | **collapse into Provision properties** | ADR-003 (PR #2329): zero readers of `:Threshold` or `HAS_THRESHOLD` in repo. Promote `threshold_value` / `threshold_unit` / `threshold_unit_normalized` onto `:Provision`; delete the label. |
| 4 | 217 | Document (hash variant) | `{hash}` | tenant-owned | `{hash, tenant_id}` | Same hash from same source PDF will collide across tenants. |
| 5 | 220 | Provision (hash variant) | `{hash}` | tenant-owned | `{hash, tenant_id}` | Same content_hash across tenants is exactly the cross-tenant leak. Drop `ON MATCH SET ... tenant_id`. |
| 6 | 243 | Jurisdiction | `{code}` | **shared, keep** | unchanged | Reference data (US-CA, EU, etc.). Already shared by design and protected by `jurisdiction_code_unique`. The `(p)-[:APPLIES_TO]->(j)` edge is fine — `p` is tenant-scoped, `j` is global, the edge is just a pointer. No tenant payload flows through Jurisdiction. |

Ripple effects:
- `Concept` (line 193) — `{name}` unique. Shared reference data; keep global.
- `Provenance` (line 209) — `{doc_id, start, end}`. Tenant-scoped via doc_id once Document is composite-keyed; key becomes `{doc_id, start, end, tenant_id}`.

## 2. Migration steps (execution order)

### Step 0 — Inventory & data assessment (read-only)
- What: Run the Cypher in §3 against each environment to count collisions.
- Files: none (ops runbook only).
- Independent: yes.
- Rollback: n/a.
- Risk: low.
- Effort: 1h.

### Step 1 — Decide Threshold disposition
- What: Grep consumers of `:Threshold` to pick (a) collapse into Provision properties or (b) composite key. Document as ADR.
- Files: `docs/adr/00XX-threshold-node-disposition.md`.
- Independent: yes.
- Rollback: revert ADR.
- Risk: low.
- Effort: 2h.

### Step 2 — Add composite indexes & constraints (additive, non-breaking)
- What: New Cypher migration adding:
  - `CREATE CONSTRAINT document_id_tenant_unique FOR (d:Document) REQUIRE (d.id, d.tenant_id) IS UNIQUE`
  - `CREATE CONSTRAINT document_hash_tenant_unique FOR (d:Document) REQUIRE (d.hash, d.tenant_id) IS UNIQUE`
  - `CREATE CONSTRAINT provision_pid_tenant_unique FOR (p:Provision) REQUIRE (p.pid, p.tenant_id) IS UNIQUE`
  - `CREATE CONSTRAINT provision_hash_tenant_unique FOR (p:Provision) REQUIRE (p.hash, p.tenant_id) IS UNIQUE`
  - (No Threshold constraint — collapsed per ADR-003.)
- These will FAIL if collisions exist — Step 0 must show zero, or Step 3 must precede.
- Files: `services/graph/scripts/migrations/2026XXXX_composite_tenant_constraints.cypher`, `services/graph/scripts/apply_constraints.py`.
- Independent: ships alone; safe additive change.
- Rollback: `DROP CONSTRAINT <name> IF EXISTS`.
- Risk: med (constraint creation fails loudly on dirty data; that's a feature).
- Effort: 3h.

### Step 3 — Backfill/split collided nodes (only if Step 0 found collisions)
- What: One-off script that copies-out a tenant-owned twin for each collided Document/Provision and re-points relationships (`IN_DOCUMENT`, `APPLIES_TO`, `HAS_THRESHOLD`, `PROVENANCE`, `MENTIONS`). Single transaction per (label, key, tenant) tuple.
- Files: `services/graph/scripts/migrations/2026XXXX_split_cross_tenant_collisions.py`.
- Must batch with: Step 2 in same release window.
- Rollback: pre-flight `CALL apoc.export.cypher.all(...)` of affected subgraph; rollback = restore export.
- Risk: HIGH if collisions are non-trivial. LOW if collision count is 0.
- Effort: 4–24h depending on Step 0.

### Step 4 — Update MERGE statements + collapse Threshold
- What: Rewrite `CYPHER_UPSERT` and `CYPHER_UPSERT_PROVISION` so every tenant-owned MERGE includes `tenant_id` in the key map, set `tenant_id` only `ON CREATE` (never `ON MATCH`), and require `tenant_id` parameter to be non-null (raise in Python before calling Cypher). Replace the `MERGE (:Threshold)` block with a `SET p.threshold_value = ..., p.threshold_unit = ..., p.threshold_unit_normalized = ...` on the Provision node, then a one-pass `MATCH (p:Provision)-[r:HAS_THRESHOLD]->(t:Threshold) SET p.threshold_value=t.value, ... DETACH DELETE t` migration to clear existing Threshold nodes.
- Files: `services/graph/app/neo4j_utils.py` (lines 184–245), `services/graph/app/consumer.py` (validation).
- Must batch with: Steps 2 and 3 (deploy together).
- Rollback: revert commit; constraints from Step 2 remain in place but old MERGE will fail on uniqueness — rollback PR must also drop the new constraints.
- Risk: med.
- Effort: 4h.

### Step 5 — Drop legacy single-property constraints
- What: After Step 4 has run in prod for ≥48h without ingest errors:
  - `DROP CONSTRAINT document_id_unique`
  - `DROP CONSTRAINT document_hash_unique`
- Files: `services/graph/scripts/migrations/2026XXXX_drop_legacy_doc_constraints.cypher`.
- Independent: yes (separate release after soak).
- Rollback: re-create constraints — but this will fail if multi-tenant docs now exist. Forward-only.
- Risk: low operationally; point-of-no-return.
- Effort: 1h.

### Step 6 — Hardening tests
- See §4.
- Effort: 6h.

**Total estimated effort: 21–41h depending on Step 3.**

## 3. Data assessment Cypher (read-only)

Run against each Neo4j database before Step 2.

```cypher
// Documents colliding across tenants (by id)
MATCH (d:Document)
WHERE d.tenant_id IS NOT NULL
WITH d.id AS doc_id, collect(DISTINCT d.tenant_id) AS tenants, count(*) AS n
WHERE size(tenants) > 1
RETURN 'Document.id' AS kind, doc_id AS key, tenants, n
UNION ALL
MATCH (d:Document)
WHERE d.hash IS NOT NULL AND d.tenant_id IS NOT NULL
WITH d.hash AS h, collect(DISTINCT d.tenant_id) AS tenants, count(*) AS n
WHERE size(tenants) > 1
RETURN 'Document.hash' AS kind, h AS key, tenants, n
UNION ALL
MATCH (p:Provision)
WHERE p.tenant_id IS NOT NULL
WITH p.pid AS pid, collect(DISTINCT p.tenant_id) AS tenants, count(*) AS n
WHERE size(tenants) > 1
RETURN 'Provision.pid' AS kind, pid AS key, tenants, n
UNION ALL
MATCH (p:Provision)
WHERE p.hash IS NOT NULL AND p.tenant_id IS NOT NULL
WITH p.hash AS h, collect(DISTINCT p.tenant_id) AS tenants, count(*) AS n
WHERE size(tenants) > 1
RETURN 'Provision.hash' AS kind, h AS key, tenants, n;
```

Because `document_id_unique` is currently enforced globally, the above can return >1 tenant only via the property-isolation path (multi-DB Enterprise) — not from single-DB Community, which would have errored on the second tenant's insert. Audit both modes. Cross-reference with API audit log for prior-owner detection on clobbered nodes.

## 4. Test strategy

New tests under `services/graph/tests/`:
- `test_neo4j_utils_tenant_merge_isolation.py`:
  - Two tenants upsert same `doc_id` → two distinct Document nodes, each with its own `tenant_id`.
  - Two tenants upsert same `doc_hash` / `provision_hash` → no cross-tenant overwrite.
  - Upsert with `tenant_id=None` raises before touching Neo4j.
  - `ON MATCH` on a tenant's own provision updates text but leaves `tenant_id` unchanged.
- `test_neo4j_constraints_composite.py`: testcontainers integration verifying composite UNIQUE constraints exist and legacy ones are absent post-migration.
- `test_jurisdiction_remains_shared.py`: two tenants reference same jurisdiction code → single Jurisdiction node, two APPLIES_TO edges from distinct tenant-owned Provisions.

Updates:
- `test_consumer.py::test_calls_upsert_from_entities` — pass tenant_id, assert MERGE params include it.
- `test_neo4j_client_database_scoping.py` — confirm property-based isolation on Community, DB-level on Enterprise.
- `test_fsma_relationships_tenant_scope.py`, `test_trace_path_tenant_scope.py` — verify pass with new composite keys.

## 5. Rollout plan

Single Kafka consumer group, no per-request flag — all-or-nothing per deploy. Release sequence IS the safety mechanism.

1. **R1 (additive):** Step 2 — composite constraints added. Old code keeps working; new constraints are additive.
2. **R2 (data fix, conditional):** Step 3 — only if Step 0 found collisions. Run during ingest pause: stop consumer, run script, validate, resume. Communicate to tenants whose data is split.
3. **R3 (code swap):** Step 4 — `neo4j_utils.py` rewrite. Deploy during low-ingest window. Monitor `MESSAGES_COUNTER{status="success"}` vs DLQ rate; auto-rollback if DLQ > 1% for 5min.
4. **R4 (cleanup, ≥48h soak):** Step 5 — drop legacy constraints. Forward-only.

Operational notes:
- Pause Kafka consumer (`graph-update` topic) before R2 and R3 to avoid mid-migration partial reads.
- DLQ topic (`_send_to_dlq` in consumer.py) is the safety net for payloads failing the new `tenant_id` requirement.
- Per-message rollback unavailable; rollback = revert deploy + drop new constraints.

## 6. Out of scope

- Variable-length trace paths (graph-security audit, separate epic).
- Neo4jClient database-override bug (#1229).
- `Concept` and `Jurisdiction` design (intentionally shared global reference data).
- `Framework` / `Control` nodes (global by design).
- FSMA MERGE statements in `models/fsma_nodes.py` (already composite-keyed).
- `hierarchy_builder.py` / `overlay_writer.py` Jurisdiction MERGEs (global reference).
- Backfilling tenant_id on pre-tenant-id historical nodes (separate data-migration epic).
- Read-side tenant predicate audit (different PR; required before declaring vulnerability closed).

## Critical files for implementation

- `/Users/sellers/RegEngine/repo/services/graph/app/neo4j_utils.py`
- `/Users/sellers/RegEngine/repo/services/graph/scripts/init_regulatory_schema.cypher`
- `/Users/sellers/RegEngine/repo/services/graph/scripts/apply_constraints.py`
- `/Users/sellers/RegEngine/repo/services/graph/app/consumer.py`
- `/Users/sellers/RegEngine/repo/services/graph/app/models/fsma_nodes.py` (reference for correct pattern)
