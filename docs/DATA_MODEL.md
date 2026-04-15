# RegEngine Data Model

Technical reference for the canonical data structures in RegEngine's FSMA 204
compliance system. Everything lives in the `fsma` PostgreSQL schema. All tables
enforce row-level security via `tenant_id` and `get_tenant_context()`.

---

## 1. Canonical Event

A **traceability event** is a single Critical Tracking Event (CTE) as defined by
FSMA 204 (21 CFR 1.1325-1.1350): harvesting, cooling, initial packing,
first land-based receiving, shipping, receiving, or transformation.

**Raw vs. canonical:** Every event preserves two payloads side by side.
`raw_payload` is the verbatim source record (CSV row, EPCIS XML, webhook JSON)
that never changes after ingestion. `normalized_payload` is the canonical form
produced by the mapper, which downstream services consume exclusively.

Key fields on `fsma.traceability_events`:

| Field | Purpose |
|---|---|
| `event_id` (PK) | UUID, system-assigned |
| `event_type` | One of 7 CTE types (harvesting, cooling, initial_packing, first_land_based_receiving, shipping, receiving, transformation) |
| `traceability_lot_code` | The TLC -- the primary key of the supply chain |
| `quantity` / `unit_of_measure` | What and how much |
| `from_entity_reference` / `to_entity_reference` | Shipper/receiver firm (resolved to canonical IDs via identity layer) |
| `from_facility_reference` / `to_facility_reference` | Ship-from/ship-to location (GLN, name, or internal ID) |
| `kdes` | Structured JSONB key data elements (replaces legacy key-value `cte_kdes` table) |
| `raw_payload` / `normalized_payload` | Dual payloads: verbatim source + canonical form |
| `provenance_metadata` | Source file hash, mapper name/version, normalization rules applied, extraction confidence |
| `confidence_score` | 0.0-1.0 normalization confidence (1.0 = exact mapping) |
| `supersedes_event_id` | FK to the event this record amends (explicit amendment chain) |
| `sha256_hash` / `chain_hash` | Integrity fields linking to the hash chain |
| `idempotency_key` | SHA-256 dedup key preventing double-ingestion |
| `schema_version` | Version of the canonical schema used to normalize |
| `status` | active, superseded, rejected, draft |

Every event enters through an **ingestion run** (`fsma.ingestion_runs`), which
is the batch receipt -- one per file upload, API call, or EPCIS document. It
tracks record/accepted/rejected counts, mapper version, and processing status.

**Evidence attachments** (`fsma.evidence_attachments`) link source documents
(BOLs, invoices, lab reports, photos) to canonical events for the evidentiary
chain. Each attachment carries its own SHA-256 hash and storage URI.

---

## 2. Entity Model

All supply-chain participants live in `fsma.canonical_entities` with a
`entity_type` discriminator:

| Entity Type | What It Represents | Key Identifiers |
|---|---|---|
| `firm` | Company / trading partner | `canonical_name`, `fda_registration`, DUNS (via alias) |
| `facility` | Physical location | `gln` (GS1 GLN), `fda_registration`, address fields |
| `product` | Product / commodity | `gtin` (GS1 GTIN), `canonical_name` |
| `lot` | Lot / batch | `canonical_name` (TLC), `internal_id` |
| `trading_relationship` | Buyer-seller link | `canonical_name` |

Each entity has a `verification_status` (verified / unverified / pending_review)
and a `confidence_score`. Entities marked `is_active = false` are soft-deleted.

Traceability events reference entities through free-text fields
(`from_entity_reference`, `to_entity_reference`, `from_facility_reference`,
`to_facility_reference`) which are resolved to canonical entity IDs by the
identity resolution layer.

---

## 3. Identity Resolution

The identity layer resolves the "same entity, many names" problem. A single
cold storage facility might appear as "ABC Cold Storage", "ABC Cold Storage LLC",
"A.B.C. Cold", and GLN `0012345000015` across different suppliers' records.

**Three tables, one flow:**

1. **`fsma.canonical_entities`** -- the master record with one canonical name
   and optional standard identifiers (GLN, GTIN, FDA registration).

2. **`fsma.entity_aliases`** -- every alternate identifier maps back to a
   canonical entity. Alias types: `name`, `gln`, `gtin`, `fda_registration`,
   `internal_code`, `duns`, `tlc_prefix`, `address_variant`, `abbreviation`,
   `trade_name`. Each alias carries a confidence score and source provenance.
   Unique constraint on `(entity_id, alias_type, alias_value)`.

