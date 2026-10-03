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
    - user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.8010.12 Safari/537.36
    - accept: */*
    - accept-encoding: gzip,deflate,br

```