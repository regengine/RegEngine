# Schema Change Policy

> **Core Principle:** The schema defines the validity of the product. Logic conforms to schema. Schema does not bend.

---

## 1. Purpose

This policy governs all changes to the RegEngine compliance database schema. It supports:
- Audit defensibility through append-only, versioned structures
- Traceability from authority documents to verdicts
- Reproducibility of any historical analysis

---

## 2. Change Classification

| Type | Examples | Approval |
|------|----------|----------|
| **Additive** | New tables, new columns (nullable) | Tech lead |
| **Semantic** | Column rename, type widening | Tech lead + Architect |
| **Destructive** | Column removal, constraint deletion | Architect + Compliance |

> **Rule:** Destructive changes require a 30-day deprecation cycle and audit log review.

---

## 3. SQL Script Requirements

### 3.1 Structure

All migrations must be:
- Idempotent (safe to re-run)
- Transactional (atomic success/failure)
- Sequentially versioned (`V{N}__description.sql`)

### 3.2 Versioning (Self-Enforcing)

```text
Each migration must insert metadata into the `schema_migrations` table
(version, checksum, git_sha) within the same transaction as the schema change.
```

> If a migration runs without recording itself, it is invalid by definition.

### 3.3 Immutability Rules

- Facts, verdicts, and analysis runs are **append-only**
- Corrections create new versions with `supersedes_id` reference
- No `UPDATE` or `DELETE` on compliance-relevant tables

---

## 4. Deployment Protocol

### 4.1 Review Requirements

- [ ] PR includes migration SQL + rollback script
- [ ] Schema diagram updated (if structural change)
- [ ] Integration tests pass against migrated schema

### 4.2 Staging Validation

- [ ] Migration applied to staging
- [ ] Replay test: Historical analyses produce identical verdicts
- [ ] Performance: No query regression > 20%

### 4.3 Pre-Migration Protocol

```text
Before applying any schema migration in production:

- Notify #engineering at least 30 minutes before the deployment window
- Confirm no long-running analysis runs are in progress
- Verify that a database backup has completed within the last 24 hours
```

> Prevents the two most common self-inflicted outages: breaking analyses mid-flight, and discovering "the last backup was 6 days ago" after the fact.

---

## 5. Hard Runtime Invariants

Engineering must implement. Reviewers must enforce.

| Invariant | Enforcement |
|-----------|-------------|
| Every analysis has an `AnalysisRun` | Application-level + FK constraint |
| Every verdict records `rule_version_id`, `fact_version_ids`, `authority_pointer_ids` | NOT NULL + FK constraints |
| Missing data → `INDETERMINATE` | Application-level (never NULL verdicts) |
| Corrections are new versions | No UPDATE on verdict tables (trigger-enforced) |
| `fsma.traceability_events` is append-only | v141 trigger (`traceability_events_mutation_policy`, `traceability_events_no_truncate`); see 5.1 |
| Legacy CTE tables are read-only retention | No new writers, columns or indexes on `fsma.cte_events` and `fsma.critical_tracking_events`; see 5.2 |

### 5.1 Sanctioned mutations of `fsma.traceability_events`

The canonical evidence table rejects every UPDATE, DELETE and TRUNCATE at the database (migration
v141, `08c7cf36ddbe`) except the two writers the application already relies on:

| Writer | Columns it may change | Constraint |
|--------|-----------------------|------------|
| Amendment (`services/shared/canonical_persistence/writer.py`) | `status`, `amended_at` | `status` may only move `active -> superseded` |
| Rules engine (`services/shared/rules/engine.py`) | `evaluation_verdict`, `no_verdict_reason`, `evaluation_error`, `evaluated_at` | none |

Any statement that changes another column, moves `status` anywhere else, deletes or truncates
raises `check_violation`. A correction is a new event that supersedes the old one, never an edit.
The break-glass is `SET LOCAL fsma.allow_mutation = 'true'` inside one transaction (the same GUC
as `fsma.cte_events`, `fsma.hash_chain` and `fsma.correction_patches`); the runtime resets it per
transaction and per pooled connection. Since migration v142 (`17fc5f9d1e69`) the GUC is an intent
flag, not an authorization: `fsma.break_glass_authorized(oid)` honours it only for a superuser or a
member of the guarded table's owner (the migration role). The runtime roles `regengine` and
`regengine_sysadmin` are never members of it, so a session holding the application credential
cannot arm the break-glass even with raw SQL. The one runtime mutation that needs it, the CTE
retention purge in `services/scheduler/service.py`, calls `fsma.arm_retention_purge(tenant_id,
min_age)` (SECURITY DEFINER) instead: the arm is scoped to the current transaction, one tenant,
`fsma.cte_events` and rows older than `min_age` (floor 730 days), and permits DELETE only; it
cannot widen into an UPDATE, another table or a younger row. Adding a column to the allowlist is a
schema change under this policy: update the trigger in a new migration, this table, and
`tests/migrations/test_v141_traceability_events_append_only.py` together; changing who may
break glass is a change to v142's helpers and
`tests/migrations/test_v142_break_glass_authorization.py`.

### 5.2 Read freeze on the legacy CTE tables (SEL-589)

`fsma.traceability_events` is the committed canonical contract for all new FSMA evidence (product
decision 2026-10-27, `docs/product/PRODUCT_PRD_2026-10.md`). `fsma.cte_events` and
`fsma.critical_tracking_events` are read-only retention: no new writers, columns or indexes. Their
reads are not frozen yet: the v1 FDA export and recall readers still default to `fsma.cte_events`
behind `FDA_EXPORT_V1_READ_CANONICAL` (default off, `services/ingestion/app/fda_export/queries.py`).
Each export, recall, trace and verification reader is cut over one at a time, only after its
historical-row and canonical coverage is documented. A migration that adds to either legacy table
is rejected under section 7.

---

## 6. Prohibited Patterns

| Pattern | Why Prohibited |
|---------|---------------|
| `UPDATE` on fact/verdict tables | Breaks audit trail |
| `DELETE` without archive | Destroys evidence |
| Schema changes outside migrations | Untracked drift |
| Optional authority references | Breaks traceability |

---

## 7. Violation Response

| Severity | Response |
|----------|----------|
| Pre-merge detection | PR rejected, no discussion |
| Post-merge detection | Immediate revert, incident filed |
| Production impact | Full incident review, policy update if systemic |

---

## Appendix: Current Schema Version

- **Version:** 1.3.0
- **Last Updated:** 2026-10-30 (v142 break-glass authorization by role; retention purge arm)
- **Git SHA:** (auto-populated by migration)
