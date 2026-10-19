# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: security-audit-fixes.spec.ts >> Security Audit Fixes >> Auth Guard Visibility & Error Handling >> Protected API responses do not leak data in error messages
- Location: tests/e2e/security-audit-fixes.spec.ts:712:13

# Error details

```
AggregateError: apiRequestContext.get: connect ECONNREFUSED ::1:3001
connect ECONNREFUSED 127.0.0.1:3001
Call log:
  - → GET http://localhost:3001/api/admin/v1/users
    - user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.6 Safari/605.1.15
    - accept: */*
    - accept-encoding: gzip,deflate,br

```