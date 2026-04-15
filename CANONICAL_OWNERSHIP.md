# Canonical Ownership

**Purpose:** For each truth-bearing concept, one obvious answer to
"what is the canonical representation of X?"

Last updated: 2026-04-14.

---

## Canonical Event

| | |
|---|---|
| **Definition** | A normalized supply chain traceability event (CTE) with Key Data Elements (KDEs), provenance metadata, content hash, and chain hash. Represents one discrete action in the food supply chain: harvesting, cooling, packing, receiving, shipping, or transformation. |
| **Schema** | `TraceabilityEvent` in `services/shared/canonical_event.py`. Key fields: `event_id`, `tenant_id`, `event_type` (CTEType enum), `traceability_lot_code`, `kdes` (JSONB), `sha256_hash`, `chain_hash`, `status` (ACTIVE/SUPERSEDED/REJECTED/DRAFT), `idempotency_key`, `provenance_metadata`. |
| **Persistence** | `fsma.traceability_events` table (canonical). Legacy: `fsma.cte_events` + `fsma.cte_kdes` (dual-write, to be removed). |
| **Who writes** | Ingestion service, via `shared/canonical_persistence.py`. |
| **Who reads** | Compliance (rule evaluation), graph (visualization), admin (dashboard), export (FDA artifacts). |
| **Versioning** | Immutable once status=ACTIVE. Amendments create a new event with `supersedes_event_id` pointing to the original, and the original status becomes SUPERSEDED. |
| **Derived vs Canonical** | **Canonical.** This is the source of truth. `cte_events` is a legacy derived copy (dual-write) that will be removed. |

---

## Canonical Entity

| | |
|---|---|
| **Definition** | A resolved real-world entity in the supply chain: a firm, facility, product, lot, or trading relationship. Carries standard identifiers (GLN, GTIN, FDA registration) plus verification status and confidence score. |
| **Schema** | `CanonicalEntity` in `services/shared/identity_resolution.py`. Key fields: `entity_id`, `tenant_id`, `entity_type` (firm/facility/product/lot/trading_relationship), `canonical_name`, `gln`, `gtin`, `fda_registration`, `verification_status` (verified/unverified/pending_review), `confidence_score`. |
| **Persistence** | `fsma.canonical_entities` (entities), `fsma.entity_aliases` (fuzzy matching aliases), `fsma.entity_merge_history` (merge/split audit trail), `fsma.identity_review_queue` (human review for ambiguous matches). |
| **Who writes** | Ingestion service (auto-create on new entity references), admin service (manual entity creation/merge), identity resolution module (auto-merge high-confidence matches). |
| **Who reads** | All services that reference supply chain participants. Graph uses for visualization. Compliance uses for cross-entity rule evaluation. Export uses for FDA column mapping. |
| **Versioning** | Mutable (updated on merge, verification, correction). History tracked via `fsma.entity_merge_history` (action: merge/split/undo_merge). `is_active` boolean for soft-delete. |
| **Derived vs Canonical** | **Canonical.** Neo4j graph nodes are derived copies used for visualization/traversal, not the source of truth. |

---

## Rule Definition

| | |
|---|---|
| **Definition** | A versioned FSMA compliance rule that defines what to check, when it applies, how severe a violation is, and what the regulatory citation is. |
| **Schema** | `RuleDefinition` in `services/shared/rules/types.py`. Key fields: `rule_id`, `rule_version`, `title`, `severity` (critical/warning/info), `category`, `applicability_conditions` (which CTE types), `evaluation_logic` (field checks or relational queries), `citation_reference`, `effective_date`, `retired_date`, `failure_reason_template`, `remediation_suggestion`. |
| **Persistence** | `fsma.rule_definitions` table. |
| **Who writes** | Admin service (seeded via `shared/rules/seeds.py`, can be updated manually). |
| **Who reads** | Compliance evaluation via `shared/rules/engine.py` (loads WHERE retired_date IS NULL AND effective_date <= CURRENT_DATE). |
| **Versioning** | `rule_version` integer. Old versions retained (retired_date set). Only active rules evaluate. |
| **Derived vs Canonical** | **Canonical.** The `FSMA_RULE_SEEDS` in code are the initial seed data; the database table is the runtime source of truth. |

---

## Rule Evaluation

