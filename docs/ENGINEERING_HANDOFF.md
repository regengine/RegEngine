# Engineering Hand-Off: Authority & Fact Lineage System

> **Status: Ship. Commit. Proceed.**

---

## 1. Schema (Authoritative)

| File | Purpose |
|------|---------|
| `migrations/V19__authority_lineage_tables.sql` | Authority documents, extracted facts, fact citations |

**Instruction:** Logic conforms to schema. Schema does not bend.

---

## 2. Governance (Enforced)

| File | Purpose |
|------|---------|
| `docs/SCHEMA_CHANGE_POLICY.md` | Change classification, deployment protocol, hard invariants |

**Instruction:** Any schema PR that violates this document is rejected without debate.

---

## 3. Explicit Scope for v1

- ✅ One rule family (CA/LA production compliance)
- ✅ Real authority docs in staging (SAG CBA, DGA, CA Labor Code, FilmLA)
- ✅ Replay-tested analysis runs
- ❌ No partitioning
- ❌ No event sourcing
- ❌ No schema auto-evolution

---

## 4. Hard Runtime Invariants

| Invariant | Implementation |
|-----------|----------------|
| Every analysis has an `AnalysisRun` | FK + application guard |
| Every verdict records `rule_version_id`, `fact_version_ids`, `authority_pointer_ids` | NOT NULL constraints |
| Missing data → `INDETERMINATE` | Application-level, never NULL verdicts |
| Corrections are new versions | No UPDATE on verdict tables |

---

## 5. Key Files

### Backend

| Component | Path |
|-----------|------|
| Models | `services/admin/app/pcos_models.py` |
| Service | `services/admin/app/authority_lineage_service.py` |
| Routes | `services/admin/app/pcos_routes.py` |

### Frontend

| Component | Path |
|-----------|------|
| Lineage Viewer | `frontend/src/components/pcos/FactLineageViewer.tsx` |

---

## 6. Future Docs (Non-Blocking)

When bandwidth permits:

- `DATA_RETENTION_POLICY.md` — regulatory + cost + privacy
- `MIGRATION_FAILURE_PLAYBOOK.md` — what to do when prod says "no"
- `RULE_AUTHORING_GUIDE.md` — so logic stays clean as rules scale