3. **`fsma.entity_merge_history`** -- reversible merge/split log. When two
   entities are confirmed as the same, a `merge` action records the source
   entity IDs and target entity ID. Merges can be undone (`undo_merge`).
   Entities can also be `split`.

4. **`fsma.identity_review_queue`** -- ambiguous matches (confidence between
   0.60 and 0.90) are queued for human review. Each candidate pair stores
   matching fields with per-field similarity scores. Status: pending,
   confirmed_match, confirmed_distinct, deferred.

The `IdentityResolutionService` (`services/shared/identity_resolution.py`)
provides the API: `register_entity`, `add_alias`, `find_entity_by_alias`,
`find_potential_matches` (fuzzy, via `SequenceMatcher`).

---

## 4. Hash Chain / Audit Trail

Immutability is enforced through a tamper-evident hash chain
(`fsma.hash_chain`). The chain is **append-only** -- no updates, no deletes.

**How it works:**

1. Each event's canonical form is hashed to produce `event_hash` (SHA-256 of
   pipe-delimited fields).
2. The chain hash is computed: `SHA-256(previous_chain_hash || event_hash)`.
   The first event per tenant uses `'GENESIS'` as the previous hash.
3. Both hashes are stored on the event (`sha256_hash`, `chain_hash`) and in
   `fsma.hash_chain` with a monotonically increasing `sequence_num` per tenant.

**Verification:** Walk the chain from any point: recompute
`SHA-256(chain_hash[N-1] || event_hash[N])` and compare to `chain_hash[N]`.
Any mismatch proves tampering.

The legacy `fsma.cte_events` table also carries `sha256_hash` and `chain_hash`
directly. During the dual-write migration period, the `CanonicalEventStore`
writes to both tables and optionally skips the chain entry when the legacy path
already wrote it.

---

## 5. Compliance Rules

Rules are **versioned policy artifacts**, not application code. They live in
`fsma.rule_definitions` and are evaluated by the rules engine.

| Field | Purpose |
|---|---|
| `title` + `rule_version` | Unique identity (same title, bumped version) |
| `severity` | `critical`, `warning`, `info` |
| `category` | `kde_presence`, `temporal_ordering`, `lot_linkage`, `source_reference`, `identifier_format`, `quantity_consistency`, `entity_resolution`, `record_completeness`, `chain_integrity` |
| `applicability_conditions` | JSONB: which CTE types, commodities, and fields this rule applies to |
| `evaluation_logic` | JSONB: declarative spec -- type (`field_presence`, `field_format`, `temporal_order`, `custom`), target field, condition, params |
| `citation_reference` | Regulatory citation (e.g., "21 CFR 1.1345(b)(3)") |
| `failure_reason_template` | Human-readable template with `{field}` placeholders |
| `remediation_suggestion` | Actionable fix text |
| `effective_date` / `retired_date` | Active window |

**Evaluation results** (`fsma.rule_evaluations`): every time a rule runs against
an event, the outcome is recorded -- `pass`, `fail`, `warn`, or `skip` -- with
`why_failed` rendered from the template and `evidence_fields_inspected` showing
exactly which fields were checked and their values.

**Rule audit log** (`fsma.rule_audit_log`): append-only trail of every rule
creation, update, retirement, or activation. Proves rules were not silently
modified.

In Python, rule types are defined in `services/shared/rules/types.py`:
`RuleDefinition`, `RuleEvaluationResult`, `EvaluationSummary` (with a
`.compliant` property: `failed == 0`).

Note: rule definitions are **global** (not tenant-scoped). Rule evaluations
**are** tenant-scoped.

---

## 6. Exception Queue

When a rule evaluation fails, it can generate or attach to an **exception case**
(`fsma.exception_cases`). This turns passive alerts into managed work items.

**Lifecycle:** `open` -> `in_review` -> `awaiting_supplier` -> `resolved` | `waived`

Each case carries:
- `linked_event_ids` / `linked_rule_evaluation_ids` (UUID arrays)
- `owner_user_id` and `due_date` for SLA tracking
- `source_supplier` and `source_facility_reference` for attribution
- `waiver_reason`, `waiver_approved_by`, `waiver_approved_at` for override audit
- `request_case_id` FK linking to an active FDA request (inherits SLA deadline)

Supporting tables:
- **`fsma.exception_comments`** -- threaded discussion (note, status_change,
  assignment, supplier_response, system)
- **`fsma.exception_attachments`** -- supporting documents
- **`fsma.exception_signoffs`** -- approval chain (review, approve, waive, reject),
  each with identity and reason

