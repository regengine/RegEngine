# Schema Change Policy

> **Core Principle:** The schema defines the validity of the product. Logic conforms to schema. Schema does not bend.

---

## 1. Purpose

This policy governs all changes to the RegEngine compliance database schema. It ensures:
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

- **Version:** 1.1.2
- **Last Updated:** 2026-01-22
- **Git SHA:** (auto-populated by migration)
