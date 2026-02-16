---
description: How to trigger the CI Resilience Agent to heal failing pipelines
---

# 🧬 CI Resilience Workflow

Use this workflow when a GitHub Action or local test suite fails consistently.

## Steps

1. **Collect Failure Logs**: Extract the failing section of the CI logs.
2. **Invoke Resilience Agent**: 
// turbo
```bash
python3 -m regengine.swarm.cli --agent sre --task "Analyze CI failure: [PASTE_LOGS_HERE]"
```
3. **Review Diagnosis**: Check the `root_cause` and `remediation` plan provided by the agent.
4. **Execute Fix**: The agent will propose specific file modifications. Use the `CoderAgent` to apply them if they involve code changes.
5. **Verify**: Re-run the failing CI job or local test.

## Example
If a test fails due to a missing environment variable:
- Agent identifies: `Missing RTO_THRESHOLD in environment`
- Agent proposes: `Add default value to config.py or update .github/workflows/backend-ci.yml`
- CoderAgent applies the fix.