---

## 7. FDA Request Workflow

The 24-hour FDA response promise is implemented as a 10-state machine in
`fsma.request_cases`:

```
intake -> scoping -> collecting -> gap_analysis -> exception_triage
       -> assembling -> internal_review -> ready -> submitted -> amended
```

**Scope types:** `tlc_trace` (trace specific lots), `product_recall`,
`facility_audit`, `date_range`, `custom`. Affected items are stored as
arrays: `affected_products`, `affected_lots`, `affected_facilities`.

**Response packages** (`fsma.response_packages`): immutable snapshots of the
data assembled for submission. Each version is SHA-256 sealed
(`package_hash`). Resubmission creates a new version with a `diff_from_previous`.
Contents include event IDs, rule evaluations, exception cases, trace data, and
gap analysis.

**Submission log** (`fsma.submission_log`): append-only record of every
submission -- type (initial, amendment, supplement, correction), method, notes,
and the package hash for integrity verification.

**Signoff chain** (`fsma.request_signoffs`): scope_approval, package_review,
final_approval, submission_authorization -- each with identity and timestamp.

Exception cases link to request cases via `request_case_id` FK, inheriting
the response deadline as their SLA.

---

## 8. Where Truth Lives

| Concept | Table | Key Columns |
|---|---|---|
| Canonical traceability event | `fsma.traceability_events` | `event_id`, `event_type`, `traceability_lot_code`, `kdes`, `normalized_payload` |
| Legacy CTE (migration period) | `fsma.cte_events` | `id`, `event_type`, `traceability_lot_code` |
| Legacy KDEs (replaced) | `fsma.cte_kdes` | `cte_event_id`, `kde_key`, `kde_value` |
| Ingestion batch receipt | `fsma.ingestion_runs` | `id`, `source_system`, `record_count`, `status` |
| Evidence documents | `fsma.evidence_attachments` | `event_id`, `document_type`, `file_hash`, `storage_uri` |
| Hash chain (immutable) | `fsma.hash_chain` | `cte_event_id`, `sequence_num`, `event_hash`, `chain_hash` |
| Canonical entity (firm/facility/product/lot) | `fsma.canonical_entities` | `entity_id`, `entity_type`, `canonical_name`, `gln`, `gtin` |
| Entity aliases | `fsma.entity_aliases` | `entity_id`, `alias_type`, `alias_value` |
| Entity merge history | `fsma.entity_merge_history` | `source_entity_ids`, `target_entity_id`, `action` |
| Identity review queue | `fsma.identity_review_queue` | `entity_a_id`, `entity_b_id`, `match_confidence`, `status` |
| Compliance rule catalog | `fsma.rule_definitions` | `rule_id`, `title`, `rule_version`, `category`, `severity` |
| Rule evaluation results | `fsma.rule_evaluations` | `event_id`, `rule_id`, `result`, `why_failed` |
| Rule change audit | `fsma.rule_audit_log` | `rule_id`, `action`, `old_values`, `new_values` |
| Exception work items | `fsma.exception_cases` | `case_id`, `severity`, `status`, `linked_event_ids` |
| Exception comments | `fsma.exception_comments` | `case_id`, `comment_text`, `comment_type` |
| Exception signoffs | `fsma.exception_signoffs` | `case_id`, `signoff_type`, `signed_by` |
| FDA request tracking | `fsma.request_cases` | `request_case_id`, `package_status`, `response_due_at` |
| Response package snapshots | `fsma.response_packages` | `request_case_id`, `package_contents`, `package_hash` |
| Submission audit trail | `fsma.submission_log` | `request_case_id`, `package_id`, `submission_type` |
| Request signoff chain | `fsma.request_signoffs` | `request_case_id`, `signoff_type`, `signed_by` |
| Legacy compliance alerts | `fsma.compliance_alerts` | `cte_event_id`, `severity`, `alert_type` |
| FDA export audit log | `fsma.fda_export_log` | `export_type`, `record_count`, `export_hash` |

---

## Migration Note

The system is in a dual-write migration period. New ingestion paths write to
`fsma.traceability_events` (canonical) via `CanonicalEventStore`. The legacy
`fsma.cte_events` and `fsma.cte_kdes` tables continue to receive writes for
backward compatibility with existing export and graph sync code. The
`dual_write` flag on `CanonicalEventStore` controls this behavior.

`fsma.compliance_alerts` (V002) is superseded by `fsma.rule_evaluations` (V044)
for new rule evaluation results.
