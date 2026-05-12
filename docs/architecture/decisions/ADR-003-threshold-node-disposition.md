# ADR-003: Threshold Node Disposition for Neo4j Tenant Isolation

- **Status:** Proposed
- **Date:** 2026-05-11
- **Deciders:** Graph service owners, security/tenant-isolation working group
- **Related:** `docs/qa/neo4j-tenant-isolation-plan.md`, epic #1643 (Neo4j tenant-isolation implementation)

> Path note: `docs/qa/neo4j-tenant-isolation-plan.md` referenced this file as `docs/adr/00XX-…`. The repository's actual ADR home is `docs/architecture/decisions/` (see `ADR-template.md`, `ADR-002-…`). Filed here as ADR-003 for continuity.

## Context

The Neo4j tenant-isolation migration (`docs/qa/neo4j-tenant-isolation-plan.md`) found three node labels MERGEd on a tenant-free key, allowing cross-tenant collisions: `:Document`, `:Provision`, and `:Threshold`. `:Document` and `:Provision` both have rich downstream consumers (queries, exporters, traceability, FSMA engine) and must retain their node identity — those will move to composite `{key, tenant_id}` MERGE.

`:Threshold` is the open question. It is created at `services/graph/app/neo4j_utils.py:203` inside `CYPHER_UPSERT`:

```cypher
MERGE (t:Threshold {pid: ob.pid})
  ON CREATE SET t.value = …, t.unit = …, t.unit_normalized = …
MERGE (p)-[:HAS_THRESHOLD]->(t)
```

The `pid` MERGE key is the parent Provision's pid. By construction each Provision has at most one Threshold (the first containing-range hit in `upsert_from_entities`, lines 261–291). Threshold has no independent identity, no other inbound relationships, and no properties that cannot be expressed as scalar fields on the parent.

### Investigation evidence

A repo-wide grep (Python, Cypher, queries/, models/, routes, exporters, FSMA engine, admin, frontend) for the strings `:Threshold`, `(t:Threshold`, `Threshold {`, `HAS_THRESHOLD`, and the property names `threshold_value` / `threshold_unit` returns **only the three write-site lines in `neo4j_utils.py` (lines 203–206, 287–289)**. There is:

- No `MATCH (:Threshold)` anywhere.
- No traversal across `HAS_THRESHOLD` in any Cypher query, exporter, FSMA module, or admin/compliance service.
- No model class for Threshold in `services/graph/app/models/` (`base.py`, `framework.py`, `fsma_nodes.py`, `tenant_nodes.py` — none reference Threshold).
- One unrelated hit in `services/admin/app/models.py:199` (`override_data: {threshold_value: 10.0}` — a dict literal in an audit-override payload, not a graph read).

In other words, `:Threshold` is currently a write-only orphan. Today it is dead weight; under the tenant-isolation migration it becomes a tenant-isolation hole with zero compensating benefit.

## Decision

**Adopt option (a): collapse `:Threshold` into properties on `:Provision`.** The properties `threshold_value`, `threshold_unit`, and `threshold_unit_normalized` move onto the `:Provision` node; the `:Threshold` label and `HAS_THRESHOLD` relationship are removed from `CYPHER_UPSERT`. Threshold drops out of the tenant-isolation migration scope entirely.

## Consequences

- **Cypher change:** Replace the `FOREACH (… threshold_is_set …)` block in `CYPHER_UPSERT` with property sets on `p` (`p.threshold_value`, `p.threshold_unit`, `p.threshold_unit_normalized`). Composite-key constraint in plan Step 2 for Threshold is no longer needed.
- **Migration:** Plan Step 4 (cross-tenant copy-out) must, for any pre-existing `:Threshold` nodes, copy their three properties onto the related `:Provision` and then `DETACH DELETE` them. Single-pass script; idempotent.
- **Constraints:** Drop `threshold_pid_tenant_unique` from Step 2 of the plan. No new Threshold constraint required.
- **Tests:** `services/graph/tests/` has no `:Threshold`-asserting tests today (verified). New test should assert that after upsert, provisions surface threshold properties directly.
- **Forward path:** If a future requirement adds many-thresholds-per-provision or cross-provision threshold sharing, reintroduce the node then with a proper composite key. Cost of reversal is low because there are no consumers to migrate.

## Alternatives considered

**(b) Keep `:Threshold` as a node, MERGE on `{pid, tenant_id}`.** Rejected because it preserves a label that nothing reads, adds a constraint and a tenant-isolation surface, and pays migration cost (copy-out, constraint creation, future audit) for zero downstream consumer. If consumers existed, this would be the safer choice; they do not.

**Defer the decision.** Rejected: the evidence is unambiguous (single write site, zero readers). Deferring would block Step 2 of the tenant-isolation plan without producing new information.

## References

- Plan: `docs/qa/neo4j-tenant-isolation-plan.md` (Step 1 — Decide Threshold disposition)
- Code: `services/graph/app/neo4j_utils.py` lines 183–213, 248–301
- Epic: #1643 — Neo4j tenant-isolation implementation
- Audit context: `~/.claude/projects/-Users-sellers-RegEngine/memory/project_session_2026_05_11.md`
