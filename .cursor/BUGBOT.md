# Cursor Bugbot Review Guidelines

Bugbot code review focus for RegEngine, an FSMA 204 food traceability compliance platform. Focus review on the core production spine (ingest, normalize, validate, persist evidence, export) and enforce the following standards.

## 1. Security

- Authentication: Verify every route handler, API endpoint, and server action enforces authentication. Check server/route_security_policy.py to ensure new or updated routes declare an explicit auth policy. Never allow routes to become public by omission.
- Tenant Isolation: Every database query, Neo4j graph traversal, Redis cache key, and event payload must be strictly scoped to the authenticated tenant. Never trust a tenant identifier from a request body or client parameter; always resolve tenant context from verified session credentials.
- Row Level Security (RLS): All PostgreSQL tables containing tenant data must enable and force Row Level Security. Policies must enforce tenant isolation on both USING and WITH CHECK clauses. Flag any policy with USING (true) or that defaults to a nil or fallback tenant.
- Injection: Flag dynamic SQL formatting, unsanitized Cypher queries in Neo4j, path traversal, or command injection. All queries must use parameterized arguments or ORM abstractions.

## 2. Secrets

- Never Commit Secrets: Flag any committed keys, tokens, passwords, private keys, certificates, or environment variable values.
- Hardcoded Credentials: Flag any hardcoded API key, token, or fallback credential in source files, configs, scripts, or tests. Secrets must come from environment variables or vault storage (cw-vault or Railway).
- Client Isolation: Client-side bundles in frontend/ must never import server-side modules, database clients, or non-public environment variables. Only NEXT_PUBLIC_* variables may reach the client.
- Redaction and Logging: Flag any log statement or error output that leaks credentials, authorization tokens, or sensitive tenant data.

## 3. Tests

- Behavior Changes Require Tests: Any bug fix, feature addition, or business logic modification must include automated tests (pytest for Python services, Vitest or Playwright for frontend).
- Do Not Weaken Assertions: Reject changes that remove assertions, widen tolerances, replace strict checks with no-ops, or add skip/xfail decorators to make a failing test pass.
- Negative Path Coverage: Critical security and compliance paths (auth, tenant isolation, schema validation, tamper detection) must include negative-path tests covering unauthorized access, cross-tenant requests, and malformed payloads.

## 4. Real Data Only

- No Fabricated Data in Product Code: Flag synthetic, fabricated, or placeholder data in product code. Production code must never use mock supplier names, dummy facility GLNs, or fake FDA registration numbers.
- Flag Invented KDEs: Flag test fixtures or migrations that invent Key Data Elements (KDEs), fabricated Traceability Lot Codes (TLCs), or synthetic TLC source identifiers.
- No Lazy Defaults: Flag arbitrary default values such as quantity 1.0, generic units of measure, or hardcoded harvest and packing dates. FSMA 204 requires exact traceability data as received; missing KDEs must trigger validation failures rather than silent defaults.
