---
description: How to add a new agent persona to the Fractal Agent Swarm
---

# How to Add a New Persona

Follow this workflow to add a new agent persona to the RegEngine Fractal Agent Swarm.

## 1. Create the Persona File

Create `.agent/personas/{role_key}.md` using this template:

```markdown
# Bot-{Name} — {Short Description}

**Squad:** A (Builders — Vertical Specialists) OR B (Guardians — Cross-Cutting)

## Identity

You are **Bot-{Name}**, the {domain} specialist for RegEngine. {1-2 sentences about the agent's
core mission and personality.}

## Domain Scope

| Path | Purpose |
|------|---------|
| `services/{service}/` | {description} |
| `industry_plugins/{vertical}/` | {description} |

## Key Documentation

- [Relevant KI](file:///path/to/ki/artifact.md)

## Mission Directives

1. **{Directive 1}.** {Explanation}
2. **{Directive 2}.** {Explanation}
3. **{Directive 3}.** {Explanation}
(minimum 5 directives)

## Testing Requirements

- All {domain} endpoints must have tests covering:
  - {scenario 1}
  - {scenario 2}
  - Tenant isolation (cross-tenant data leak prevention)
  - `@pytest.mark.security` for auth flows

## Context Priming

When activated, immediately review:
1. `{primary file or directory}`
2. `{secondary file}`
3. `{documentation link}`
```

## 2. Register in Orchestrator

Add the new role to `AGENT_REGISTRY` in `scripts/swarm_orchestrator.py`:

```python
"role_key": AgentRole(
    key="role_key",
    label="Bot-{Name}",
    squad=Squad.BUILDERS,  # or Squad.GUARDIANS
    persona_file="{role_key}.md",
    description="{Short description}",
    domain_paths=["services/{service}/", "industry_plugins/{vertical}/"],
),
```

> **Note:** `summon_agent.py` uses dynamic discovery, so it will automatically find the new persona file. Only the orchestrator needs manual registration.

## 3. Update Labeler

Add a label mapping in `.github/labeler.yml`:

```yaml
agent:{role_key}:
  - changed-files:
    - any-glob-to-any-file:
      - 'services/{service}/**'
      - 'industry_plugins/{vertical}/**'
```

## 4. Update Issue Template

Add the new agent to the dropdown in `.github/ISSUE_TEMPLATE/agent-task.yml`:

```yaml
- "Bot-{Name} ({Short Description})"
```

## 5. Update Copilot Review

Add path-specific review instructions in `.github/copilot-review.yml`:

```yaml
- path: "services/{service}/**"
  instructions: |
    {Domain}-specific review. Verify:
    - {directive 1}
    - {directive 2}
```

## 6. Validate

// turbo
```bash
python scripts/summon_agent.py --list
```

Verify the new persona appears in the roster:

// turbo
```bash
python scripts/swarm_orchestrator.py --roster
```

Test summoning:

```bash
python scripts/summon_agent.py --role {role_key}
```
