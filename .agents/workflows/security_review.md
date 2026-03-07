Review the requested change for RegEngine-specific security risks.

Check:
- auth and session boundaries
- tenant isolation
- raw SQL or Cypher concatenation
- secrets committed to code or docs
- PII leaks in logs or responses
- missing negative tests for protected routes

Use `services/shared/`, `docs/security/`, and the changed files as the primary context.
Return concrete findings with file paths and severity.
