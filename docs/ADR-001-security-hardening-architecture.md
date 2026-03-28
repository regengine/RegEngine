# Architecture Decision Record

## ADR-001: Security Hardening Architecture

**Status:** Accepted
**Date:** 2026-03-27
**Decision Makers:** Christopher Sellers

---

## Context

A full-codebase security audit on 2026-03-20 identified 10 critical vulnerabilities and 12 improvement suggestions across the RegEngine platform. The findings spanned backend services (FastAPI), frontend (Next.js), SQL migrations (Supabase), Kubernetes infrastructure, and Docker configuration.

This ADR documents the six key architecture decisions made during the remediation sprint (PRs #320–#330). Each decision involved trade-offs between security posture, implementation risk, and operational complexity.

**Audit references:**
- Backend: `BACKEND_AUDIT_2026-03-20.md`
- Frontend: `FRONTEND_AUDIT_2026-03-20.md`

---

## Decision 1: SQL Injection — Column Allowlisting

### Context
Dynamic column names were interpolated into SQL queries via f-strings, creating SQL injection vectors in sorting and filtering endpoints.

### Decision
Validate all dynamic column names against a frozen allowlist derived from database schema introspection. Reject any column name not in the allowlist with a 400 response.

### Rationale
- More restrictive than parameterization alone (column names cannot be parameterized in SQL)
- Deterministic — the allowlist is derived from the schema, not maintained manually
- Zero runtime overhead beyond a set lookup

### Alternatives Considered

1. **SQLAlchemy ORM migration** — Would eliminate raw SQL entirely
   - Pros: Systematic protection, type safety
   - Cons: High regression risk with 50+ existing asyncpg queries; multi-sprint effort
   - Rejected: Too much blast radius for a security hotfix sprint

2. **Regex validation** — Allow only `[a-zA-Z_]` patterns
   - Pros: Simple to implement
   - Cons: Allows valid-looking but nonexistent columns; doesn't prevent schema probing
   - Rejected: Allowlist is equally simple and strictly more secure

### Consequences
- **Positive**: All SQL injection vectors closed; new columns automatically excluded until explicitly added
- **Negative**: Adding a new sortable/filterable column requires updating the allowlist
- **Neutral**: Existing queries unchanged; only the validation layer is new

**Implementation**: `services/shared/rbac.py`, PR #323

---

## Decision 2: Auth Guards — FastAPI Dependency Injection

### Context
9 API endpoints lacked authentication checks, allowing unauthenticated access to sensitive operations (ingestion, evidence verification, label analysis).

### Decision
Use `Depends(require_permission("scope.action"))` on every endpoint rather than a middleware-based auth gate. Permission strings follow the `resource.action` pattern (e.g., `ingest.read`, `evidence.verify`, `labels.analyze`).

### Rationale
- Consistent with 80% of existing endpoints already using this pattern
- Fine-grained RBAC: each endpoint declares exactly which permission it needs
- Compile-time visible: missing auth is obvious in code review (no implicit middleware)
- Testable: permission checks can be unit tested per endpoint

### Alternatives Considered

1. **Global auth middleware** — Require auth on all `/api/*` routes, exempt specific paths
   - Pros: Can't accidentally miss an endpoint
   - Cons: Requires maintaining an exemption list; inconsistent with existing codebase
   - Rejected: Exemption lists are a security antipattern (new endpoints are secure by default, but exemptions can be stale)

2. **Decorator-based auth** — `@require_auth` decorator on route functions
   - Pros: Visible in code
   - Cons: Doesn't integrate with FastAPI's DI system; can't inject user context
   - Rejected: Loses the ergonomic benefit of `Depends()` providing the authenticated user object

### Consequences
- **Positive**: All 9 endpoints now require explicit auth; RBAC permissions are self-documenting
- **Negative**: Each new endpoint must remember to add `Depends(require_permission())` — but this is the existing convention
- **Neutral**: No migration needed for existing authenticated endpoints

**Implementation**: `services/shared/rbac.py`, `services/ingestion/app/authz.py`, PR #322

---

## Decision 3: RLS — Defense in Depth with Sysadmin Bypass

### Context
Row Level Security (RLS) enforces tenant isolation at the database level. The sysadmin role bypasses RLS for migrations, data repair, and support operations. The audit found this bypass was unmonitored and lacked guardrails.

### Decision
Retain the sysadmin RLS bypass but add three defense layers:
1. **Audit logging**: Every sysadmin query that would bypass RLS is logged to `audit_logs` with the query, timestamp, and user
2. **Role-gated trigger**: A PostgreSQL trigger validates that only the `sysadmin` database role can invoke the bypass
3. **Prometheus alerts**: Alert on sysadmin bypass frequency exceeding baseline (> 10/hour)

### Rationale
- Removing bypass entirely would break migrations and data repair workflows
- Monitoring + alerting makes bypass visible without blocking legitimate operations
- Role-gating prevents privilege escalation from application-level compromise

### Alternatives Considered

1. **Remove sysadmin bypass entirely** — All queries go through RLS
   - Pros: Strongest isolation
   - Cons: Breaks migration scripts, data repair, and support tooling; requires rewriting all admin operations
   - Rejected: Operational necessity outweighs the security benefit

2. **Time-boxed bypass tokens** — Sysadmin gets a short-lived token for bypass
   - Pros: Limits bypass window
   - Cons: Complex to implement; doesn't help with automated migrations
   - Rejected: Audit logging achieves similar visibility with less complexity

### Consequences
- **Positive**: Full audit trail for sysadmin operations; alerting on anomalous bypass patterns
- **Negative**: Slight overhead per sysadmin query (trigger + log insert)
- **Neutral**: No change to application-level tenant isolation behavior

**Implementation**: Supabase migration, PR #324

---

## Decision 4: Frontend Auth — Phased Cookie Migration

### Context
Authentication tokens were stored in `localStorage`, vulnerable to XSS exfiltration. The fix migrates to HTTP-only cookies, but a hard cutover would force-logout all users with active sessions.

### Decision
Dual-write migration approach:
- **Phase 1** (PR #327): Write credentials to both `localStorage` and HTTP-only cookies. Read from cookies first, fall back to `localStorage`.
- **Phase 2** (post-deploy, after confirming cookie auth works): Remove `localStorage` writes. Clear stale `localStorage` entries.

### Rationale
- Zero-downtime migration: users with existing sessions continue working
- Phased approach allows rollback if cookie auth has issues
- HTTP-only cookies eliminate the XSS token theft vector

### Alternatives Considered

1. **Hard cutover** — Remove localStorage, set cookies, force re-login
   - Pros: Clean, no dual-write complexity
   - Cons: All active users logged out simultaneously; support burden
   - Rejected: Unacceptable UX for a security fix that should be invisible to users

2. **Service worker token broker** — Store tokens in a service worker, out of DOM reach
   - Pros: XSS-resistant without cookies
   - Cons: Complex; service worker lifecycle issues; no CSRF protection
   - Rejected: HTTP-only cookies are the industry standard solution

### Consequences
- **Positive**: XSS token theft eliminated; seamless migration for active users
- **Negative**: Temporary dual-write complexity; must remember to execute Phase 2
- **Neutral**: Cookie size adds ~200 bytes per request

**Implementation**: `frontend/src/app/api/session/route.ts`, PR #327

---

## Decision 5: CSRF — Double-Submit Cookie Pattern

### Context
After migrating auth to cookies, the application becomes vulnerable to CSRF attacks. Browser-initiated requests automatically include cookies, so a malicious site could forge state-changing requests.

### Decision
Implement the double-submit cookie pattern:
1. On login, server generates a CSRF token and sets two cookies:
   - `re_csrf` — JS-readable (not httpOnly) so the client can read and attach as a header
   - `re_csrf_sig` — HMAC signature (httpOnly) for server-side verification
2. Middleware verifies `X-CSRF-Token` header matches `re_csrf_sig` on all POST/PUT/PATCH/DELETE to `/api/*`
3. Exemptions: `/api/auth/*`, `/api/webhooks/*`, `/api/session`, and requests with `Authorization: Bearer` header

### Rationale
- Stateless: no server-side session storage required (compatible with serverless/edge)
- Compatible with the existing API proxy architecture
- `SameSite=Lax` cookies provide additional defense layer
- Bearer token exemption supports API clients that don't use browser cookies

### Alternatives Considered

1. **Synchronizer token pattern** — Server stores token in session, client includes in form/header
   - Pros: Slightly stronger (token never in a cookie)
   - Cons: Requires server-side session state; incompatible with stateless edge middleware
   - Rejected: Adds infrastructure dependency (session store) for marginal security gain

2. **SameSite=Strict only** — Rely solely on SameSite cookie attribute
   - Pros: Zero implementation effort
   - Cons: Breaks top-level navigations from external links; not supported in all contexts
   - Rejected: SameSite=Lax is the safe default, but Lax allows top-level GET navigations which could be exploited

### Consequences
- **Positive**: CSRF attacks blocked; no server-side state required
- **Negative**: Every mutating fetch must include the CSRF header (handled by axios interceptor)
- **Neutral**: ~2KB additional cookie overhead; graceful degradation if `CSRF_SECRET` not configured

**Implementation**: `frontend/src/lib/csrf.ts`, `frontend/src/middleware.ts`, PR #329

---

## Decision 6: JWT — Key ID (kid) Rotation

### Context
JWT tokens were signed with a single static secret. Rotating the secret required invalidating all active tokens simultaneously, causing a mass logout event.

### Decision
Add `kid` (Key ID) header to JWTs and implement a key registry supporting multiple active keys:
1. New key generated and added to registry
2. New tokens signed with the new key (identified by `kid`)
3. Existing tokens validated against the key matching their `kid`
4. Old key removed after token TTL expiry (tokens naturally expire)

### Rationale
- Zero-downtime key rotation: no user impact during rotation
- Standard JWT practice (RFC 7515 `kid` header)
- Supports emergency rotation: add new key, immediately stop signing with old key, old tokens expire naturally

### Alternatives Considered

1. **Token blacklisting** — Maintain a revocation list, rotate key, blacklist old tokens
   - Pros: Immediate revocation capability
   - Cons: Requires a shared blacklist store (Redis); O(n) lookup per request
   - Rejected: Over-engineered for routine rotation; `kid`-based approach handles the normal case

2. **Short-lived tokens + refresh tokens** — 5-minute access tokens with longer refresh tokens
   - Pros: Limits exposure window
   - Cons: Major auth flow rewrite; refresh token storage and rotation adds complexity
   - Rejected: Larger scope change than needed; can be added later as an enhancement

### Consequences
- **Positive**: Key rotation without downtime; emergency rotation support; standard `kid` header
- **Negative**: Key registry adds a small amount of state to manage
- **Neutral**: Existing tokens continue to work until natural expiry

**Implementation**: `services/shared/crypto_signing.py` (`MultiKeySigner`), `services/shared/jwt_auth.py`, PR #328

---

## Summary

| Decision | Pattern | Key Trade-off |
|---|---|---|
| SQL Injection | Column allowlist | Restrictive but requires manual updates for new columns |
| Auth Guards | FastAPI `Depends()` | Per-endpoint declaration vs. global middleware |
| RLS | Audit + alert on bypass | Operational access preserved with visibility |
| Cookie Migration | Dual-write phased | Zero-downtime migration with temporary complexity |
| CSRF | Double-submit cookie | Stateless but requires client-side header attachment |
| JWT Rotation | `kid` header + key registry | Zero-downtime rotation with key lifecycle management |

## References

- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [RFC 7515 — JSON Web Signature (JWS)](https://datatracker.ietf.org/doc/html/rfc7515) — `kid` header parameter
- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- Deploy Checklist: `docs/DEPLOY_CHECKLIST_SECURITY_HARDENING.md`
- Backend Audit: `BACKEND_AUDIT_2026-03-20.md`
- Frontend Audit: `FRONTEND_AUDIT_2026-03-20.md`
- FSMA SLOs: `nfr/fsma_slos.yaml`
