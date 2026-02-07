# RegEngine Architecture

> **RegEngine is compliance-as-infrastructure.** We provide the regulatory intelligence layer that production systems need to operate lawfully across jurisdictions.

---

## Multi-Domain Architecture

RegEngine implements compliance through **domain-specific modules** rather than premature abstraction. This allows us to:

- Learn regulatory patterns from real implementations
- Move fast in new verticals without generic-layer constraints
- Extract common patterns only after proving them in production

### Current Implementations

| Module | Domain | Regulations | Service | Port |
|--------|--------|-------------|---------|------|
| **FSMA 204** | Food traceability | FDA Food Safety Modernization Act | `services/compliance` | 8500 |
| **PCOS** | Entertainment production | SAG-AFTRA, DGA, CA Labor Code, FilmLA | `services/admin` | 8000 |

**This is intentional multi-vertical strategy, not technical debt.**

---

## Conceptual Architecture

Both modules implement the same regulatory intelligence patterns:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   AUTHORITY     │───▶│  EXTRACTED FACT  │───▶│    CITATION     │
│   DOCUMENT      │    │   (Versioned)    │    │   (Evidence)    │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                      │                       │
        ▼                      ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  RULE VERSION   │───▶│  RULE EVALUATION │───▶│   AUDIT VERDICT │
│(Effective-Dated)│    │  (Context-Bound) │    │   (Immutable)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

**Key Properties:**
- **Append-only**: No UPDATE or DELETE on versioned tables
- **Traceable**: Every verdict links to source authority
- **Temporal**: Rules and facts have effective date ranges
- **Reproducible**: Any historical analysis can be re-derived

---

## Schema Mapping

| Concept | FSMA Tables | PCOS Tables | Governance |
|---------|-------------|-------------|------------|
| Authority Sources | `fsma_authority_documents`, `fsma_authority_versions` | `pcos_authority_documents` | Immutable, SHA-256 hashed |
| Extracted Facts | `fsma_facts` | `pcos_extracted_facts` | Versioned, supersedes chain |
| Compliance Rules | `fsma_rules` | `pcos_rule_definitions` | Effective-dated |
| Analysis Results | `fsma_evaluations` | `pcos_rule_evaluations` | Evidence-linked |
| Audit Trail | `fsma_audit_log` | `pcos_audit_events` | Append-only |

> Both modules use prefix namespacing (`fsma_*`, `pcos_*`) to allow coexistence in a shared database while maintaining clear domain boundaries.

---

## Shared Governance Infrastructure

Both FSMA and PCOS enforce identical governance principles:

### Immutability Triggers
```sql
-- Prevents UPDATE/DELETE on versioned tables
CREATE TRIGGER prevent_authority_modifications
  BEFORE UPDATE OR DELETE ON pcos_authority_documents
  FOR EACH ROW EXECUTE FUNCTION raise_immutable_violation();
```

### Schema Version Tracking
```sql
CREATE TABLE schema_governance (
  version TEXT PRIMARY KEY,
  checksum TEXT NOT NULL,
  applied_at TIMESTAMPTZ DEFAULT now(),
  approved_by TEXT
);
```

### Evidence Chain Integrity
- Citations must reference existing facts
- Facts must reference existing authority documents
- Verdicts must record rule version + fact versions used

**Implementation:** See [migrations/V20__schema_governance.sql](file:///Users/christophersellers/Desktop/RegEngine/services/admin/migrations/V20__schema_governance.sql)

---

## Service Topology

```
                              ┌──────────────────────┐
                              │     Load Balancer    │
                              │   (nginx gateway)    │
                              └──────────┬───────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
              ▼                          ▼                          ▼
     ┌────────────────┐        ┌────────────────┐        ┌────────────────┐
     │   Frontend     │        │   Admin API    │        │  Graph API     │
     │   (Next.js)    │        │   (FastAPI)    │        │  (FastAPI)     │
     │   Port: 3000   │        │   Port: 8000   │        │  Port: 8200    │
     │                │        │   (PCOS)       │        │                │
     └────────────────┘        └────────────────┘        └────────────────┘
                                         │                          │
              ┌──────────────────────────┼──────────────────────────┤
              │                          │                          │
              ▼                          ▼                          ▼
     ┌────────────────┐        ┌────────────────┐        ┌────────────────┐
     │  Ingestion     │        │  Compliance    │        │  Opportunity   │
     │   (FastAPI)    │        │    (FSMA)      │        │    API         │
     │   Port: 8002   │        │  Port: 8500    │        │  Port: 8300    │
     └────────────────┘        └────────────────┘        └────────────────┘
```

---

## Data Flow: How a Compliance Query Works

1. **Ingest** (port 8002): PDF uploaded → extracted to `authority_documents`
2. **NLP** (port 8100): Extract facts → `pcos_extracted_facts` / `fsma_facts`
3. **Compliance** (8500) or **Admin** (8000): Apply rules → generate evaluations
4. **Graph** (port 8200): Query evidence chains across citations
5. **Frontend** (port 3000): Display verdict + provenance to user

> **Critical:** Steps 1-4 are append-only. Historical queries replay deterministically.

---

## Port Summary

| Port | Service | Domain |
|------|---------|--------|
| 3000 | Frontend (Next.js) | All |
| 8000 | Admin API (PCOS) | Entertainment |
| 8002 | Ingestion API | Shared |
| 8100 | NLP Service | Shared |
| 8200 | Graph API | Shared |
| 8300 | Opportunity API | Shared |
| 8500 | Compliance API (FSMA) | Food Safety |
| 8600 | Scheduler | Shared |
| 5432 | PostgreSQL | All |
| 6379 | Redis | All |
| 7687 | Neo4j Bolt | All |

---

## Future Consolidation

We will extract a generic `core_compliance` module when:

- [ ] We have 3+ domain implementations in production
- [ ] Common patterns are stable across domains
- [ ] Customer demand justifies migration risk

**Until then:** Domain-specific modules with shared governance principles.

### Candidate Third Verticals
- **Pharmaceutical (21 CFR Part 11)** ← Most likely next
- Financial services (SOX, FINRA)
- Construction (OSHA, local permitting)

> **Strategic focus:** Pharmaceutical leverages existing FDA credibility from FSMA. Same regulatory authority = faster time-to-market.

---

## For Investors & Engineers

### Why This Matters

**For investors:** This architecture proves RegEngine works across fundamentally different regulatory domains (food safety ≠ entertainment production). That's evidence of platform viability, not a point solution.

**For engineers:** Each module is a reference implementation. When you build a new vertical, copy the patterns from FSMA or PCOS rather than importing a half-baked abstraction.

### The Thesis

> Premium pricing requires audit-grade defensibility.  
> Audit-grade requires immutable provenance.  
> Immutable provenance requires schema discipline.

Both FSMA and PCOS implement this thesis. The table names differ; the principles don't.

---

## Quick Reference

| What | Where |
|------|-------|
| FSMA routes | `/v1/fsma/*` on port 8500 |
| PCOS routes | `/pcos/*` on port 8000 |
| Schema governance | `migrations/V20__schema_governance.sql` |
| Change policy | `docs/SCHEMA_CHANGE_POLICY.md` |
| PCOS models | `services/admin/app/pcos_models.py` |
| FSMA extractor | `services/nlp/app/extractors/fsma_extractor.py` |

---

## Health Check Endpoints

All services expose `/health`:

```bash
# Check all services
for port in 8000 8002 8100 8200 8300 8500 8600; do
  echo "Port $port: $(curl -s http://localhost:$port/health | jq -r .status)"
done
```
