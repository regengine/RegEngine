---
description: Validate a new agent's first task against swarm quality standards
---

# Onboarding Validation Workflow

Use this workflow to validate that a newly added or existing agent produces correct, schema-compliant output on its first task.

## 1. Pre-Flight Checks

Verify the agent is properly configured:

// turbo
```bash
python scripts/summon_agent.py --list
```

Check persona file exists and has required sections:

// turbo
```bash
for section in "Identity" "Domain Scope" "Mission Directives" "Testing Requirements" "Context Priming"; do
  echo -n "  $section: "
  grep -l "$section" .agent/personas/*.md | wc -l | tr -d ' '
done
```

## 2. Summon Agent with Test Task

Give the agent a controlled test task:

```bash
python scripts/summon_agent.py --role {ROLE} --task "Review your domain scope files and produce a status report" --output json
```

## 3. Validate Output Schema

Save the agent's output to a file and validate:

```bash
python scripts/swarm_orchestrator.py --validate agent_output.json
```

**Expected result:** `✅ Output from Bot-{Name} is valid.`

## 4. Check Output Quality

Manually verify the output against this rubric:

| Criterion | Weight | Pass/Fail |
|-----------|--------|-----------|
| Agent name matches persona | 10% | |
| Task description is accurate | 10% | |
| Status is valid enum value | 10% | |
| Confidence is between 0.0-1.0 | 5% | |
| Files changed are real paths | 15% | |
| Tests section is populated | 15% | |
| Risks are well-described | 15% | |
| Recommendations are actionable | 10% | |
| Handoff is appropriate (or null) | 10% | |

**Pass threshold:** ≥80% of weighted criteria.

## 5. Chain Simulation

Test the agent in a chain:

```bash
python scripts/swarm_orchestrator.py --chain {ROLE},qa --task "Verify {ROLE} agent can chain to Bot-QA"
```

Verify:
- [ ] First agent's output includes handoff to Bot-QA
- [ ] Chain context accumulates correctly
- [ ] Bot-QA receives prior agent's handoff block

## 6. Sweep Simulation (Guardians only)

If the agent is Squad B (Guardian), test as a sweep:

```bash
python scripts/swarm_orchestrator.py --sweep {SWEEP_TYPE}
```

## 7. Record Results

If validation passes, the agent is cleared for production use.
If validation fails, iterate on the persona file and re-test.