| | |
|---|---|
| **Definition** | The result of applying one rule to one event. Records pass/fail/warn/skip/error, the evidence fields inspected, and the confidence of evaluation. |
| **Schema** | `RuleEvaluationResult` in `services/shared/rules/types.py`. Key fields: `evaluation_id`, `rule_id`, `rule_version`, `result` (pass/fail/warn/skip/error), `why_failed`, `evidence_fields_inspected` (list of dicts), `confidence`, `citation_reference`, `remediation_suggestion`. Aggregated into `EvaluationSummary` (total/passed/failed/warned/skipped counts + `compliant` property). |
| **Persistence** | `fsma.rule_evaluations` table (when `persist=True`). |
| **Who writes** | Compliance service via `shared/rules/engine.py` (evaluate_event, evaluate_events_batch). |
| **Who reads** | Export (FDA V2 format includes compliance status + rule failures), admin dashboard, monitoring. |
| **Versioning** | Each evaluation references the rule_version at time of evaluation. Re-evaluation creates new rows, does not overwrite. |
| **Derived vs Canonical** | **Derived** from rule definitions + canonical events. Can be regenerated by re-running evaluation. However, persisted results are the record of what was assessed at a point in time. |

---

## Audit Record

| | |
|---|---|
| **Definition** | A security/compliance audit event recording who did what, when, from where, and with what result. Covers authentication, authorization, data access, data modification, configuration changes, security alerts, and API operations. |
| **Schema** | Defined in `services/shared/audit_logging.py`. Key fields: `event_id`, `tenant_id`, `actor` (AuditActor: actor_id, actor_type, username, IP, user_agent), `event_type` (60+ AuditEventType values), `category` (10 AuditEventCategory values), `severity` (DEBUG/INFO/WARNING/ERROR/CRITICAL), `resource_type`, `resource_id`, `action_details` (JSONB), `result` (success/failure). |
| **Persistence** | Application-level audit log (structlog/database). Tamper-evidence provided by `fsma.hash_chain` table for compliance-bearing events. |
| **Who writes** | All services via `shared/audit_logging.py`. |
| **Who reads** | Admin service (security dashboard), compliance (audit trail), export (compliance artifacts). |
| **Versioning** | Append-only. Events are immutable once written. |
| **Derived vs Canonical** | **Canonical.** The audit record IS the evidence. Cannot be regenerated. |

---

## Export Artifact

| | |
|---|---|
| **Definition** | A generated file (spreadsheet) containing traceability events formatted to FDA 204 specifications. Includes 33 columns (V1) or 37 columns (V2 with compliance status). Hashed for integrity verification. |
| **Schema** | `FDA_COLUMNS` / `FDA_COLUMNS_V2` specs in `services/ingestion/app/fda_export_service.py`. Mapping function: `_event_to_fda_row()`. |
| **Persistence** | Generated on-demand. Metadata recorded in `fsma.fda_export_log` (export_type, query params, record_count, export_hash SHA-256, generated_by, generated_at). |
| **Who writes** | Export service (in ingestion) via `fda_export_service.py`. |
| **Who reads** | Customers (download), FDA (regulatory submission), admin (monitoring via `export_monitoring.py`). |
| **Versioning** | Each generation is a new artifact with its own hash. Export log tracks all generations. |
| **Derived vs Canonical** | **Derived** from canonical events + rule evaluations + canonical entities. Can be regenerated, but each generation is logged immutably. The export log entry (hash, timestamp, who) is canonical evidence that an export occurred. |

---

## Duplicate / Ambiguous Definitions to Resolve

| Issue | Where | Action |
|-------|-------|--------|
| Dual event storage | `traceability_events` (canonical) vs `cte_events` (legacy) | Remove dual-write to `cte_events` after migration complete. `canonical_persistence.py` contains the dual-write code — clearly marked as temporary. |
| Audit logging scope | `shared/audit_logging.py` mixes security audit (login, access) with compliance audit (data modification, export) | Split into security audit (application concerns) and compliance audit (regulatory concerns) during Phase 3 refactoring. |
| Entity identity in Neo4j vs PostgreSQL | Graph service maintains entity nodes in Neo4j; `canonical_entities` in PostgreSQL | PostgreSQL is canonical. Neo4j is derived. Drop Neo4j dependency for identity resolution. |
