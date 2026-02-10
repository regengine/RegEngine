---
description: Run a security audit using Bot-Security persona directives
---

# Security Audit Workflow

Run this workflow to perform a comprehensive security audit of the RegEngine codebase using Bot-Security's mission directives.

## 1. Activate Bot-Security

```bash
python scripts/summon_agent.py --role security --task "Full security audit of the RegEngine codebase"
```

Or via the orchestrator:
```bash
python scripts/swarm_orchestrator.py --sweep security
```

## 2. Secrets Scan

// turbo
```bash
grep -rn --include="*.py" --include="*.ts" --include="*.tsx" -E "(password\s*=\s*['\"][^'\"]+|api_key\s*=\s*['\"][^'\"]+|secret\s*=\s*['\"][^'\"]+)" services/ shared/ frontend/src/ | grep -v test | grep -v __pycache__ | grep -v node_modules || echo "✅ No hardcoded secrets found"
```

## 3. IDOR Vulnerability Scan

Check all database queries include tenant scoping:

// turbo
```bash
grep -rn --include="*.py" "\.execute\|\.query\|session\." services/ | grep -v "tenant_id" | grep -v test | grep -v __pycache__ | grep -v migration || echo "✅ All queries include tenant scoping"
```

## 4. Input Sanitization Check

Verify all endpoints use Pydantic validation:

// turbo
```bash
grep -rn --include="*.py" "def.*request.*:" services/*/app/ | grep -v "Depends\|BaseModel\|Pydantic" | head -20 || echo "✅ Endpoint input validation looks good"
```

## 5. RLS Verification

// turbo
```bash
grep -rn --include="*.sql" "ROW LEVEL SECURITY\|CREATE POLICY" infra/ services/ || echo "⚠️ No RLS policies found in SQL files"
```

## 6. Print Statement Audit

Production code should use structlog, not print():

// turbo
```bash
grep -rn --include="*.py" "^\s*print(" services/ shared/ | grep -v test | grep -v __pycache__ || echo "✅ No print statements in production code"
```

## 7. Run Security Tests

```bash
pytest -m security -q 2>&1 | tail -20
```

## 8. Generate Report

Document findings using the agent output schema:
- Reference: `.agent/protocols/output_schema.md`
- Create a JSON output file with all findings
- If risks found, create a GitHub Issue tagged `agent:security`
