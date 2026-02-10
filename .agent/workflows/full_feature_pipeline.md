---
description: Full feature pipeline using multi-agent chain (build → security → UI → QA)
---

# Full Feature Pipeline

Multi-agent chain workflow for implementing and validating a complete feature. Ensures every feature passes through Builder and Guardian agents before merge.

## Overview

```
Developer creates Issue → Bot-{Vertical} builds → Bot-Security reviews
  → Bot-UI audits frontend → Bot-QA validates tests → Ready for merge
```

## 1. Create Agent Task Issue

Create an issue using the "Agent Task" template (`.github/ISSUE_TEMPLATE/agent-task.yml`):
- Select the appropriate Builder agent (Bot-FSMA, Bot-PCOS, Bot-Energy, etc.)
- Set chain to "→ Bot-Security → Bot-UI → Bot-QA (Full review)"
- Fill in task description and acceptance criteria

## 2. Builder Agent — Implementation

Summon the vertical-specific builder agent:

```bash
python scripts/swarm_orchestrator.py --summon fsma --task "YOUR_TASK_DESCRIPTION" --output json
```

**Builder agent responsibilities:**
- Implement the feature following persona directives
- Write tests (>80% coverage for new code)
- Produce structured output per `.agent/protocols/output_schema.md`
- Include handoff context for Bot-Security

**Completion criteria:**
- [ ] Feature implemented
- [ ] Tests written and passing
- [ ] Output JSON produced with handoff block

## 3. Bot-Security — Security Review

Feed the Builder's output as chain context:

```bash
python scripts/swarm_orchestrator.py --chain security --task "Review [FEATURE] for security vulnerabilities" --output json
```

**Security review checklist:**
- [ ] No IDOR vulnerabilities
- [ ] Tenant isolation maintained (Double-Lock)
- [ ] Input sanitization via Pydantic
- [ ] Parameterized queries (no string interpolation)
- [ ] No hardcoded secrets
- [ ] API authentication required
- [ ] Audit logging for security events

**If critical risk found:** Chain halts. Fix before proceeding.

## 4. Bot-UI — Frontend Audit (if applicable)

Only if the feature touches `frontend/`:

```bash
python scripts/swarm_orchestrator.py --chain ui --task "Audit frontend changes for [FEATURE]" --output json
```

**UI audit checklist:**
- [ ] Design tokens used (no hardcoded colors)
- [ ] Tailwind classes (no inline styles)
- [ ] Existing components reused
- [ ] Responsive breakpoints
- [ ] Accessibility (ARIA, keyboard nav)

## 5. Bot-QA — Final Validation

```bash
python scripts/swarm_orchestrator.py --chain qa --task "Validate tests and coverage for [FEATURE]" --output json
```

**QA validation checklist:**
- [ ] All existing tests still pass
- [ ] New tests cover happy path + edge cases
- [ ] Security tests included (`@pytest.mark.security`)
- [ ] No flaky tests (run 3x)
- [ ] Coverage meets >80% threshold
- [ ] Agent output schema is valid

## 6. Merge

Once all agents produce `status: completed`:

```bash
# Verify all tests pass
pytest -q services/*/tests

# Format code
make fmt

# Create PR
gh pr create --title "feat(scope): description" --body "Agent chain: complete"
```
