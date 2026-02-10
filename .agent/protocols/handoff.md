# Inter-Agent Handoff Protocol

> Defines how agents in the Fractal Agent Swarm communicate, hand off work, and resolve conflicts.

## Handoff Message Format

Every handoff between agents uses this YAML structure:

```yaml
handoff:
  from_agent: Bot-FSMA           # The agent completing its scope
  to_agent: Bot-Security          # The next agent in the chain
  priority: high                  # critical | high | medium | low
  timestamp: "2026-02-09T22:15:00Z"
  
  context: |
    Brief description of what was done and why the next agent is needed.
    Include enough detail for the receiver to continue without re-reading all files.
  
  files_touched:
    - path: services/graph/app/routers/fsma/validate.py
      action: created             # created | modified | deleted
    - path: services/graph/tests/test_fsma_validate.py
      action: created
  
  risks_found:
    - severity: medium
      description: "New endpoint accepts TLC strings — potential injection vector"
      requires_review: true
    - severity: low
      description: "No rate limiting applied yet"
      requires_review: false
  
  action_required: |
    Review for IDOR vulnerabilities, verify tenant isolation at the RLS layer,
    and confirm parameterized Cypher queries are injection-safe.
  
  tests_status:
    added: 12
    modified: 0
    all_passing: true
```

## Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| `from_agent` | ✅ | Source agent persona name |
| `to_agent` | ✅ | Target agent persona name |
| `priority` | ✅ | Urgency level |
| `context` | ✅ | What was done and why handoff is needed |
| `files_touched` | ✅ | All files created/modified/deleted |
| `action_required` | ✅ | What the next agent must do |
| `risks_found` | ⚠️ | Required if any risks were identified |
| `tests_status` | ⚠️ | Required if any code was changed |

## Chain Execution

### Sequential Chains

The most common pattern — agents execute one after another:

```
Bot-FSMA → Bot-Security → Bot-UI → Bot-QA
  (build)     (review)     (audit)   (test)
```

Each agent receives:
1. The original task description
2. All prior handoff blocks (accumulated context)
3. Its own persona directives

### Parallel Chains

For independent reviews, agents can run in parallel:

```
             ┌→ Bot-Security (security review)
Bot-FSMA ────┤
  (build)    └→ Bot-UI (frontend audit)
                        │
                Bot-QA ←┘ (merge + test)
```

### Chain Termination

A chain completes when:
- The final agent produces output with `handoff: null`
- Any agent sets `priority: critical` (chain halts, escalates to human)
- All agents in the chain have produced their output

## Conflict Resolution

### Priority Rules

1. **Security always wins.** If Bot-Security flags a risk as `critical`, the chain halts regardless of other agents' status.
2. **Guardians (Squad B) override Builders (Squad A)** on cross-cutting concerns:
   - Security posture
   - Infrastructure standards
   - Design system compliance
3. **Builders (Squad A) override Guardians (Squad B)** on domain logic:
   - Regulatory interpretation
   - Business rule accuracy
   - Vertical-specific calculations
4. **Two Guardians disagree → Escalate to human.**
5. **Two Builders disagree → The more specific persona wins** (e.g., Bot-FSMA over Bot-Energy on food safety).

### Disagreement Format

When an agent disagrees with a prior agent's decision:

```yaml
disagreement:
  with_agent: Bot-Infra
  regarding: "Version pinning of neo4j-driver"
  my_position: "Need neo4j-driver>=5.15 for the new FSMA graph traversal API"
  their_position: "Pin to neo4j-driver==5.14.1 for deterministic builds"
  resolution: "escalate"  # accept | override | escalate
  justification: "Domain-specific requirement — new API is required by 21 CFR 1.1455"
```

## Sweep Patterns

Predefined agent chains for recurring tasks:

| Sweep | Chain | Trigger |
|-------|-------|---------|
| `security` | Bot-Security | Weekly (Monday) |
| `ui-drift` | Bot-UI | Weekly (Monday) |
| `infra-health` | Bot-Infra | Monthly |
| `full-audit` | Bot-Security → Bot-UI → Bot-Infra → Bot-QA | On demand |
| `feature` | Bot-{vertical} → Bot-Security → Bot-UI → Bot-QA | Per feature |
